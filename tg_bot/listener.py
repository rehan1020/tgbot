"""
Telethon user client for monitoring private signal groups.
Handles signal detection and triggers trades.
"""

import asyncio
from typing import Callable, Optional

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat

from config import TelegramConfig
from tg_bot.signal_parser import SignalParser
from models import Signal
from utils.logger import get_logger
from utils.user_manager import get_user_manager, UserManager

logger = get_logger("telethon_client")


class TelethonListener:
    """Telethon user client for monitoring private groups."""
    
    def __init__(
        self,
        config: TelegramConfig,
        on_signal: Optional[Callable] = None,
    ):
        self.config = config
        self.on_signal = on_signal
        self.parser = SignalParser()
        self.user_manager: Optional[UserManager] = None
        
        self.client = TelegramClient(
            config.session_name,
            config.api_id,
            config.api_hash,
        )
        
        self.is_running = False
        self.my_user_id: Optional[int] = None
    
    async def start(self):
        """Start the Telethon client."""
        print("DEBUG USER: Starting user client...")
        logger.info("Starting user client...")
        
        print("DEBUG USER: Getting user manager...")
        self.user_manager = await get_user_manager()
        
        print("DEBUG USER: Setting target group...")
        if not self.user_manager.target_group:
            await self.user_manager.set_target_group(self.config.target_group)
        
        print("DEBUG USER: Connecting to Telegram...")
        # Connect and check auth
        await self.client.connect()
        
        print("DEBUG USER: Checking authorization...")
        if not await self.client.is_user_authorized():
            print("DEBUG USER: Not authorized, need login...")
            logger.info("Login required...")
            await self.client.start(
                phone=self.config.phone,
                password=lambda: self.config.password if self.config.password else None
            )
        else:
            print("DEBUG USER: Already authorized!")
            await self.client.start()
        
        print("DEBUG USER: Getting user info...")
        me = await self.client.get_me()
        self.my_user_id = me.id
        logger.info(f"Logged in as: {me.first_name} (@{me.username or 'no username'})")
        print(f"DEBUG USER: Logged in as {me.first_name}")
        
        print("DEBUG USER: Registering user...")
        await self.user_manager.register_user(self.my_user_id, me.username)
        
        # Load dialogs to cache entities
        print("DEBUG USER: Loading chats (15s timeout)...")
        logger.info("Loading chats...")
        try:
            dialogs = await asyncio.wait_for(
                self.client.get_dialogs(limit=100), 
                timeout=15.0
            )
            logger.info(f"Loaded {len(dialogs)} chats")
            print(f"DEBUG USER: Loaded {len(dialogs)} chats")
        except asyncio.TimeoutError:
            logger.warning("Loading chats timed out, continuing...")
            print("DEBUG USER: Timeout loading chats!")
            dialogs = []
        
        print("DEBUG USER: Setting up event handlers...")
        # Set up signal handler
        @self.client.on(events.NewMessage())
        async def handle_message(event):
            await self._handle_message(event)
        
        self.is_running = True
        
        print("DEBUG USER: Looking for target group...")
        # Find target group
        target_found = False
        for dialog in dialogs:
            if dialog.id == self.user_manager.target_group:
                logger.info(f"✅ Monitoring: {dialog.name} (ID: {dialog.id})")
                print(f"DEBUG USER: Found target group: {dialog.name}")
                target_found = True
                break
        
        if not target_found:
            logger.warning(f"⚠️ Target group {self.user_manager.target_group} not found in dialogs")
            print(f"DEBUG USER: Target group NOT found!")
        
        print("DEBUG USER: User client running! Waiting for disconnect...")
        logger.info("User client running - monitoring for signals...")
        
        await self.client.run_until_disconnected()
    
    async def stop(self):
        """Stop the client."""
        self.is_running = False
        if self.user_manager:
            await self.user_manager.close()
        await self.client.disconnect()
    
    async def _handle_message(self, event):
        """Handle incoming messages - only process signals from target group."""
        chat_id = event.chat_id
        text = event.message.text or ""
        
        if not text:
            return
        
        # Only process signals from target group
        if chat_id == self.user_manager.target_group:
            print(f"📨 Message from target group: {text[:50]}...")
            await self._handle_signal(event, text)
    
    async def _handle_signal(self, event, text):
        """Parse and process trading signals."""
        if not self.parser.is_signal_message(text):
            return
        
        signal = self.parser.parse(text)
        if not signal:
            return
        
        logger.info(f"📊 SIGNAL: {signal.pair_name} @ {signal.entry_price}")
        
        # Get users with auto-trade enabled
        auto_users = await self.user_manager.get_auto_trade_users()
        mode = "🧪 DRY RUN" if self.user_manager.dry_run else "🔴 LIVE"
        
        # Reply with signal info
        await event.reply(
            f"📊 **Signal Detected!** {mode}\n\n"
            f"**{signal.pair_name}**\n"
            f"Entry: `{signal.entry_price}`\n"
            f"TP: `{signal.take_profit}` (+{((signal.take_profit/signal.entry_price)-1)*100:.1f}%)\n"
            f"SL: `{signal.stop_loss}` ({((signal.stop_loss/signal.entry_price)-1)*100:.1f}%)\n"
            f"R/R: {signal.risk_reward_ratio:.2f}\n\n"
            f"👥 {len(auto_users)} users will auto-trade",
            parse_mode='md'
        )
        
        # Process for each auto-trade user
        if self.on_signal:
            for user in auto_users:
                try:
                    await self.on_signal(signal, user)
                except Exception as e:
                    logger.error(f"Signal error for {user.user_id}: {e}")


async def run_listener(config: TelegramConfig, on_signal: Callable):
    """Run the listener."""
    listener = TelethonListener(config, on_signal)
    await listener.start()
