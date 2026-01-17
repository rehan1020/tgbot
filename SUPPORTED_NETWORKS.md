# 🚀 Supported Networks

## Total: 11 Blockchains

### 🟣 Solana Ecosystem
- **Solana** (Mainnet)
  - DEX: Jupiter, Raydium
  - Wallet: 1 Solana wallet

---

### 🔷 EVM Ecosystem (1 wallet works for all!)

#### Layer 1 Chains:
- **Ethereum** (ETH)
  - DEXes: Uniswap, SushiSwap, 1inch
  - Chain ID: 1

- **BNB Smart Chain** (BSC)
  - DEXes: PancakeSwap, BiSwap
  - Chain ID: 56

- **Polygon** (MATIC)
  - DEXes: QuickSwap, SushiSwap
  - Chain ID: 137

- **Avalanche** (AVAX)  
  - DEXes: Trader Joe, Pangolin
  - Chain ID: 43114

- **Ronin** (RON)
  - DEXes: Katana DEX
  - Chain ID: 2020
  - Used for: Axie Infinity ecosystem

#### Layer 2 Chains:
- **Base** (Coinbase L2)
  - DEXes: BaseSwap, Aerodrome
  - Chain ID: 8453

- **Arbitrum** (ARB)
  - DEXes: Uniswap, SushiSwap, Camelot
  - Chain ID: 42161

- **Optimism** (OP)
  - DEXes: Uniswap, Velodrome
  - Chain ID: 10

**One EVM private key = access to ALL 8 EVM chains above!**

---

### 💎 TON Ecosystem
- **TON** (The Open Network)
  - DEXes: DeDust, STON.fi
  - Wallet: Separate TON wallet required

---

## 📊 Summary

| Wallet Type | Command | Chains Supported | Count |
|-------------|---------|------------------|-------|
| **Solana** | `/addwallet solana <key>` | Solana | 1 |
| **EVM** | `/addwallet evm <key>` | ETH, BSC, Polygon, Avalanche, Base, Arbitrum, Optimism, Ronin | 8 |
| **TON** | `/addwallet ton <key>` | TON | 1 |
| **TOTAL** | 3 wallets needed | **11 blockchains** | **11** |

---

## 🌐 RPC Endpoints (Public & Free)

All chains come with **FREE public RPCs** out of the box:
- ✅ No setup required
- ✅ Works immediately
- ✅ No API keys needed

**Optional:** Add premium RPCs in `.env` for faster speeds.

---

## 💰 Wrapped Assets

Can also trade wrapped versions:
- **WBTC** (Wrapped Bitcoin) on all EVM chains
- **WETH** (Wrapped ETH) on all EVM chains  
- **WDOGE** (Wrapped Dogecoin) on EVM chains
- Bridge assets between chains

---

## 🎯 What's NOT Supported

| Asset | Why |
|-------|-----|
| Native Bitcoin (BTC) | No DEXes/smart contracts |
| Native Dogecoin (DOGE) | No DEXes/smart contracts |
| Cardano (ADA) | Different architecture (coming soon?) |
| Ripple (XRP) | No DEXes |

**Use wrapped versions** (WBTC, WDOGE) on EVM chains instead!
