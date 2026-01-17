"""
1inch DEX aggregator integration for EVM chains.
"""

import asyncio
from typing import Optional, Dict
from datetime import datetime

import aiohttp
from web3 import Web3
from eth_account import Account

from config import QUOTE_TOKENS, RPCConfig
from models import Chain, TradeResult
from dex.base import BaseDEX, Quote
from utils.logger import get_logger

logger = get_logger("oneinch")

# 1inch API endpoints by chain
ONEINCH_API = {
    Chain.ETHEREUM: "https://api.1inch.dev/swap/v6.0/1",
    Chain.ETHEREUM_SEPOLIA: "https://api.1inch.dev/swap/v6.0/11155111",  # Sepolia testnet
    Chain.ETHEREUM_GOERLI: "https://api.1inch.dev/swap/v6.0/5",           # Goerli testnet
    Chain.BSC: "https://api.1inch.dev/swap/v6.0/56",
    Chain.BASE: "https://api.1inch.dev/swap/v6.0/8453",
    Chain.ARBITRUM: "https://api.1inch.dev/swap/v6.0/42161",
}

# Native token addresses (for wrapping)
NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


class OneInchDEX(BaseDEX):
    """1inch DEX aggregator for EVM chain swaps."""
    
    def __init__(
        self,
        chain: Chain,
        rpc_url: str,
        private_key: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize 1inch DEX.
        
        Args:
            chain: EVM chain to use
            rpc_url: RPC endpoint URL
            private_key: Hex-encoded private key (with or without 0x)
            api_key: 1inch API key (optional but recommended)
        """
        super().__init__(chain, rpc_url, private_key)
        
        self.api_base = ONEINCH_API.get(chain)
        if not self.api_base:
            raise ValueError(f"Chain {chain} not supported by 1inch integration")
        
        self.api_key = api_key
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        
        self.account: Optional[Account] = None
        self.wallet_address: Optional[str] = None
        
        if private_key:
            try:
                # Normalize private key
                if not private_key.startswith("0x"):
                    private_key = "0x" + private_key
                
                self.account = Account.from_key(private_key)
                self.wallet_address = self.account.address
                logger.info(f"Wallet initialized: {self.wallet_address[:10]}...")
            except Exception as e:
                logger.error(f"Failed to initialize wallet: {e}")
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
            )
        return self._session
    
    async def close(self):
        """Close connections."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_quote(
        self,
        input_token: str,
        output_token: str,
        amount: float,
        slippage: float = 0.01,
    ) -> Optional[Quote]:
        """Get a swap quote from 1inch."""
        try:
            session = await self._get_session()
            
            # Get token decimals (default to 18 for most ERC20)
            # USDT/USDC typically have 6 decimals
            if input_token in QUOTE_TOKENS.get(self.chain.value, {}).values():
                decimals = 6
            else:
                decimals = 18
            
            amount_raw = int(amount * (10 ** decimals))
            
            params = {
                "src": input_token,
                "dst": output_token,
                "amount": str(amount_raw),
            }
            
            url = f"{self.api_base}/quote"
            
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"1inch quote failed: {error_text}")
                    return None
                
                data = await response.json()
            
            # Parse response
            out_amount_raw = int(data.get("dstAmount", 0))
            out_decimals = 18  # TODO: Get from token metadata
            out_amount = out_amount_raw / (10 ** out_decimals)
            
            price = out_amount / amount if amount > 0 else 0
            
            # Extract protocols used
            protocols = data.get("protocols", [[]])
            if protocols and protocols[0]:
                route_parts = []
                for hop in protocols[0]:
                    if hop:
                        names = [p.get("name", "?") for p in hop]
                        route_parts.append("/".join(names))
                route_str = " → ".join(route_parts)
            else:
                route_str = "Direct"
            
            return Quote(
                input_token=input_token,
                output_token=output_token,
                input_amount=amount,
                output_amount=out_amount,
                price=price,
                price_impact=0,  # 1inch doesn't return this directly
                route=route_str,
                raw_quote=data,
            )
            
        except Exception as e:
            logger.error(f"Error getting 1inch quote: {e}")
            return None
    
    async def execute_swap(
        self,
        quote: Quote,
        dry_run: bool = False,
    ) -> TradeResult:
        """Execute a swap on 1inch."""
        if not self.account:
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
            
            # Get swap transaction data
            decimals = 6 if quote.input_token in QUOTE_TOKENS.get(self.chain.value, {}).values() else 18
            amount_raw = int(quote.input_amount * (10 ** decimals))
            
            params = {
                "src": quote.input_token,
                "dst": quote.output_token,
                "amount": str(amount_raw),
                "from": self.wallet_address,
                "slippage": 1,  # 1%
                "disableEstimate": "true",
            }
            
            url = f"{self.api_base}/swap"
            
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return TradeResult(
                        success=False,
                        error=f"1inch swap request failed: {error_text}",
                    )
                
                data = await response.json()
            
            # Build and send transaction
            tx = data.get("tx", {})
            
            transaction = {
                "from": self.wallet_address,
                "to": Web3.to_checksum_address(tx.get("to")),
                "value": int(tx.get("value", 0)),
                "data": tx.get("data"),
                "gas": int(tx.get("gas", 300000)),
                "gasPrice": int(tx.get("gasPrice", self.web3.eth.gas_price)),
                "nonce": self.web3.eth.get_transaction_count(self.wallet_address),
                "chainId": self.web3.eth.chain_id,
            }
            
            # Sign transaction
            signed_tx = self.account.sign_transaction(transaction)
            
            # Send transaction
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"✅ Swap executed: {tx_hash_hex}")
            
            # Wait for confirmation
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                return TradeResult(
                    success=True,
                    tx_hash=tx_hash_hex,
                    amount_in=quote.input_amount,
                    amount_out=quote.output_amount,
                    price=quote.price,
                    gas_used=receipt.gasUsed,
                )
            else:
                return TradeResult(
                    success=False,
                    tx_hash=tx_hash_hex,
                    error="Transaction reverted",
                )
                
        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return TradeResult(
                success=False,
                error=str(e),
            )
    
    async def get_token_price(self, token_address: str) -> Optional[float]:
        """Get token price using DexScreener (more reliable than 1inch for price)."""
        try:
            session = await self._get_session()
            
            # Use DexScreener for price
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                pairs = data.get("pairs", [])
                
                if pairs:
                    return float(pairs[0].get("priceUsd", 0)) or None
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return None
    
    async def get_token_balance(self, token_address: str) -> float:
        """Get ERC20 token balance."""
        if not self.wallet_address:
            return 0
        
        try:
            # ERC20 balanceOf ABI
            abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function",
                },
            ]
            
            contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=abi,
            )
            
            balance_raw = contract.functions.balanceOf(self.wallet_address).call()
            decimals = contract.functions.decimals().call()
            
            return balance_raw / (10 ** decimals)
            
        except Exception as e:
            logger.error(f"Error getting token balance: {e}")
            return 0
    
    async def get_native_balance(self) -> float:
        """Get native token balance (ETH/BNB)."""
        if not self.wallet_address:
            return 0
        
        try:
            balance_wei = self.web3.eth.get_balance(self.wallet_address)
            return balance_wei / 1e18
            
        except Exception as e:
            logger.error(f"Error getting native balance: {e}")
            return 0
    
    async def approve_token(
        self,
        token_address: str,
        spender: str,
        amount: Optional[int] = None,
    ) -> bool:
        """
        Approve token spending for 1inch router.
        
        Args:
            token_address: Token to approve
            spender: Address to approve (1inch router)
            amount: Amount to approve (None = unlimited)
            
        Returns:
            True if approval successful
        """
        if not self.account:
            return False
        
        try:
            # ERC20 approve ABI
            abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_spender", "type": "address"},
                        {"name": "_value", "type": "uint256"},
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function",
                },
            ]
            
            contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=abi,
            )
            
            # Unlimited approval if amount not specified
            if amount is None:
                amount = 2**256 - 1
            
            tx = contract.functions.approve(
                Web3.to_checksum_address(spender),
                amount,
            ).build_transaction({
                "from": self.wallet_address,
                "gas": 100000,
                "gasPrice": self.web3.eth.gas_price,
                "nonce": self.web3.eth.get_transaction_count(self.wallet_address),
                "chainId": self.web3.eth.chain_id,
            })
            
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            return receipt.status == 1
            
        except Exception as e:
            logger.error(f"Error approving token: {e}")
            return False


def get_oneinch_for_chain(
    chain: Chain,
    rpc_config: RPCConfig,
    private_key: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[OneInchDEX]:
    """
    Get 1inch DEX instance for a specific chain.
    
    Args:
        chain: Target chain
        rpc_config: RPC configuration
        private_key: Wallet private key
        api_key: 1inch API key
        
    Returns:
        OneInchDEX instance if chain is supported
    """
    rpc_urls = {
        Chain.ETHEREUM: rpc_config.ethereum,
        Chain.ETHEREUM_SEPOLIA: rpc_config.ethereum_sepolia,  # Sepolia testnet
        Chain.ETHEREUM_GOERLI: rpc_config.ethereum_goerli,    # Goerli testnet
        Chain.BSC: rpc_config.bsc,
        Chain.BASE: rpc_config.base,
        Chain.ARBITRUM: rpc_config.arbitrum,
    }
    
    rpc_url = rpc_urls.get(chain)
    if not rpc_url:
        return None
    
    return OneInchDEX(chain, rpc_url, private_key, api_key)
