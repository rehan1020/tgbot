"""
Jupiter DEX integration for Solana.
"""

import asyncio
import base64
import base58
from typing import Optional
from datetime import datetime

import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.signature import Signature

from config import QUOTE_TOKENS
from models import Chain, TradeResult
from dex.base import BaseDEX, Quote
from utils.logger import get_logger

logger = get_logger("jupiter")

# Jupiter API endpoints
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
JUPITER_PRICE_API = "https://price.jup.ag/v6/price"


class JupiterDEX(BaseDEX):
    """Jupiter DEX integration for Solana swaps."""
    
    def __init__(self, rpc_url: str, private_key: Optional[str] = None):
        """
        Initialize Jupiter DEX.
        
        Args:
            rpc_url: Solana RPC endpoint
            private_key: Base58 encoded private key
        """
        super().__init__(Chain.SOLANA, rpc_url, private_key)
        
        self.client = AsyncClient(rpc_url)
        self.keypair: Optional[Keypair] = None
        self.wallet_address: Optional[str] = None
        
        if private_key:
            try:
                # Decode base58 private key
                secret = base58.b58decode(private_key)
                self.keypair = Keypair.from_bytes(secret)
                self.wallet_address = str(self.keypair.pubkey())
                logger.info(f"Wallet initialized: {self.wallet_address[:8]}...")
            except Exception as e:
                logger.error(f"Failed to initialize wallet: {e}")
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def close(self):
        """Close connections."""
        if self._session and not self._session.closed:
            await self._session.close()
        await self.client.close()
    
    async def get_quote(
        self,
        input_token: str,
        output_token: str,
        amount: float,
        slippage: float = 0.01,
    ) -> Optional[Quote]:
        """Get a swap quote from Jupiter."""
        try:
            session = await self._get_session()
            
            # Convert amount to lamports (assuming 6 decimals for USDC/USDT)
            # TODO: Get actual decimals from token metadata
            decimals = 6 if input_token in QUOTE_TOKENS["solana"].values() else 9
            amount_raw = int(amount * (10 ** decimals))
            
            params = {
                "inputMint": input_token,
                "outputMint": output_token,
                "amount": str(amount_raw),
                "slippageBps": int(slippage * 10000),  # Convert to basis points
            }
            
            async with session.get(JUPITER_QUOTE_API, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Jupiter quote failed: {error_text}")
                    return None
                
                data = await response.json()
                
                # Parse quote response
                out_amount_raw = int(data.get("outAmount", 0))
                out_decimals = 9  # TODO: Get from token metadata
                out_amount = out_amount_raw / (10 ** out_decimals)
                
                price = out_amount / amount if amount > 0 else 0
                price_impact = float(data.get("priceImpactPct", 0))
                
                # Build route description
                route_info = data.get("routePlan", [])
                route_str = " → ".join(
                    [r.get("swapInfo", {}).get("label", "?") for r in route_info]
                ) or "Direct"
                
                return Quote(
                    input_token=input_token,
                    output_token=output_token,
                    input_amount=amount,
                    output_amount=out_amount,
                    price=price,
                    price_impact=price_impact,
                    route=route_str,
                    raw_quote=data,
                )
                
        except Exception as e:
            logger.error(f"Error getting Jupiter quote: {e}")
            return None
    
    async def execute_swap(
        self,
        quote: Quote,
        dry_run: bool = False,
    ) -> TradeResult:
        """Execute a swap on Jupiter."""
        if not self.keypair:
            return TradeResult(
                success=False,
                error="Wallet not initialized. Provide private key.",
            )
        
        if dry_run:
            logger.info(
                f"[DRY RUN] Would swap {quote.input_amount} "
                f"→ {quote.output_amount} via {quote.route}"
            )
            return TradeResult(
                success=True,
                amount_in=quote.input_amount,
                amount_out=quote.output_amount,
                price=quote.price,
                tx_hash="DRY_RUN_NO_TX",
            )
        
        try:
            session = await self._get_session()
            
            # Request swap transaction
            swap_request = {
                "quoteResponse": quote.raw_quote,
                "userPublicKey": self.wallet_address,
                "wrapAndUnwrapSol": True,
            }
            
            async with session.post(JUPITER_SWAP_API, json=swap_request) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return TradeResult(
                        success=False,
                        error=f"Jupiter swap request failed: {error_text}",
                    )
                
                data = await response.json()
            
            # Decode and sign transaction
            swap_tx_data = data.get("swapTransaction")
            if not swap_tx_data:
                return TradeResult(
                    success=False,
                    error="No swap transaction returned",
                )
            
            # Decode base64 transaction
            tx_bytes = base64.b64decode(swap_tx_data)
            transaction = Transaction.deserialize(tx_bytes)
            
            # Sign transaction
            transaction.sign(self.keypair)
            
            # Send transaction
            result = await self.client.send_transaction(
                transaction,
                self.keypair,
                opts={"skip_preflight": False},
            )
            
            tx_hash = str(result.value)
            logger.info(f"✅ Swap executed: {tx_hash}")
            
            return TradeResult(
                success=True,
                tx_hash=tx_hash,
                amount_in=quote.input_amount,
                amount_out=quote.output_amount,
                price=quote.price,
            )
            
        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return TradeResult(
                success=False,
                error=str(e),
            )
    
    async def get_token_price(self, token_address: str) -> Optional[float]:
        """Get token price in USD from Jupiter."""
        try:
            session = await self._get_session()
            
            params = {"ids": token_address}
            
            async with session.get(JUPITER_PRICE_API, params=params) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                price_data = data.get("data", {}).get(token_address, {})
                return float(price_data.get("price", 0)) or None
                
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return None
    
    async def get_token_balance(self, token_address: str) -> float:
        """Get SPL token balance."""
        if not self.wallet_address:
            return 0
        
        try:
            # Get token accounts
            response = await self.client.get_token_accounts_by_owner_json_parsed(
                self.keypair.pubkey(),
                {"mint": token_address},
            )
            
            if response.value:
                account = response.value[0]
                amount = account.account.data.parsed["info"]["tokenAmount"]
                return float(amount["uiAmount"] or 0)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting token balance: {e}")
            return 0
    
    async def get_native_balance(self) -> float:
        """Get SOL balance."""
        if not self.wallet_address:
            return 0
        
        try:
            response = await self.client.get_balance(self.keypair.pubkey())
            # Convert lamports to SOL
            return response.value / 1e9
            
        except Exception as e:
            logger.error(f"Error getting SOL balance: {e}")
            return 0
