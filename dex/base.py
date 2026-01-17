"""
Base class for DEX integrations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from models import Chain, TradeResult


@dataclass
class Quote:
    """Quote for a swap."""
    input_token: str
    output_token: str
    input_amount: float
    output_amount: float
    price: float  # Price of input in terms of output
    price_impact: float  # Price impact percentage
    route: str  # Human-readable route description
    raw_quote: dict  # Raw quote data from DEX


class BaseDEX(ABC):
    """Abstract base class for DEX integrations."""
    
    def __init__(self, chain: Chain, rpc_url: str, private_key: Optional[str] = None):
        """
        Initialize DEX integration.
        
        Args:
            chain: Blockchain network
            rpc_url: RPC endpoint URL
            private_key: Wallet private key for signing transactions
        """
        self.chain = chain
        self.rpc_url = rpc_url
        self.private_key = private_key
    
    @abstractmethod
    async def get_quote(
        self,
        input_token: str,
        output_token: str,
        amount: float,
        slippage: float = 0.01,
    ) -> Optional[Quote]:
        """
        Get a quote for a swap.
        
        Args:
            input_token: Input token address
            output_token: Output token address
            amount: Amount of input token
            slippage: Allowed slippage (0.01 = 1%)
            
        Returns:
            Quote if successful, None otherwise
        """
        pass
    
    @abstractmethod
    async def execute_swap(
        self,
        quote: Quote,
        dry_run: bool = False,
    ) -> TradeResult:
        """
        Execute a swap based on a quote.
        
        Args:
            quote: Quote from get_quote()
            dry_run: If True, simulate but don't execute
            
        Returns:
            TradeResult with execution details
        """
        pass
    
    @abstractmethod
    async def get_token_price(self, token_address: str) -> Optional[float]:
        """
        Get current price of a token in USD.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Price in USD if available, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_token_balance(self, token_address: str) -> float:
        """
        Get wallet balance of a token.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Balance amount
        """
        pass
    
    @abstractmethod
    async def get_native_balance(self) -> float:
        """
        Get native token balance (ETH, SOL, BNB, etc.).
        
        Returns:
            Native token balance
        """
        pass
