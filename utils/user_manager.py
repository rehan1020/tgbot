"""
Multi-user manager for handling per-user settings, wallets, and positions.
"""

import json
import os
import aiosqlite
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime
from cryptography.fernet import Fernet

from utils.logger import get_logger

logger = get_logger("user_manager")

DATABASE_FILE = "users.db"


@dataclass
class UserSettings:
    """Per-user settings."""
    user_id: int
    username: Optional[str] = None
    capital_percent: float = 0.05  # 5%
    max_positions: int = 1
    slippage_tolerance: float = 0.01  # 1%
    leverage: int = 1  # 1x, 2x, 5x, 10x, etc.
    auto_trade: bool = True  # Auto-trade on signals
    is_admin: bool = False
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class UserManager:
    """Manage multiple users with their own settings and wallets."""
    
    def __init__(self, data_dir: str = "."):
        """
        Initialize user manager.
        
        Args:
            data_dir: Directory to store database
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.data_dir / DATABASE_FILE
        self.db: Optional[aiosqlite.Connection] = None
        
        # Encryption for wallet keys
        self._encryption_key = self._get_encryption_key()
        self._fernet = Fernet(self._encryption_key)
        
        # Global settings
        self.target_group: Optional[int] = None
        self.dry_run: bool = True
        self.price_check_interval: int = 10
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key."""
        key_file = self.data_dir / ".key"
        
        if key_file.exists():
            return key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            return key
    
    async def initialize(self):
        """Initialize the database."""
        self.db = await aiosqlite.connect(self.db_path)
        
        # Create users table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                capital_percent REAL DEFAULT 0.05,
                max_positions INTEGER DEFAULT 1,
                slippage_tolerance REAL DEFAULT 0.01,
                leverage INTEGER DEFAULT 1,
                auto_trade INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        
        # Add leverage column if it doesn't exist (migration)
        try:
            await self.db.execute("ALTER TABLE users ADD COLUMN leverage INTEGER DEFAULT 1")
            await self.db.commit()
        except:
            pass  # Column already exists
        
        # Create wallets table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                encrypted_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, chain),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Create positions table (per-user)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                token_address TEXT NOT NULL,
                pair_name TEXT,
                entry_amount_quote REAL DEFAULT 0,
                entry_amount_token REAL DEFAULT 0,
                actual_entry_price REAL DEFAULT 0,
                target_entry_price REAL NOT NULL,
                take_profit_price REAL NOT NULL,
                stop_loss_price REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                opened_at TEXT,
                closed_at TEXT,
                entry_tx_hash TEXT,
                exit_tx_hash TEXT,
                exit_price REAL,
                pnl_percent REAL,
                pnl_absolute REAL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Create global settings table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        await self.db.commit()
        
        # Load global settings
        await self._load_global_settings()
        
        logger.info("User manager initialized")
    
    async def _load_global_settings(self):
        """Load global settings from database."""
        cursor = await self.db.execute("SELECT key, value FROM global_settings")
        rows = await cursor.fetchall()
        
        for key, value in rows:
            if key == "target_group":
                self.target_group = int(value) if value else None
            elif key == "dry_run":
                self.dry_run = value.lower() == "true"
            elif key == "price_check_interval":
                self.price_check_interval = int(value)
    
    async def _save_global_setting(self, key: str, value: str):
        """Save a global setting."""
        await self.db.execute(
            "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await self.db.commit()
    
    async def close(self):
        """Close database connection."""
        if self.db:
            await self.db.close()
    
    # ============ User Management ============
    
    async def register_user(self, user_id: int, username: Optional[str] = None) -> UserSettings:
        """Register a new user or get existing."""
        existing = await self.get_user(user_id)
        if existing:
            return existing
        
        # Check if this is the first user (make them admin)
        cursor = await self.db.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        is_admin = count == 0
        
        settings = UserSettings(
            user_id=user_id,
            username=username,
            is_admin=is_admin,
        )
        
        await self.db.execute(
            """
            INSERT INTO users (user_id, username, capital_percent, max_positions, 
                             slippage_tolerance, leverage, auto_trade, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, settings.capital_percent, settings.max_positions,
             settings.slippage_tolerance, settings.leverage, 1 if settings.auto_trade else 0,
             1 if is_admin else 0, settings.created_at)
        )
        await self.db.commit()
        
        logger.info(f"User registered: {user_id} (admin: {is_admin})")
        return settings
    
    async def get_user(self, user_id: int) -> Optional[UserSettings]:
        """Get user settings."""
        cursor = await self.db.execute(
            """SELECT user_id, username, capital_percent, max_positions, 
                      slippage_tolerance, leverage, auto_trade, is_admin, created_at 
               FROM users WHERE user_id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return UserSettings(
            user_id=row[0],
            username=row[1],
            capital_percent=row[2] or 0.05,
            max_positions=row[3] or 1,
            slippage_tolerance=row[4] or 0.01,
            leverage=row[5] or 1,
            auto_trade=bool(row[6]) if row[6] is not None else True,
            is_admin=bool(row[7]) if row[7] is not None else False,
            created_at=row[8] or "",
        )
    
    async def update_user_setting(self, user_id: int, key: str, value: Any) -> bool:
        """Update a user setting."""
        valid_keys = ["capital_percent", "max_positions", "slippage_tolerance", "leverage", "auto_trade"]
        if key not in valid_keys:
            return False
        
        if key == "auto_trade":
            value = 1 if value else 0
        
        await self.db.execute(
            f"UPDATE users SET {key} = ? WHERE user_id = ?",
            (value, user_id)
        )
        await self.db.commit()
        return True
    
    async def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        user = await self.get_user(user_id)
        return user and user.is_admin
    
    async def get_all_users(self) -> List[UserSettings]:
        """Get all registered users."""
        cursor = await self.db.execute(
            """SELECT user_id, username, capital_percent, max_positions, 
                      slippage_tolerance, leverage, auto_trade, is_admin, created_at 
               FROM users"""
        )
        rows = await cursor.fetchall()
        
        return [
            UserSettings(
                user_id=row[0],
                username=row[1],
                capital_percent=row[2] or 0.05,
                max_positions=row[3] or 1,
                slippage_tolerance=row[4] or 0.01,
                leverage=row[5] or 1,
                auto_trade=bool(row[6]) if row[6] is not None else True,
                is_admin=bool(row[7]) if row[7] is not None else False,
                created_at=row[8] or "",
            )
            for row in rows
        ]
    
    async def get_auto_trade_users(self) -> List[UserSettings]:
        """Get users with auto-trade enabled."""
        cursor = await self.db.execute(
            """SELECT user_id, username, capital_percent, max_positions, 
                      slippage_tolerance, leverage, auto_trade, is_admin, created_at 
               FROM users WHERE auto_trade = 1"""
        )
        rows = await cursor.fetchall()
        
        return [
            UserSettings(
                user_id=row[0],
                username=row[1],
                capital_percent=row[2] or 0.05,
                max_positions=row[3] or 1,
                slippage_tolerance=row[4] or 0.01,
                leverage=row[5] or 1,
                auto_trade=True,
                is_admin=bool(row[7]) if row[7] is not None else False,
                created_at=row[8] or "",
            )
            for row in rows
        ]
    
    # ============ Wallet Management ============
    
    async def add_wallet(self, user_id: int, chain: str, private_key: str) -> bool:
        """Add or update a user's wallet."""
        chain = chain.lower()
        # Support mainnet and testnet chains
        supported_chains = ["solana", "evm", "ton", "ethereum_sepolia", "ethereum_goerli"]
        if chain not in supported_chains:
            return False
        
        # Encrypt the key
        encrypted = self._fernet.encrypt(private_key.encode()).decode()
        
        await self.db.execute(
            """
            INSERT OR REPLACE INTO wallets (user_id, chain, encrypted_key, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, chain, encrypted, datetime.now().isoformat())
        )
        await self.db.commit()
        
        logger.info(f"Wallet added for user {user_id}: {chain}")
        return True
    
    async def get_wallet(self, user_id: int, chain: str) -> Optional[str]:
        """Get user's wallet private key (decrypted)."""
        cursor = await self.db.execute(
            "SELECT encrypted_key FROM wallets WHERE user_id = ? AND chain = ?",
            (user_id, chain.lower())
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        # Decrypt
        return self._fernet.decrypt(row[0].encode()).decode()
    
    async def has_wallet(self, user_id: int, chain: str) -> bool:
        """Check if user has a wallet for the chain."""
        cursor = await self.db.execute(
            "SELECT 1 FROM wallets WHERE user_id = ? AND chain = ?",
            (user_id, chain.lower())
        )
        return await cursor.fetchone() is not None
    
    async def remove_wallet(self, user_id: int, chain: str) -> bool:
        """Remove a user's wallet."""
        cursor = await self.db.execute(
            "DELETE FROM wallets WHERE user_id = ? AND chain = ?",
            (user_id, chain.lower())
        )
        await self.db.commit()
        return cursor.rowcount > 0
    
    async def get_user_wallets(self, user_id: int) -> Dict[str, bool]:
        """Get which wallets a user has."""
        cursor = await self.db.execute(
            "SELECT chain FROM wallets WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        
        return {
            "solana": any(r[0] == "solana" for r in rows),
            "evm": any(r[0] == "evm" for r in rows),
            "ton": any(r[0] == "ton" for r in rows),
            "ethereum_sepolia": any(r[0] == "ethereum_sepolia" for r in rows),
            "ethereum_goerli": any(r[0] == "ethereum_goerli" for r in rows),
        }
    
    # ============ Global Settings ============
    
    async def set_target_group(self, group_id: int):
        """Set target group."""
        self.target_group = group_id
        await self._save_global_setting("target_group", str(group_id))
    
    async def set_dry_run(self, value: bool):
        """Set dry run mode."""
        self.dry_run = value
        await self._save_global_setting("dry_run", str(value).lower())
    
    async def set_price_check_interval(self, seconds: int):
        """Set price check interval."""
        self.price_check_interval = seconds
        await self._save_global_setting("price_check_interval", str(seconds))
    
    # ============ Position Management ============
    
    async def count_user_positions(self, user_id: int) -> int:
        """Count active positions for a user."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM user_positions WHERE user_id = ? AND status IN ('pending', 'active')",
            (user_id,)
        )
        return (await cursor.fetchone())[0]
    
    async def create_position(
        self,
        user_id: int,
        chain: str,
        token_address: str,
        pair_name: str,
        target_entry: float,
        take_profit: float,
        stop_loss: float,
    ) -> int:
        """Create a new position for a user."""
        cursor = await self.db.execute(
            """
            INSERT INTO user_positions (
                user_id, chain, token_address, pair_name,
                target_entry_price, take_profit_price, stop_loss_price,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (user_id, chain, token_address, pair_name,
             target_entry, take_profit, stop_loss, datetime.now().isoformat())
        )
        await self.db.commit()
        return cursor.lastrowid
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get trading stats for a user."""
        cursor = await self.db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'closed_tp' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'closed_sl' THEN 1 ELSE 0 END) as losses,
                SUM(pnl_absolute) as total_pnl
            FROM user_positions WHERE user_id = ?
            """,
            (user_id,)
        )
        row = await cursor.fetchone()
        
        return {
            "total_trades": row[0] or 0,
            "wins": row[1] or 0,
            "losses": row[2] or 0,
            "total_pnl": row[3] or 0,
        }


# Global instance
_user_manager: Optional[UserManager] = None


async def get_user_manager() -> UserManager:
    """Get the global user manager instance."""
    global _user_manager
    if _user_manager is None:
        _user_manager = UserManager()
        await _user_manager.initialize()
    return _user_manager
