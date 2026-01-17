"""
Position manager for tracking and managing open trades.
Monitors prices and executes SL/TP orders.
"""

import asyncio
import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any

from config import Config, QUOTE_TOKENS
from models import Signal, Position, PositionStatus, Chain, TradeResult
from chain.detector import ChainDetector
from dex.base import BaseDEX
from dex.jupiter import JupiterDEX
from dex.oneinch import OneInchDEX, get_oneinch_for_chain
from utils.logger import get_logger

logger = get_logger("position_manager")


class PositionManager:
    """Manage trading positions with SL/TP monitoring."""
    
    def __init__(
        self,
        config: Config,
        db_path: str = "positions.db",
    ):
        """
        Initialize position manager.
        
        Args:
            config: Bot configuration
            db_path: Path to SQLite database
        """
        self.config = config
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
        
        # DEX instances
        self.dex_instances: Dict[Chain, BaseDEX] = {}
        
        # Chain detector
        self.chain_detector = ChainDetector()
        
        # Monitoring state
        self.is_monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self.on_position_opened: Optional[Callable] = None
        self.on_position_closed: Optional[Callable] = None
    
    async def initialize(self):
        """Initialize the position manager."""
        # Initialize database
        await self._init_database()
        
        # Initialize DEX instances
        await self._init_dex_instances()
        
        logger.info("Position manager initialized")
    
    async def _init_database(self):
        """Initialize SQLite database for position tracking."""
        self.db = await aiosqlite.connect(self.db_path)
        
        # Create positions table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                token_address TEXT NOT NULL,
                pair_name TEXT,
                quote_token TEXT DEFAULT 'USDT',
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
                raw_signal TEXT
            )
        """)
        
        await self.db.commit()
        logger.info(f"Database initialized: {self.db_path}")
    
    async def _init_dex_instances(self):
        """Initialize DEX instances for each chain."""
        # Solana (Jupiter)
        if self.config.wallet.solana_private_key:
            self.dex_instances[Chain.SOLANA] = JupiterDEX(
                rpc_url=self.config.rpc.solana,
                private_key=self.config.wallet.solana_private_key,
            )
            logger.info("Jupiter DEX initialized for Solana")
        
        # EVM chains (1inch)
        if self.config.wallet.evm_private_key:
            for chain in [Chain.ETHEREUM, Chain.ETHEREUM_SEPOLIA, Chain.ETHEREUM_GOERLI, Chain.BSC, Chain.BASE, Chain.ARBITRUM]:
                dex = get_oneinch_for_chain(
                    chain=chain,
                    rpc_config=self.config.rpc,
                    private_key=self.config.wallet.evm_private_key,
                )
                if dex:
                    self.dex_instances[chain] = dex
                    logger.info(f"1inch DEX initialized for {chain.value}")
    
    async def close(self):
        """Close connections."""
        self.is_monitoring = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        for dex in self.dex_instances.values():
            await dex.close()
        
        await self.chain_detector.close()
        
        if self.db:
            await self.db.close()
    
    async def process_signal(self, signal: Signal) -> Optional[Position]:
        """
        Process a trading signal.
        
        Args:
            signal: Parsed trading signal
            
        Returns:
            Created position if successful
        """
        # Check max positions
        active_count = await self._count_active_positions()
        if active_count >= self.config.trading.max_positions:
            logger.warning(
                f"Max positions ({self.config.trading.max_positions}) reached. "
                f"Ignoring signal for {signal.pair_name}"
            )
            return None
        
        # Detect chain
        chain = await self.chain_detector.detect_chain(signal.contract_address)
        if not chain:
            logger.error(f"Could not detect chain for {signal.contract_address}")
            return None
        
        signal.chain = chain
        
        # Check if we have DEX for this chain
        if chain not in self.dex_instances:
            logger.error(f"No DEX configured for chain {chain.value}")
            return None
        
        # Create position
        position = Position(
            signal=signal,
            chain=chain,
            token_address=signal.contract_address,
            target_entry_price=signal.entry_price,
            take_profit_price=signal.take_profit,
            stop_loss_price=signal.stop_loss,
            status=PositionStatus.PENDING,
        )
        
        # Save to database
        position.id = await self._save_position(position, signal)
        
        logger.info(
            f"📋 Position created: {signal.pair_name} on {chain.value} | "
            f"Entry: {signal.entry_price} | TP: {signal.take_profit} | SL: {signal.stop_loss}"
        )
        
        return position
    
    async def _save_position(self, position: Position, signal: Signal) -> int:
        """Save position to database."""
        cursor = await self.db.execute(
            """
            INSERT INTO positions (
                chain, token_address, pair_name, quote_token,
                target_entry_price, take_profit_price, stop_loss_price,
                status, created_at, raw_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position.chain.value,
                position.token_address,
                signal.pair_name,
                position.quote_token,
                position.target_entry_price,
                position.take_profit_price,
                position.stop_loss_price,
                position.status.value,
                datetime.now().isoformat(),
                signal.raw_message,
            )
        )
        await self.db.commit()
        return cursor.lastrowid
    
    async def _count_active_positions(self) -> int:
        """Count active and pending positions."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM positions WHERE status IN ('pending', 'active')"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    
    async def start_monitoring(self):
        """Start the price monitoring loop."""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Position monitoring started")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                # Get all pending and active positions
                positions = await self._get_open_positions()
                
                for position_data in positions:
                    await self._check_position(position_data)
                
                # Wait before next check
                await asyncio.sleep(self.config.trading.price_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(5)
    
    async def _get_open_positions(self) -> List[Dict]:
        """Get all pending and active positions."""
        cursor = await self.db.execute(
            """
            SELECT id, chain, token_address, pair_name, quote_token,
                   entry_amount_token, actual_entry_price,
                   target_entry_price, take_profit_price, stop_loss_price,
                   status
            FROM positions
            WHERE status IN ('pending', 'active')
            """
        )
        
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        
        return [dict(zip(columns, row)) for row in rows]
    
    async def _check_position(self, pos_data: Dict):
        """Check a single position and take action if needed."""
        position_id = pos_data["id"]
        chain = Chain(pos_data["chain"])
        token_address = pos_data["token_address"]
        status = pos_data["status"]
        
        dex = self.dex_instances.get(chain)
        if not dex:
            return
        
        # Get current price
        current_price = await dex.get_token_price(token_address)
        if not current_price:
            logger.debug(f"Could not get price for {token_address}")
            return
        
        if status == "pending":
            # Check if we should enter the position
            target_entry = pos_data["target_entry_price"]
            
            # For LONG: enter when price <= target
            if current_price <= target_entry:
                logger.info(
                    f"🎯 Entry price hit! {pos_data['pair_name']} @ {current_price:.6f} "
                    f"(target: {target_entry:.6f})"
                )
                await self._execute_entry(position_id, pos_data, dex, current_price)
        
        elif status == "active":
            # Check SL/TP
            take_profit = pos_data["take_profit_price"]
            stop_loss = pos_data["stop_loss_price"]
            
            if current_price >= take_profit:
                logger.info(
                    f"✅ Take profit hit! {pos_data['pair_name']} @ {current_price:.6f}"
                )
                await self._execute_exit(
                    position_id, pos_data, dex, current_price, "tp"
                )
            
            elif current_price <= stop_loss:
                logger.info(
                    f"🛑 Stop loss hit! {pos_data['pair_name']} @ {current_price:.6f}"
                )
                await self._execute_exit(
                    position_id, pos_data, dex, current_price, "sl"
                )
    
    async def _execute_entry(
        self,
        position_id: int,
        pos_data: Dict,
        dex: BaseDEX,
        current_price: float,
    ):
        """Execute entry trade."""
        chain = Chain(pos_data["chain"])
        token_address = pos_data["token_address"]
        
        # Calculate trade size (5% of quote token balance)
        quote_token = QUOTE_TOKENS.get(chain.value, {}).get("USDT")
        if not quote_token:
            logger.error(f"No quote token for chain {chain.value}")
            return
        
        balance = await dex.get_token_balance(quote_token)
        trade_amount = balance * self.config.trading.capital_percent
        
        if trade_amount <= 0:
            logger.error(f"Insufficient balance for trade")
            return
        
        logger.info(f"Executing entry: {trade_amount:.2f} USDT → {pos_data['pair_name']}")
        
        # Get quote
        quote = await dex.get_quote(
            input_token=quote_token,
            output_token=token_address,
            amount=trade_amount,
            slippage=self.config.trading.slippage_tolerance,
        )
        
        if not quote:
            logger.error("Failed to get quote for entry")
            return
        
        # Execute swap
        result = await dex.execute_swap(
            quote=quote,
            dry_run=self.config.trading.dry_run,
        )
        
        if result.success:
            # Update position
            await self.db.execute(
                """
                UPDATE positions
                SET status = 'active',
                    entry_amount_quote = ?,
                    entry_amount_token = ?,
                    actual_entry_price = ?,
                    opened_at = ?,
                    entry_tx_hash = ?
                WHERE id = ?
                """,
                (
                    trade_amount,
                    result.amount_out,
                    result.price,
                    datetime.now().isoformat(),
                    result.tx_hash,
                    position_id,
                )
            )
            await self.db.commit()
            
            logger.info(
                f"✅ Entry executed: {result.amount_out:.4f} tokens @ {result.price:.6f}"
            )
            
            if self.on_position_opened:
                await self.on_position_opened(pos_data, result)
        else:
            logger.error(f"Entry failed: {result.error}")
    
    async def _execute_exit(
        self,
        position_id: int,
        pos_data: Dict,
        dex: BaseDEX,
        current_price: float,
        exit_type: str,  # "tp" or "sl"
    ):
        """Execute exit trade."""
        chain = Chain(pos_data["chain"])
        token_address = pos_data["token_address"]
        token_amount = pos_data["entry_amount_token"]
        
        if not token_amount or token_amount <= 0:
            logger.error("No tokens to sell")
            return
        
        # Get quote token
        quote_token = QUOTE_TOKENS.get(chain.value, {}).get("USDT")
        if not quote_token:
            logger.error(f"No quote token for chain {chain.value}")
            return
        
        logger.info(f"Executing exit ({exit_type}): {token_amount:.4f} tokens → USDT")
        
        # Get quote
        quote = await dex.get_quote(
            input_token=token_address,
            output_token=quote_token,
            amount=token_amount,
            slippage=self.config.trading.slippage_tolerance,
        )
        
        if not quote:
            logger.error("Failed to get quote for exit")
            return
        
        # Execute swap
        result = await dex.execute_swap(
            quote=quote,
            dry_run=self.config.trading.dry_run,
        )
        
        if result.success:
            # Calculate PnL
            entry_price = pos_data["actual_entry_price"]
            pnl_percent = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            pnl_absolute = result.amount_out - pos_data.get("entry_amount_quote", 0)
            
            status = "closed_tp" if exit_type == "tp" else "closed_sl"
            
            # Update position
            await self.db.execute(
                """
                UPDATE positions
                SET status = ?,
                    closed_at = ?,
                    exit_tx_hash = ?,
                    exit_price = ?,
                    pnl_percent = ?,
                    pnl_absolute = ?
                WHERE id = ?
                """,
                (
                    status,
                    datetime.now().isoformat(),
                    result.tx_hash,
                    current_price,
                    pnl_percent,
                    pnl_absolute,
                    position_id,
                )
            )
            await self.db.commit()
            
            emoji = "🎉" if exit_type == "tp" else "💔"
            logger.info(
                f"{emoji} Exit executed: {result.amount_out:.2f} USDT | "
                f"PnL: {pnl_percent:+.2f}% (${pnl_absolute:+.2f})"
            )
            
            if self.on_position_closed:
                await self.on_position_closed(pos_data, result, pnl_percent)
        else:
            logger.error(f"Exit failed: {result.error}")
    
    async def get_position_stats(self) -> Dict:
        """Get statistics about positions."""
        cursor = await self.db.execute(
            """
            SELECT 
                status,
                COUNT(*) as count,
                SUM(pnl_absolute) as total_pnl
            FROM positions
            GROUP BY status
            """
        )
        
        rows = await cursor.fetchall()
        
        stats = {
            "pending": 0,
            "active": 0,
            "closed_tp": 0,
            "closed_sl": 0,
            "total_pnl": 0,
        }
        
        for row in rows:
            status, count, pnl = row
            stats[status] = count
            if pnl:
                stats["total_pnl"] += pnl
        
        return stats
