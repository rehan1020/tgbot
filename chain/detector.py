"""
Chain detection module.
Automatically detects which blockchain a contract address belongs to.
"""

import asyncio
import re
from typing import Optional, Dict, Any

import aiohttp

from models import Chain, TokenInfo
from utils.logger import get_logger

logger = get_logger("chain_detector")


# DexScreener API endpoint
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

# GeckoTerminal API endpoint (backup)
GECKOTERMINAL_API = "https://api.geckoterminal.com/api/v2/networks"

# Chain ID to Chain enum mapping
CHAIN_MAPPING = {
    "solana": Chain.SOLANA,
    "ethereum": Chain.ETHEREUM,
    "eth": Chain.ETHEREUM,
    "ethereum-sepolia": Chain.ETHEREUM_SEPOLIA,
    "sepolia": Chain.ETHEREUM_SEPOLIA,
    "ethereum-goerli": Chain.ETHEREUM_GOERLI,
    "goerli": Chain.ETHEREUM_GOERLI,
    "bsc": Chain.BSC,
    "binance": Chain.BSC,
    "base": Chain.BASE,
    "arbitrum": Chain.ARBITRUM,
    "arbitrum-one": Chain.ARBITRUM,
}


class ChainDetector:
    """Detect which blockchain a token address belongs to."""
    
    def __init__(self):
        """Initialize chain detector."""
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def detect_address_format(self, address: str) -> Optional[str]:
        """
        Detect address format (Solana vs EVM) based on the address string.
        
        Args:
            address: Contract address to check
            
        Returns:
            "solana", "evm", or None if invalid
        """
        # EVM address: 0x followed by 40 hex characters
        if re.match(r'^0x[a-fA-F0-9]{40}$', address):
            return "evm"
        
        # Solana address: Base58, 32-44 characters
        base58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        if 32 <= len(address) <= 44 and all(c in base58_chars for c in address):
            return "solana"
        
        return None
    
    async def detect_chain(self, address: str) -> Optional[Chain]:
        """
        Detect which blockchain the token exists on.
        
        Args:
            address: Contract address
            
        Returns:
            Chain enum if detected, None otherwise
        """
        # First, check address format
        format_type = self.detect_address_format(address)
        
        if format_type is None:
            logger.error(f"Invalid address format: {address}")
            return None
        
        if format_type == "solana":
            logger.info(f"Detected Solana address: {address[:8]}...")
            return Chain.SOLANA
        
        # For EVM addresses, query DexScreener to find the chain
        logger.info(f"EVM address detected, querying DexScreener...")
        return await self._detect_evm_chain(address)
    
    async def _detect_evm_chain(self, address: str) -> Optional[Chain]:
        """
        Detect which EVM chain the token is on using DexScreener.
        
        Args:
            address: EVM contract address
            
        Returns:
            Chain enum if found, None otherwise
        """
        try:
            session = await self._get_session()
            url = f"{DEXSCREENER_API}/{address}"
            
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"DexScreener API returned {response.status}")
                    return await self._fallback_chain_detection(address)
                
                data = await response.json()
                
                if not data.get("pairs"):
                    logger.warning(f"No pairs found for {address}")
                    return await self._fallback_chain_detection(address)
                
                # Get the chain from the first pair (usually highest liquidity)
                pair = data["pairs"][0]
                chain_id = pair.get("chainId", "").lower()
                
                chain = CHAIN_MAPPING.get(chain_id)
                
                if chain:
                    logger.info(f"Detected chain: {chain.value} for {address[:8]}...")
                    return chain
                else:
                    logger.warning(f"Unknown chain ID from DexScreener: {chain_id}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.warning("DexScreener API timeout, trying fallback...")
            return await self._fallback_chain_detection(address)
        except Exception as e:
            logger.error(f"Error querying DexScreener: {e}")
            return await self._fallback_chain_detection(address)
    
    async def _fallback_chain_detection(self, address: str) -> Optional[Chain]:
        """
        Fallback chain detection using GeckoTerminal.
        
        Args:
            address: EVM contract address
            
        Returns:
            Chain enum if found, None otherwise
        """
        # Networks to check in order of popularity
        networks = [
            ("eth", Chain.ETHEREUM),
            ("ethereum-sepolia", Chain.ETHEREUM_SEPOLIA),  # Sepolia testnet
            ("ethereum-goerli", Chain.ETHEREUM_GOERLI),   # Goerli testnet
            ("bsc", Chain.BSC),
            ("base", Chain.BASE),
            ("arbitrum", Chain.ARBITRUM),
        ]
        
        try:
            session = await self._get_session()
            
            for network_id, chain in networks:
                url = f"{GECKOTERMINAL_API}/{network_id}/tokens/{address}"
                
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            logger.info(f"Found token on {chain.value} via GeckoTerminal")
                            return chain
                except:
                    continue
            
            logger.warning(f"Could not detect chain for {address}")
            return None
            
        except Exception as e:
            logger.error(f"Fallback chain detection failed: {e}")
            return None
    
    async def get_token_info(self, address: str, chain: Optional[Chain] = None) -> Optional[TokenInfo]:
        """
        Get detailed token information.
        
        Args:
            address: Contract address
            chain: Chain if already known
            
        Returns:
            TokenInfo if found, None otherwise
        """
        if chain is None:
            chain = await self.detect_chain(address)
        
        if chain is None:
            return None
        
        try:
            session = await self._get_session()
            url = f"{DEXSCREENER_API}/{address}"
            
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                
                if not data.get("pairs"):
                    return None
                
                # Get info from the first (most liquid) pair
                pair = data["pairs"][0]
                base_token = pair.get("baseToken", {})
                
                return TokenInfo(
                    address=address,
                    symbol=base_token.get("symbol", "UNKNOWN"),
                    name=base_token.get("name", "Unknown Token"),
                    decimals=18,  # Default, may need to query on-chain
                    chain=chain,
                    price_usd=float(pair.get("priceUsd", 0)) if pair.get("priceUsd") else None,
                    liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)) if pair.get("liquidity") else None,
                )
                
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return None


# Singleton instance
_detector: Optional[ChainDetector] = None


def get_chain_detector() -> ChainDetector:
    """Get the chain detector singleton."""
    global _detector
    if _detector is None:
        _detector = ChainDetector()
    return _detector


async def detect_chain(address: str) -> Optional[Chain]:
    """Convenience function to detect chain."""
    detector = get_chain_detector()
    return await detector.detect_chain(address)
