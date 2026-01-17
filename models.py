"""
Data models for the trading bot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TradeDirection(Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"


class Chain(Enum):
    """Supported blockchain networks."""
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    ETHEREUM_SEPOLIA = "ethereum_sepolia"  # Sepolia testnet
    ETHEREUM_GOERLI = "ethereum_goerli"    # Goerli testnet
    BSC = "bsc"
    BASE = "base"
    ARBITRUM = "arbitrum"


class PositionStatus(Enum):
    """Status of a trading position."""
    PENDING = "pending"      # Waiting for limit entry price
    ACTIVE = "active"        # Position is open
    CLOSED_TP = "closed_tp"  # Closed at take profit
    CLOSED_SL = "closed_sl"  # Closed at stop loss
    CLOSED_MANUAL = "closed_manual"  # Manually closed
    FAILED = "failed"        # Failed to execute


@dataclass
class Signal:
    """Parsed trading signal from Telegram."""
    direction: TradeDirection
    pair_name: str
    contract_address: str
    entry_price: float
    take_profit: float
    stop_loss: float
    raw_message: str
    timestamp: datetime = field(default_factory=datetime.now)
    chain: Optional[Chain] = None
    
    def __post_init__(self):
        """Validate signal data."""
        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")
        if self.take_profit <= 0:
            raise ValueError("Take profit must be positive")
        if self.stop_loss <= 0:
            raise ValueError("Stop loss must be positive")
        
        # For LONG: TP > Entry > SL
        if self.direction == TradeDirection.LONG:
            if not (self.take_profit > self.entry_price > self.stop_loss):
                raise ValueError(
                    f"Invalid LONG signal: TP ({self.take_profit}) > "
                    f"Entry ({self.entry_price}) > SL ({self.stop_loss}) required"
                )
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk/reward ratio."""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0


@dataclass
class Position:
    """Active trading position."""
    id: Optional[int] = None
    signal: Signal = None
    chain: Chain = None
    token_address: str = ""
    quote_token: str = "USDT"
    
    # Amounts
    entry_amount_quote: float = 0  # Amount in USDT/USDC spent
    entry_amount_token: float = 0  # Amount of tokens received
    actual_entry_price: float = 0  # Actual fill price
    
    # Targets (from signal)
    target_entry_price: float = 0
    take_profit_price: float = 0
    stop_loss_price: float = 0
    
    # Status
    status: PositionStatus = PositionStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    # Transaction hashes
    entry_tx_hash: Optional[str] = None
    exit_tx_hash: Optional[str] = None
    
    # Result
    exit_price: Optional[float] = None
    pnl_percent: Optional[float] = None
    pnl_absolute: Optional[float] = None
    
    def calculate_pnl(self, exit_price: float) -> tuple[float, float]:
        """Calculate PnL for a given exit price."""
        if self.actual_entry_price <= 0:
            return 0, 0
        
        pnl_percent = ((exit_price - self.actual_entry_price) / self.actual_entry_price) * 100
        pnl_absolute = (exit_price - self.actual_entry_price) * self.entry_amount_token
        
        return pnl_percent, pnl_absolute


@dataclass
class TradeResult:
    """Result of a trade execution."""
    success: bool
    tx_hash: Optional[str] = None
    amount_in: float = 0
    amount_out: float = 0
    price: float = 0
    gas_used: float = 0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TokenInfo:
    """Information about a token."""
    address: str
    symbol: str
    name: str
    decimals: int
    chain: Chain
    price_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
