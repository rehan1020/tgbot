"""
Settings manager for runtime configuration.
Allows changing settings via Telegram bot commands.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from utils.logger import get_logger

logger = get_logger("settings")

SETTINGS_FILE = "bot_settings.json"
KEYS_FILE = "wallet_keys.enc"


@dataclass
class RuntimeSettings:
    """Runtime-configurable settings."""
    capital_percent: float = 0.05
    max_positions: int = 1
    slippage_tolerance: float = 0.01
    price_check_interval: int = 10
    dry_run: bool = True
    target_group: Optional[int] = None
    admin_user_id: Optional[int] = None  # Only this user can change settings


class SettingsManager:
    """Manage bot settings with persistence."""
    
    def __init__(self, data_dir: str = "."):
        """
        Initialize settings manager.
        
        Args:
            data_dir: Directory to store settings files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.settings_path = self.data_dir / SETTINGS_FILE
        self.keys_path = self.data_dir / KEYS_FILE
        
        # Generate or load encryption key
        self._encryption_key = self._get_encryption_key()
        
        # Load settings
        self.settings = self._load_settings()
        self.wallets: Dict[str, str] = {}
        self._load_wallets()
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key for wallet storage."""
        key_file = self.data_dir / ".key"
        
        if key_file.exists():
            return key_file.read_bytes()
        else:
            # Generate new key
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            # Make it less visible
            if os.name != 'nt':  # Unix
                os.chmod(key_file, 0o600)
            return key
    
    def _load_settings(self) -> RuntimeSettings:
        """Load settings from file."""
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text())
                return RuntimeSettings(**data)
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
        
        return RuntimeSettings()
    
    def _save_settings(self):
        """Save settings to file."""
        try:
            data = asdict(self.settings)
            self.settings_path.write_text(json.dumps(data, indent=2))
            logger.info("Settings saved")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    def _load_wallets(self):
        """Load encrypted wallet keys."""
        if self.keys_path.exists():
            try:
                fernet = Fernet(self._encryption_key)
                encrypted = self.keys_path.read_bytes()
                decrypted = fernet.decrypt(encrypted)
                self.wallets = json.loads(decrypted.decode())
            except Exception as e:
                logger.error(f"Error loading wallets: {e}")
                self.wallets = {}
    
    def _save_wallets(self):
        """Save encrypted wallet keys."""
        try:
            fernet = Fernet(self._encryption_key)
            data = json.dumps(self.wallets).encode()
            encrypted = fernet.encrypt(data)
            self.keys_path.write_bytes(encrypted)
            logger.info("Wallets saved (encrypted)")
        except Exception as e:
            logger.error(f"Error saving wallets: {e}")
    
    # Settings getters/setters
    
    def get_capital_percent(self) -> float:
        return self.settings.capital_percent
    
    def set_capital_percent(self, value: float) -> bool:
        if 0.01 <= value <= 1.0:  # 1% to 100%
            self.settings.capital_percent = value
            self._save_settings()
            return True
        return False
    
    def get_max_positions(self) -> int:
        return self.settings.max_positions
    
    def set_max_positions(self, value: int) -> bool:
        if 1 <= value <= 10:
            self.settings.max_positions = value
            self._save_settings()
            return True
        return False
    
    def get_slippage(self) -> float:
        return self.settings.slippage_tolerance
    
    def set_slippage(self, value: float) -> bool:
        if 0.001 <= value <= 0.5:  # 0.1% to 50%
            self.settings.slippage_tolerance = value
            self._save_settings()
            return True
        return False
    
    def get_dry_run(self) -> bool:
        return self.settings.dry_run
    
    def set_dry_run(self, value: bool):
        self.settings.dry_run = value
        self._save_settings()
    
    def get_target_group(self) -> Optional[int]:
        return self.settings.target_group
    
    def set_target_group(self, value: int):
        self.settings.target_group = value
        self._save_settings()
    
    def get_admin_user_id(self) -> Optional[int]:
        return self.settings.admin_user_id
    
    def set_admin_user_id(self, value: int):
        self.settings.admin_user_id = value
        self._save_settings()
    
    # Wallet management
    
    def add_wallet(self, chain: str, private_key: str) -> bool:
        """
        Add or update a wallet.
        
        Args:
            chain: 'solana' or 'evm'
            private_key: Private key string
            
        Returns:
            True if successful
        """
        chain = chain.lower()
        if chain not in ['solana', 'evm']:
            return False
        
        # Basic validation
        if chain == 'solana':
            # Base58 format, 32-88 chars
            if not (32 <= len(private_key) <= 88):
                return False
        else:  # evm
            # Hex format, optionally with 0x prefix
            if private_key.startswith('0x'):
                private_key = private_key[2:]
            if len(private_key) != 64:
                return False
        
        self.wallets[chain] = private_key
        self._save_wallets()
        return True
    
    def get_wallet(self, chain: str) -> Optional[str]:
        """Get wallet private key for a chain."""
        return self.wallets.get(chain.lower())
    
    def has_wallet(self, chain: str) -> bool:
        """Check if wallet exists for chain."""
        return chain.lower() in self.wallets
    
    def remove_wallet(self, chain: str) -> bool:
        """Remove a wallet."""
        chain = chain.lower()
        if chain in self.wallets:
            del self.wallets[chain]
            self._save_wallets()
            return True
        return False
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings as dict."""
        return {
            "capital_percent": f"{self.settings.capital_percent * 100:.1f}%",
            "max_positions": self.settings.max_positions,
            "slippage": f"{self.settings.slippage_tolerance * 100:.1f}%",
            "price_check_interval": f"{self.settings.price_check_interval}s",
            "dry_run": self.settings.dry_run,
            "target_group": self.settings.target_group,
            "wallets": {
                "solana": "✅ Set" if self.has_wallet("solana") else "❌ Not set",
                "evm": "✅ Set" if self.has_wallet("evm") else "❌ Not set",
            }
        }


# Global instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
