"""
Telegram Bot Handler - Handles button interactions via Bot API.
Works alongside Telethon user client for monitoring.
"""

import asyncio
from typing import Callable, Optional, Dict, Any

from telethon import TelegramClient, events, Button as TelethonButton
from telethon.tl.types import UpdateBotCallbackQuery
from telethon.errors import MessageNotModifiedError

from config import TelegramConfig
from utils.logger import get_logger
from utils.user_manager import get_user_manager, UserManager

logger = get_logger("bot_handler")


class BotHandler:
    """Handles bot interactions with inline buttons."""
    
    def __init__(self, bot_token: str, api_id: int, api_hash: str):
        self.bot_token = bot_token
        self.api_id = api_id
        self.api_hash = api_hash
        self.user_manager: Optional[UserManager] = None
        
        # Create bot client using Telethon with bot token
        self.bot = TelegramClient(
            'bot_session',
            api_id,
            api_hash
        )
        
        self.is_running = False
    
    async def start(self):
        """Start the bot client."""
        print("DEBUG BOT: Starting bot handler...")
        logger.info("Starting bot handler...")
        
        print("DEBUG BOT: Getting user manager...")
        self.user_manager = await get_user_manager()
        
        print("DEBUG BOT: Connecting bot to Telegram...")
        # Start as bot
        await self.bot.start(bot_token=self.bot_token)
        
        print("DEBUG BOT: Getting bot info...")
        me = await self.bot.get_me()
        logger.info(f"Bot started: @{me.username}")
        print(f"DEBUG BOT: Bot is @{me.username}")
        
        print("DEBUG BOT: Registering event handlers...")
        # Register handlers
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def handle_start(event):
            await self._cmd_start(event)
        
        @self.bot.on(events.NewMessage(pattern='/help'))
        async def handle_help(event):
            await self._cmd_help(event)
        
        @self.bot.on(events.NewMessage(pattern='/addwallet'))
        async def handle_addwallet(event):
            await self._cmd_addwallet(event)
        
        @self.bot.on(events.NewMessage(pattern='/removewallet'))
        async def handle_removewallet(event):
            await self._cmd_removewallet(event)
        
        @self.bot.on(events.CallbackQuery())
        async def handle_callback(event):
            await self._handle_callback(event)
        
        self.is_running = True
        print("DEBUG BOT: Bot handler ready!")
        logger.info("Bot handler ready!")
    
    async def run(self):
        """Run the bot (blocking)."""
        print("DEBUG BOT: Bot entering run loop...")
        await self.bot.run_until_disconnected()
    
    async def stop(self):
        """Stop the bot."""
        self.is_running = False
        await self.bot.disconnect()
    
    async def _cmd_start(self, event):
        """Handle /start command."""
        user_id = event.sender_id
        print(f"📥 /start from user {user_id}")
        
        user = await self.user_manager.get_user(user_id)
        if not user:
            user = await self.user_manager.register_user(user_id, event.sender.username)
        
        buttons = self._get_main_menu()
        if user.is_admin:
            buttons.append([TelethonButton.inline("👑 Admin", "menu_admin")])
        
        admin_msg = "\n👑 Admin" if user.is_admin else ""
        
        await event.reply(
            f"👋 **Trading Bot**{admin_msg}\n\n"
            f"Your ID: `{user_id}`\n\n"
            f"Use the buttons below:",
            parse_mode='md',
            buttons=buttons
        )
    
    async def _cmd_help(self, event):
        """Handle /help command."""
        print(f"📥 /help from user {event.sender_id}")
        await event.reply(
            "📖 **Commands**\n\n"
            "/start - Main menu with buttons\n"
            "/help - This help message\n"
            "/addwallet <chain> <key> - Add wallet\n"
            "/removewallet <chain> - Remove wallet\n\n"
            "**Chains:** `solana`, `evm`, `ethereum_sepolia`, `ethereum_goerli`, `ton`\n\n"
            "⚠️ Add wallets only in private DM!",
            parse_mode='md'
        )
    
    async def _cmd_addwallet(self, event):
        """Handle /addwallet command."""
        user_id = event.sender_id
        print(f"📥 /addwallet from user {user_id}")
        
        # Only in private chat
        if not event.is_private:
            await event.reply("⚠️ Use this command in private DM only!")
            return
        
        text = event.message.text or ""
        parts = text.split()
        
        if len(parts) < 3:
            await event.reply(
                "**Add Wallet**\n\n"
                "Usage: `/addwallet <chain> <key>`\n\n"
                "Chains:\n"
                "• `solana` - Solana wallet\n"
                "• `evm` - Works for ETH, BSC, Polygon, Base, Arbitrum, etc.\n"
                "• `ethereum_sepolia` - Ethereum Sepolia testnet\n"
                "• `ethereum_goerli` - Ethereum Goerli testnet (deprecated)\n"
                "• `ton` - TON wallet\n\n"
                "Example:\n`/addwallet evm 0x123...abc`",
                parse_mode='md'
            )
            return
        
        chain = parts[1].lower()
        key = parts[2]
        
        # Delete message for security
        try:
            await event.delete()
        except:
            pass
        
        if await self.user_manager.add_wallet(user_id, chain, key):
            await event.respond(f"✅ {chain.upper()} wallet added!\n🔐 Encrypted and stored.")
        else:
            await event.respond("❌ Invalid chain. Use: `solana`, `evm`, `ethereum_sepolia`, `ethereum_goerli`, or `ton`", parse_mode='md')
    
    async def _cmd_removewallet(self, event):
        """Handle /removewallet command."""
        user_id = event.sender_id
        print(f"📥 /removewallet from user {user_id}")
        text = event.message.text or ""
        parts = text.split()
        
        if len(parts) < 2:
            await event.reply("Usage: `/removewallet solana` or `evm` or `ton`", parse_mode='md')
            return
        
        chain = parts[1].lower()
        if await self.user_manager.remove_wallet(user_id, chain):
            await event.reply(f"✅ {chain.upper()} wallet removed")
        else:
            await event.reply(f"❌ No {chain} wallet found")
    
    def _get_main_menu(self):
        """Get main menu buttons."""
        return [
            [
                TelethonButton.inline("⚙️ Settings", "menu_settings"),
                TelethonButton.inline("👛 Wallets", "menu_wallets"),
            ],
            [
                TelethonButton.inline("📊 Stats", "menu_stats"),
                TelethonButton.inline("📍 Status", "menu_status"),
            ],
        ]
    
    async def _handle_callback(self, event):
        """Handle button callbacks."""
        user_id = event.sender_id
        data = event.data.decode('utf-8') if isinstance(event.data, bytes) else str(event.data)
        print(f"🔘 Button click: {data} from user {user_id}")
        
        user = await self.user_manager.get_user(user_id)
        if not user:
            user = await self.user_manager.register_user(user_id)
        
        try:
            await self._process_callback(event, data, user, user_id)
        except MessageNotModifiedError:
            # Message content is the same - just acknowledge the click
            await event.answer()
        except Exception as e:
            print(f"❌ Callback error: {e}")
            await event.answer("❌ Error occurred", alert=True)
    
    async def _process_callback(self, event, data, user, user_id):
        """Process callback data."""
        
        # Main Menu
        if data == "menu_main":
            buttons = self._get_main_menu()
            if user.is_admin:
                buttons.append([TelethonButton.inline("👑 Admin", "menu_admin")])
            await event.edit(
                f"📱 **Main Menu**\n\nID: `{user_id}`",
                parse_mode='md',
                buttons=buttons
            )
        
        # Settings
        elif data == "menu_settings":
            buttons = [
                [TelethonButton.inline(f"💰 Capital: {user.capital_percent*100:.0f}%", "change_capital")],
                [TelethonButton.inline(f"📊 Max Pos: {user.max_positions}", "change_maxpos")],
                [TelethonButton.inline(f"📉 Slip: {user.slippage_tolerance*100:.1f}%", "change_slippage")],
                [TelethonButton.inline(f"⚡ Leverage: {user.leverage}x", "change_leverage")],
                [TelethonButton.inline(f"🤖 Auto: {'ON' if user.auto_trade else 'OFF'}", "toggle_autotrade")],
                [TelethonButton.inline("⬅️ Back", "menu_main")],
            ]
            await event.edit(
                f"⚙️ **Settings**\n\n"
                f"💰 Capital: {user.capital_percent*100:.0f}%\n"
                f"📊 Max Positions: {user.max_positions}\n"
                f"📉 Slippage: {user.slippage_tolerance*100:.1f}%\n"
                f"⚡ Leverage: {user.leverage}x\n"
                f"🤖 Auto-Trade: {'ON' if user.auto_trade else 'OFF'}",
                parse_mode='md',
                buttons=buttons
            )
        
        # Capital selection
        elif data == "change_capital":
            buttons = [
                [TelethonButton.inline("1%", "cap_1"), TelethonButton.inline("3%", "cap_3"), TelethonButton.inline("5%", "cap_5")],
                [TelethonButton.inline("10%", "cap_10"), TelethonButton.inline("15%", "cap_15"), TelethonButton.inline("20%", "cap_20")],
                [TelethonButton.inline("⬅️ Back", "menu_settings")],
            ]
            await event.edit(f"💰 **Select Capital**\n\nCurrent: {user.capital_percent*100:.0f}%", parse_mode='md', buttons=buttons)
        
        elif data.startswith("cap_"):
            val = int(data.split("_")[1])
            await self.user_manager.update_user_setting(user_id, "capital_percent", val/100)
            await event.answer(f"✅ Capital: {val}%")
            # Refresh settings menu
            user = await self.user_manager.get_user(user_id)
            await self._show_settings_menu(event, user)
        
        # Max positions
        elif data == "change_maxpos":
            buttons = [
                [TelethonButton.inline("1", "pos_1"), TelethonButton.inline("2", "pos_2"), TelethonButton.inline("3", "pos_3")],
                [TelethonButton.inline("5", "pos_5"), TelethonButton.inline("10", "pos_10")],
                [TelethonButton.inline("⬅️ Back", "menu_settings")],
            ]
            await event.edit(f"📊 **Max Positions**\n\nCurrent: {user.max_positions}", parse_mode='md', buttons=buttons)
        
        elif data.startswith("pos_"):
            val = int(data.split("_")[1])
            await self.user_manager.update_user_setting(user_id, "max_positions", val)
            await event.answer(f"✅ Max: {val}")
            user = await self.user_manager.get_user(user_id)
            await self._show_settings_menu(event, user)
        
        # Slippage
        elif data == "change_slippage":
            buttons = [
                [TelethonButton.inline("0.5%", "slip_0.5"), TelethonButton.inline("1%", "slip_1"), TelethonButton.inline("2%", "slip_2")],
                [TelethonButton.inline("3%", "slip_3"), TelethonButton.inline("5%", "slip_5")],
                [TelethonButton.inline("⬅️ Back", "menu_settings")],
            ]
            await event.edit(f"📉 **Slippage**\n\nCurrent: {user.slippage_tolerance*100:.1f}%", parse_mode='md', buttons=buttons)
        
        elif data.startswith("slip_"):
            val = float(data.split("_")[1])
            await self.user_manager.update_user_setting(user_id, "slippage_tolerance", val/100)
            await event.answer(f"✅ Slippage: {val}%")
            user = await self.user_manager.get_user(user_id)
            await self._show_settings_menu(event, user)
        
        # Leverage selection
        elif data == "change_leverage":
            buttons = [
                [TelethonButton.inline("1x", "lev_1"), TelethonButton.inline("2x", "lev_2"), TelethonButton.inline("3x", "lev_3")],
                [TelethonButton.inline("5x", "lev_5"), TelethonButton.inline("10x", "lev_10"), TelethonButton.inline("20x", "lev_20")],
                [TelethonButton.inline("50x", "lev_50"), TelethonButton.inline("75x", "lev_75"), TelethonButton.inline("100x", "lev_100")],
                [TelethonButton.inline("⬅️ Back", "menu_settings")],
            ]
            await event.edit(f"⚡ **Leverage**\n\nCurrent: {user.leverage}x\n\n⚠️ Higher = Higher Risk!", parse_mode='md', buttons=buttons)
        
        elif data.startswith("lev_"):
            val = int(data.split("_")[1])
            await self.user_manager.update_user_setting(user_id, "leverage", val)
            await event.answer(f"✅ Leverage: {val}x")
            user = await self.user_manager.get_user(user_id)
            await self._show_settings_menu(event, user)
        
        # Toggle autotrade
        elif data == "toggle_autotrade":
            new_val = not user.auto_trade
            await self.user_manager.update_user_setting(user_id, "auto_trade", new_val)
            await event.answer(f"🤖 Auto: {'ON' if new_val else 'OFF'}")
            user = await self.user_manager.get_user(user_id)
            await self._show_settings_menu(event, user)
        
        # Wallets
        elif data == "menu_wallets":
            wallets = await self.user_manager.get_user_wallets(user_id)
            buttons = [
                [TelethonButton.inline(f"{'✅' if wallets['solana'] else '❌'} Solana", "w_solana")],
                [TelethonButton.inline(f"{'✅' if wallets['evm'] else '❌'} EVM (Mainnet)", "w_evm")],
                [TelethonButton.inline(f"{'✅' if wallets.get('ethereum_sepolia', False) else '❌'} Sepolia (Test)", "w_ethereum_sepolia")],
                [TelethonButton.inline(f"{'✅' if wallets.get('ethereum_goerli', False) else '❌'} Goerli (Test)", "w_ethereum_goerli")],
                [TelethonButton.inline(f"{'✅' if wallets['ton'] else '❌'} TON", "w_ton")],
                [TelethonButton.inline("⬅️ Back", "menu_main")],
            ]
            await event.edit(
                "👛 **Wallets**\n\nTap to manage.\nAdd: `/addwallet <chain> <key>`",
                parse_mode='md',
                buttons=buttons
            )
        
        elif data.startswith("w_"):
            chain = data.split("_")[1]
            has = await self.user_manager.has_wallet(user_id, chain)
            buttons = []
            if has:
                buttons.append([TelethonButton.inline("🗑️ Remove", f"rm_{chain}")])
            buttons.append([TelethonButton.inline("⬅️ Back", "menu_wallets")])
            
            if chain == "evm":
                info = "\n\nWorks for: ETH, BSC, Polygon, Base, Arbitrum, etc."
            elif chain == "ethereum_sepolia":
                info = "\n\nEthereum Sepolia testnet"
            elif chain == "ethereum_goerli":
                info = "\n\nEthereum Goerli testnet (deprecated)"
            else:
                info = ""
            await event.edit(
                f"👛 **{chain.upper()}**\n\n{'✅ Connected' if has else '❌ Not set'}{info}\n\nAdd: `/addwallet {chain} <key>`",
                parse_mode='md',
                buttons=buttons
            )
        
        elif data.startswith("rm_"):
            chain = data.split("_")[1]
            await self.user_manager.remove_wallet(user_id, chain)
            await event.answer(f"✅ {chain.upper()} removed")
            await self._show_wallets_menu(event, user_id)
        
        # Stats
        elif data == "menu_stats":
            stats = await self.user_manager.get_user_stats(user_id)
            wr = 0
            if stats["wins"] + stats["losses"] > 0:
                wr = stats["wins"] / (stats["wins"] + stats["losses"]) * 100
            buttons = [[TelethonButton.inline("⬅️ Back", "menu_main")]]
            await event.edit(
                f"📊 **Stats**\n\nTrades: {stats['total_trades']}\nWins: {stats['wins']} ✅\nLosses: {stats['losses']} ❌\nWin Rate: {wr:.1f}%\nPnL: ${stats['total_pnl']:.2f}",
                parse_mode='md',
                buttons=buttons
            )
        
        # Status
        elif data == "menu_status":
            mode = "🧪 DRY" if self.user_manager.dry_run else "🔴 LIVE"
            wallets = await self.user_manager.get_user_wallets(user_id)
            buttons = [[TelethonButton.inline("⬅️ Back", "menu_main")]]
            await event.edit(
                f"📍 **Status**\n\nMode: {mode}\nAuto: {'ON' if user.auto_trade else 'OFF'}\nCap: {user.capital_percent*100:.0f}%\n\nSOL {'✅' if wallets['solana'] else '❌'} | EVM {'✅' if wallets['evm'] else '❌'} | Sepolia {'✅' if wallets.get('ethereum_sepolia', False) else '❌'} | Goerli {'✅' if wallets.get('ethereum_goerli', False) else '❌'} | TON {'✅' if wallets['ton'] else '❌'}",
                parse_mode='md',
                buttons=buttons
            )
        
        # Admin
        elif data == "menu_admin":
            if not user.is_admin:
                await event.answer("❌ Admin only", alert=True)
                return
            buttons = [
                [TelethonButton.inline(f"Mode: {'🧪 DRY' if self.user_manager.dry_run else '🔴 LIVE'}", "toggle_dry")],
                [TelethonButton.inline("👥 Users", "admin_users")],
                [TelethonButton.inline("⬅️ Back", "menu_main")],
            ]
            await event.edit("👑 **Admin**", parse_mode='md', buttons=buttons)
        
        elif data == "toggle_dry":
            if not user.is_admin:
                return
            new_val = not self.user_manager.dry_run
            await self.user_manager.set_dry_run(new_val)
            await event.answer(f"Mode: {'DRY' if new_val else 'LIVE'}")
            await self._show_admin_menu(event)
        
        elif data == "admin_users":
            if not user.is_admin:
                return
            users = await self.user_manager.get_all_users()
            txt = f"👥 **Users ({len(users)})**\n\n"
            for u in users[:15]:
                txt += f"{'🤖' if u.auto_trade else '⏸️'} @{u.username or u.user_id}\n"
            if len(users) > 15:
                txt += f"...+{len(users)-15} more"
            buttons = [[TelethonButton.inline("⬅️ Back", "menu_admin")]]
            await event.edit(txt, parse_mode='md', buttons=buttons)
    
    async def _show_settings_menu(self, event, user):
        """Show settings menu."""
        buttons = [
            [TelethonButton.inline(f"💰 Capital: {user.capital_percent*100:.0f}%", "change_capital")],
            [TelethonButton.inline(f"📊 Max Pos: {user.max_positions}", "change_maxpos")],
            [TelethonButton.inline(f"📉 Slip: {user.slippage_tolerance*100:.1f}%", "change_slippage")],
            [TelethonButton.inline(f"⚡ Leverage: {user.leverage}x", "change_leverage")],
            [TelethonButton.inline(f"🤖 Auto: {'ON' if user.auto_trade else 'OFF'}", "toggle_autotrade")],
            [TelethonButton.inline("⬅️ Back", "menu_main")],
        ]
        await event.edit(
            f"⚙️ **Settings**\n\n"
            f"💰 Capital: {user.capital_percent*100:.0f}%\n"
            f"📊 Max Positions: {user.max_positions}\n"
            f"📉 Slippage: {user.slippage_tolerance*100:.1f}%\n"
            f"⚡ Leverage: {user.leverage}x\n"
            f"🤖 Auto-Trade: {'ON' if user.auto_trade else 'OFF'}",
            parse_mode='md',
            buttons=buttons
        )
    
    async def _show_wallets_menu(self, event, user_id):
        """Show wallets menu."""
        wallets = await self.user_manager.get_user_wallets(user_id)
        buttons = [
            [TelethonButton.inline(f"{'✅' if wallets['solana'] else '❌'} Solana", "w_solana")],
            [TelethonButton.inline(f"{'✅' if wallets['evm'] else '❌'} EVM (Mainnet)", "w_evm")],
            [TelethonButton.inline(f"{'✅' if wallets.get('ethereum_sepolia', False) else '❌'} Sepolia (Test)", "w_ethereum_sepolia")],
            [TelethonButton.inline(f"{'✅' if wallets.get('ethereum_goerli', False) else '❌'} Goerli (Test)", "w_ethereum_goerli")],
            [TelethonButton.inline(f"{'✅' if wallets['ton'] else '❌'} TON", "w_ton")],
            [TelethonButton.inline("⬅️ Back", "menu_main")],
        ]
        await event.edit(
            "👛 **Wallets**\n\nTap to manage.\nAdd: `/addwallet <chain> <key>`",
            parse_mode='md',
            buttons=buttons
        )
    
    async def _show_admin_menu(self, event):
        """Show admin menu."""
        buttons = [
            [TelethonButton.inline(f"Mode: {'🧪 DRY' if self.user_manager.dry_run else '🔴 LIVE'}", "toggle_dry")],
            [TelethonButton.inline("👥 Users", "admin_users")],
            [TelethonButton.inline("⬅️ Back", "menu_main")],
        ]
        await event.edit("👑 **Admin**", parse_mode='md', buttons=buttons)
