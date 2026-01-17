# Telegram Signal Trading Bot (Multi-User)

A multi-chain trading bot for groups where each user can trade with their own wallets.

## Features

- 👥 **Multi-User** - Each user has own settings & wallets
- 🤖 **Auto-Trade Toggle** - Users can enable/disable
- 🔐 **Encrypted Wallets** - Secure storage per user
- 🔗 **Multi-Chain** - Solana, ETH, BSC, Base, Arbitrum
- 📊 **Per-User Stats** - Track individual performance

## Quick Start

### 1. Create Bot
1. Message `@BotFather` on Telegram
2. Send `/newbot` and follow prompts
3. Copy your bot token

### 2. Configure
```bash
copy .env.example .env
# Edit .env and add your bot token:
# TELEGRAM_BOT_TOKEN=your_token_here
```

### 3. Run
```bash
pip install -r requirements.txt
python main.py
```

### 4. Setup in Telegram
1. Add bot to your signal group
2. Send `/setgroup` to set it as target
3. Users send `/start` to register

## User Commands

| Command | Description |
|---------|-------------|
| `/start` | Register with bot |
| `/settings` | View your settings |
| `/setcapital 5` | Set trade size (5%) |
| `/setmaxpos 2` | Max concurrent trades |
| `/autotrade on/off` | Enable/disable trading |
| `/wallets` | View wallet status |
| `/addwallet solana <key>` | Add wallet (DM only) |
| `/mystats` | Your trading stats |

## Admin Commands
| `/setgroup` | Set signal group |
| `/dryrun on/off` | Toggle live mode |
| `/users` | List all users |

## How It Works

```
Signal Posted → Bot Parses
     ↓
Users with auto-trade ON
     ↓ (for each user)
Check their wallet → Execute with their settings
     ↓
Monitor SL/TP → Auto-exit
```

## Project Structure
```
tgbot/
├── main.py           # Entry point
├── config.py         # Configuration
├── tg_bot/
│   ├── listener.py   # Bot commands
│   └── signal_parser.py
├── utils/
│   ├── user_manager.py  # Multi-user DB
│   └── logger.py
├── dex/              # DEX integrations
└── chain/            # Chain detection
```
