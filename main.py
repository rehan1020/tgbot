"""
Telegram Signal Trading Bot - Hybrid Mode
User client monitors groups + Bot handles button interactions.
"""

import asyncio
import os
import sys
from typing import Optional

from config import load_config, Config
from models import Signal
from tg_bot.listener import TelethonListener
from tg_bot.bot_handler import BotHandler
from utils.logger import setup_logger, get_logger, TradeLogger
from utils.user_manager import get_user_manager, UserSettings


class TradingBot:
    """Main trading bot - runs user client + bot."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("bot")
        self.trade_logger = TradeLogger()
        
        self.user_client: Optional[TelethonListener] = None
        self.bot_handler: Optional[BotHandler] = None
        self.is_running = False
    
    async def start(self):
        """Start both user client and bot."""
        print("DEBUG: Starting bot...")
        self.logger.info("="*50)
        self.logger.info("  TELEGRAM TRADING BOT")
        self.logger.info("="*50)
        
        print("DEBUG: Getting user manager...")
        user_manager = await get_user_manager()
        
        if user_manager.dry_run:
            self.logger.warning("⚠️  DRY RUN MODE")
        else:
            self.logger.warning("🔴 LIVE MODE")
        
        print(f"DEBUG: Target group: {user_manager.target_group}")
        self.logger.info(f"Target group: {user_manager.target_group}")
        
        # Check for bot token
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        print(f"DEBUG: Bot token found: {bool(bot_token)}")
        
        # Create user client for monitoring
        print("DEBUG: Creating user client...")
        self.user_client = TelethonListener(
            config=self.config.telegram,
            on_signal=self._on_signal,
        )
        
        self.is_running = True
        
        if bot_token:
            # Hybrid mode: run both
            print("DEBUG: Hybrid mode - starting both clients...")
            self.logger.info("✅ Bot token found - buttons enabled!")
            self.bot_handler = BotHandler(
                bot_token=bot_token,
                api_id=self.config.telegram.api_id,
                api_hash=self.config.telegram.api_hash,
            )
            
            # Start both concurrently
            print("DEBUG: Starting concurrent clients...")
            await asyncio.gather(
                self._run_user_client(),
                self._run_bot(),
            )
        else:
            # User client only mode
            print("DEBUG: User client only mode...")
            self.logger.warning("⚠️ No TELEGRAM_BOT_TOKEN - buttons disabled")
            self.logger.info("Add bot token to .env to enable buttons")
            await self.user_client.start()
    
    async def _run_user_client(self):
        """Run user client."""
        try:
            await self.user_client.start()
        except Exception as e:
            self.logger.error(f"User client error: {e}")
    
    async def _run_bot(self):
        """Run bot handler."""
        try:
            await self.bot_handler.start()
            await self.bot_handler.run()
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
    
    async def stop(self):
        """Stop everything."""
        self.logger.info("Shutting down...")
        self.is_running = False
        
        if self.user_client:
            await self.user_client.stop()
        if self.bot_handler:
            await self.bot_handler.stop()
        
        self.logger.info("Bot stopped")
    
    async def _on_signal(self, signal: Signal, user: UserSettings):
        """Handle signal for a user."""
        self.logger.info(f"Processing signal for user {user.user_id}: {signal.pair_name}")
        
        self.trade_logger.log_signal({
            "user_id": user.user_id,
            "pair": signal.pair_name,
            "entry": signal.entry_price,
            "tp": signal.take_profit,
            "sl": signal.stop_loss,
            "address": signal.contract_address,
        })
        
        user_manager = await get_user_manager()
        
        # Check max positions
        pos_count = await user_manager.count_user_positions(user.user_id)
        if pos_count >= user.max_positions:
            self.logger.warning(f"User {user.user_id} at max positions")
            return
        
        self.logger.info(
            f"[SIGNAL] User {user.user_id}: {signal.pair_name} @ {signal.entry_price}"
        )


async def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1].lower() == "help":
        print("""
Telegram Trading Bot (Hybrid Mode)

Usage:
    python main.py      Start the bot
    python main.py help Show this help

Setup:
    1. Get API credentials from https://my.telegram.org
    2. Create a bot via @BotFather (for buttons)
    3. Edit .env with both credentials
    4. Run: python main.py
        """)
        return
    
    # Load config
    try:
        config = load_config()
    except ValueError as e:
        print(f"Config error: {e}")
        print("\nEdit .env with your Telegram API credentials.")
        sys.exit(1)
    
    # Setup logging
    setup_logger(
        name="trading_bot",
        level=config.log_level,
        log_file=config.log_file,
    )
    
    # Create and start bot
    bot = TradingBot(config)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        await bot.stop()
    except Exception as e:
        get_logger("main").error(f"Fatal error: {e}")
        await bot.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
