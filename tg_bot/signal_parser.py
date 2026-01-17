"""
Signal parser for extracting trading signals from Telegram messages.
"""

import re
from datetime import datetime
from typing import Optional, Tuple

from models import Signal, TradeDirection
from utils.logger import get_logger

logger = get_logger("signal_parser")


class SignalParser:
    """Parse trading signals from Telegram messages."""
    
    # Regex patterns for extracting signal components
    PATTERNS = {
        # Direction: {LONG} or {SHORT}
        "direction": re.compile(r'\{(LONG|SHORT)\}', re.IGNORECASE),
        
        # Pair name: $TOKEN/USDT or TOKEN/USDT
        "pair": re.compile(r'\$?([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)', re.IGNORECASE),
        
        # Contract address patterns
        # Solana: Base58, typically 32-44 chars
        "solana_address": re.compile(r'\b([1-9A-HJ-NP-Za-km-z]{32,44})\b'),
        
        # EVM: 0x followed by 40 hex chars
        "evm_address": re.compile(r'\b(0x[a-fA-F0-9]{40})\b'),
        
        # Entry price: LIMIT ENTRY: 0.03975 or Entry: 0.03975
        "entry_price": re.compile(
            r'(?:LIMIT\s*)?ENTRY[:\s]+([0-9]+\.?[0-9]*)',
            re.IGNORECASE
        ),
        
        # Take profit: TP: 0.04344 or Take Profit: 0.04344
        "take_profit": re.compile(
            r'(?:✅\s*)?(?:TAKE\s*PROFIT|TP)[:\s]+([0-9]+\.?[0-9]*)',
            re.IGNORECASE
        ),
        
        # Stop loss: SL: 0.03846 or Stop Loss: 0.03846
        "stop_loss": re.compile(
            r'(?:❌\s*)?(?:STOP\s*LOSS|SL)[:\s]+([0-9]+\.?[0-9]*)',
            re.IGNORECASE
        ),
        
        # Alternative: CA: or Contract: prefix
        "ca_prefix": re.compile(
            r'(?:CA|CONTRACT|ADDRESS)[:\s]+([A-Za-z0-9]+)',
            re.IGNORECASE
        ),
    }
    
    def __init__(self):
        """Initialize the signal parser."""
        self.last_parsed_signal: Optional[Signal] = None
    
    def parse(self, message: str) -> Optional[Signal]:
        """
        Parse a message and extract trading signal.
        
        Args:
            message: Raw message text from Telegram
            
        Returns:
            Signal object if valid signal found, None otherwise
        """
        # Check for test signal first
        test_signal = self.parse_test_signal(message)
        if test_signal:
            return test_signal
        
        try:
            # Extract direction
            direction = self._extract_direction(message)
            if not direction:
                logger.debug("No direction found in message")
                return None
            
            # Only process LONG signals (spot trading)
            if direction == TradeDirection.SHORT:
                logger.info("SHORT signal detected - skipping (spot trading only)")
                return None
            
            # Extract pair name
            pair_name = self._extract_pair_name(message)
            if not pair_name:
                logger.debug("No pair name found in message")
                return None
            
            # Extract contract address
            contract_address = self._extract_contract_address(message)
            if not contract_address:
                logger.warning(f"No contract address found for {pair_name}")
                return None
            
            # Extract prices
            entry_price = self._extract_price(message, "entry_price")
            take_profit = self._extract_price(message, "take_profit")
            stop_loss = self._extract_price(message, "stop_loss")
            
            if not all([entry_price, take_profit, stop_loss]):
                logger.warning(
                    f"Missing prices - Entry: {entry_price}, "
                    f"TP: {take_profit}, SL: {stop_loss}"
                )
                return None
            
            # Create and validate signal
            signal = Signal(
                direction=direction,
                pair_name=pair_name,
                contract_address=contract_address,
                entry_price=entry_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                raw_message=message,
                timestamp=datetime.now(),
            )
            
            self.last_parsed_signal = signal
            logger.info(
                f"✅ Parsed signal: {pair_name} | "
                f"Entry: {entry_price} | TP: {take_profit} | SL: {stop_loss}"
            )
            
            return signal
            
        except ValueError as e:
            logger.error(f"Invalid signal data: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing signal: {e}")
            return None
    
    def _extract_direction(self, message: str) -> Optional[TradeDirection]:
        """Extract trade direction from message."""
        match = self.PATTERNS["direction"].search(message)
        if match:
            direction_str = match.group(1).upper()
            return TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        return None
    
    def _extract_pair_name(self, message: str) -> Optional[str]:
        """Extract trading pair name from message."""
        match = self.PATTERNS["pair"].search(message)
        if match:
            token = match.group(1).upper()
            quote = match.group(2).upper()
            return f"{token}/{quote}"
        return None
    
    def _extract_contract_address(self, message: str) -> Optional[str]:
        """Extract contract address from message."""
        # First try explicit CA: prefix
        match = self.PATTERNS["ca_prefix"].search(message)
        if match:
            addr = match.group(1)
            # Validate it's a proper address
            if self._is_valid_address(addr):
                return addr
        
        # Try EVM address (0x...)
        match = self.PATTERNS["evm_address"].search(message)
        if match:
            return match.group(1)
        
        # Try Solana address (base58)
        match = self.PATTERNS["solana_address"].search(message)
        if match:
            addr = match.group(1)
            # Exclude common false positives
            if self._is_likely_solana_address(addr):
                return addr
        
        return None
    
    def _extract_price(self, message: str, price_type: str) -> Optional[float]:
        """Extract a price value from message."""
        match = self.PATTERNS[price_type].search(message)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    
    def _is_valid_address(self, addr: str) -> bool:
        """Check if address looks valid."""
        # EVM
        if addr.startswith("0x") and len(addr) == 42:
            return all(c in "0123456789abcdefABCDEF" for c in addr[2:])
        # Solana (base58)
        if 32 <= len(addr) <= 44:
            base58_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
            return all(c in base58_chars for c in addr)
        return False
    
    def _is_likely_solana_address(self, addr: str) -> bool:
        """
        Check if a base58 string is likely a Solana address.
        Filter out common false positives.
        """
        if len(addr) < 32 or len(addr) > 44:
            return False
        
        # Check for base58 characters only
        base58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        if not all(c in base58_chars for c in addr):
            return False
        
        # Filter out common words that might match
        common_words = {
            "LONG", "SHORT", "ENTRY", "LIMIT", "USDT", "USDC",
            "PROFIT", "LOSS", "CRYPTO", "TRADE", "TOKEN"
        }
        if addr.upper() in common_words:
            return False
        
        return True
    
    def is_signal_message(self, message: str) -> bool:
        """
        Quick check if a message might be a trading signal.
        Used to filter messages before full parsing.
        """
        # Check for test signal
        if self._is_test_signal(message):
            return True
        
        # Must have direction indicator
        if not self.PATTERNS["direction"].search(message):
            return False
        
        # Must have at least entry price
        if not self.PATTERNS["entry_price"].search(message):
            return False
        
        return True
    
    def _is_test_signal(self, message: str) -> bool:
        """Check if this is a test signal message."""
        test_patterns = [
            re.compile(r'\bTEST\s+SIGNAL\b', re.IGNORECASE),
            re.compile(r'\bTEST\s+BUY\b', re.IGNORECASE),
            re.compile(r'\bTEST\s+LONG\b', re.IGNORECASE),
            re.compile(r'\bSIGNAL\s+TEST\b', re.IGNORECASE),
        ]
        return any(pattern.search(message) for pattern in test_patterns)
    
    def parse_test_signal(self, message: str) -> Optional[Signal]:
        """Parse a test signal with predefined values for testing purposes."""
        if not self._is_test_signal(message):
            return None
        
        # Default test values
        test_values = {
            "pair_name": "TEST/USDT",
            "contract_address": "0x5a3C7Abb3E5a7EAc2Ca421E20E691EfC885D7D37",  # Test address
            "entry_price": 0.1,
            "take_profit": 0.12,  # 20% gain
            "stop_loss": 0.09,    # 10% loss
        }
        
        # Try to extract pair name if specified
        pair_match = self.PATTERNS["pair"].search(message)
        if pair_match:
            token = pair_match.group(1).upper()
            quote = pair_match.group(2).upper()
            test_values["pair_name"] = f"{token}/{quote}"
        
        # Try to extract custom prices
        entry_match = self.PATTERNS["entry_price"].search(message)
        if entry_match:
            try:
                test_values["entry_price"] = float(entry_match.group(1))
                test_values["take_profit"] = test_values["entry_price"] * 1.2  # 20% gain
                test_values["stop_loss"] = test_values["entry_price"] * 0.9   # 10% loss
            except ValueError:
                pass
        
        # Create test signal
        signal = Signal(
            direction=TradeDirection.LONG,
            pair_name=test_values["pair_name"],
            contract_address=test_values["contract_address"],
            entry_price=test_values["entry_price"],
            take_profit=test_values["take_profit"],
            stop_loss=test_values["stop_loss"],
            raw_message=message,
            timestamp=datetime.now(),
        )
        
        logger.info(f"✅ Parsed TEST signal: {signal.pair_name} | Entry: {signal.entry_price} | TP: {signal.take_profit} | SL: {signal.stop_loss}")
        
        self.last_parsed_signal = signal
        return signal


def parse_signal(message: str) -> Optional[Signal]:
    """Convenience function to parse a signal."""
    parser = SignalParser()
    return parser.parse(message)
