"""
Configuration module for Telegram Trading Bot.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class TelegramConfig:
    """Telegram User Client configuration."""
    api_id: int
    api_hash: str
    phone: str
    target_group: int
    password: Optional[str] = None  # 2FA password
    session_name: str = "trading_bot"


@dataclass
class WalletConfig:
    """Wallet private keys configuration."""
    solana_private_key: Optional[str] = None
    evm_private_key: Optional[str] = None


@dataclass
class RPCConfig:
    # RPC endpoints for each chain.
    # Solana
    solana: str = "https://api.mainnet-beta.solana.com"
        
    # EVM Chains (Ethereum & L2s)
    ethereum: str = "https://eth.llamarpc.com"
    ethereum_sepolia: str = "https://ethereum-sepolia-rpc.publicnode.com"  # Sepolia testnet
    ethereum_goerli: str = "https://ethereum-goerli-rpc.publicnode.com"     # Goerli testnet
    bsc: str = "https://bsc-dataseed1.binance.org"
    base: str = "https://mainnet.base.org"
    arbitrum: str = "https://arb1.arbitrum.io/rpc"
    polygon: str = "https://polygon-rpc.com"
    avalanche: str = "https://api.avax.network/ext/bc/C/rpc"
    optimism: str = "https://mainnet.optimism.io"
    ronin: str = "https://api.roninchain.com/rpc"
        
    # TON Network
    ton: str = "https://toncenter.com/api/v2/jsonRPC"
    
    # Chain IDs for EVM chains
    chain_ids: Dict[str, int] = field(default_factory=lambda: {
        "ethereum": 1,
        "ethereum_sepolia": 11155111,  # Sepolia testnet
        "ethereum_goerli": 5,           # Goerli testnet
        "bsc": 56,
        "base": 8453,
        "arbitrum": 42161,
        "polygon": 137,
        "avalanche": 43114,
        "optimism": 10,
        "ronin": 2020,
    })


@dataclass
class TradingConfig:
    """Trading parameters."""
    capital_percent: float = 0.05  # 5% of capital per trade
    max_positions: int = 1
    slippage_tolerance: float = 0.01  # 1%
    price_check_interval: int = 10  # seconds
    dry_run: bool = True


@dataclass
class Config:
    """Main configuration container."""
    telegram: TelegramConfig
    wallet: WalletConfig
    rpc: RPCConfig
    trading: TradingConfig
    log_level: str = "INFO"
    log_file: Optional[str] = None


def load_config() -> Config:
    """Load configuration from environment variables."""
    
    # Telegram config
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    phone = os.getenv("TELEGRAM_PHONE")
    target_group = os.getenv("TELEGRAM_TARGET_GROUP")
    
    if not all([api_id, api_hash, phone]):
        raise ValueError(
            "Missing Telegram config. Get API credentials from https://my.telegram.org"
        )
    
    if not target_group:
        raise ValueError("Missing TELEGRAM_TARGET_GROUP")
    
    telegram_config = TelegramConfig(
        api_id=int(api_id),
        api_hash=api_hash,
        phone=phone,
        target_group=int(target_group),
        password=os.getenv("TELEGRAM_PASSWORD") or None,
    )
    
    # Wallet config
    wallet_config = WalletConfig(
        solana_private_key=os.getenv("SOLANA_PRIVATE_KEY"),
        evm_private_key=os.getenv("EVM_PRIVATE_KEY"),
    )
    
    # RPC config with custom endpoints if provided
    rpc_config = RPCConfig()
    if os.getenv("SOLANA_RPC_URL"):
        rpc_config.solana = os.getenv("SOLANA_RPC_URL")
    if os.getenv("ETHEREUM_RPC_URL"):
        rpc_config.ethereum = os.getenv("ETHEREUM_RPC_URL")
    if os.getenv("ETHEREUM_SEPOLIA_RPC_URL"):
        rpc_config.ethereum_sepolia = os.getenv("ETHEREUM_SEPOLIA_RPC_URL")
    if os.getenv("ETHEREUM_GOERLI_RPC_URL"):
        rpc_config.ethereum_goerli = os.getenv("ETHEREUM_GOERLI_RPC_URL")
    if os.getenv("BSC_RPC_URL"):
        rpc_config.bsc = os.getenv("BSC_RPC_URL")
    if os.getenv("BASE_RPC_URL"):
        rpc_config.base = os.getenv("BASE_RPC_URL")
    if os.getenv("ARBITRUM_RPC_URL"):
        rpc_config.arbitrum = os.getenv("ARBITRUM_RPC_URL")
    if os.getenv("POLYGON_RPC_URL"):
        rpc_config.polygon = os.getenv("POLYGON_RPC_URL")
    if os.getenv("AVALANCHE_RPC_URL"):
        rpc_config.avalanche = os.getenv("AVALANCHE_RPC_URL")
    if os.getenv("OPTIMISM_RPC_URL"):
        rpc_config.optimism = os.getenv("OPTIMISM_RPC_URL")
    if os.getenv("RONIN_RPC_URL"):
        rpc_config.ronin = os.getenv("RONIN_RPC_URL")
    if os.getenv("TON_RPC_URL"):
        rpc_config.ton = os.getenv("TON_RPC_URL")
    
    # Trading config
    trading_config = TradingConfig(
        capital_percent=float(os.getenv("TRADE_CAPITAL_PERCENT", "0.05")),
        max_positions=int(os.getenv("MAX_POSITIONS", "1")),
        slippage_tolerance=float(os.getenv("SLIPPAGE_TOLERANCE", "0.01")),
        price_check_interval=int(os.getenv("PRICE_CHECK_INTERVAL", "10")),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )
    
    return Config(
        telegram=telegram_config,
        wallet=wallet_config,
        rpc=rpc_config,
        trading=trading_config,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE"),
    )


# Quote token addresses for each chain (USDT/USDC)
QUOTE_TOKENS = {
    "solana": {
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    },
    "ethereum": {
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    },
    "ethereum_sepolia": {
        "USDC": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",  # Sepolia USDC
        "USDT": "0x50ac23d5d36302aa90a89e9f601b3f4d8a7d92d0",  # Sepolia USDT equivalent
    },
    "ethereum_goerli": {
        "USDC": "0x07865c6e87b9f7025bc9e0b34ef87b92350e9ce4",  # Goerli USDC
        "USDT": "0x50ac23d5d36302aa90a89e9f601b3f4d8a7d92d0",  # Goerli USDT equivalent
    },
    "bsc": {
        "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "USDT": "0x55d398326f99059fF775485246999027B3197955",
    },
    "base": {
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "USDT": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
    },
    "arbitrum": {
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    },
}

# Native tokens for gas
NATIVE_TOKENS = {
    "solana": "SOL",
    "ethereum": "ETH",
    "ethereum_sepolia": "ETH",  # Sepolia testnet
    "ethereum_goerli": "ETH",   # Goerli testnet
    "bsc": "BNB",
    "base": "ETH",
    "arbitrum": "ETH",
}
