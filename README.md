# Universal Trading Strategy Backtesting
### Powered by Cartesi | Verifiable On-Chain Results

> Any technical indicator. Any exchange.  
> Any strategy. Results verified on Ethereum.

## Live Deployment

| | |
|---|---|
| **Network** | Ethereum Sepolia (testnet) |
| **Contract** | `0x704cA61F80eD64C466714b709bf3ABC579b14a75` |
| **Strategy** | EMA 9/26 Cross (LONG + SHORT) |
| **Status** | ✅ Live |

## What is this?

A backtesting engine for trading strategies deployed as a Cartesi dApp.

Results are computed inside a Linux VM and verified on Ethereum —
nobody can fake or manipulate them.

Think: Bloomberg Terminal for AI agents, but trustless and on-chain.

## How it works

```
User sends params
        ↓
Ethereum Sepolia (InputBox contract)
        ↓
Cartesi Node (VPS)
        ↓
Linux VM (Python) runs EMA backtest
        ↓
Result → on-chain Notice (verifiable by anyone)
```

## Current Strategy: EMA 9/26 Cross

Entry signals:
```
→ Golden Cross (EMA9 crosses EMA26 upward)   = LONG
→ Death Cross  (EMA9 crosses EMA26 downward) = SHORT
```

Parameters:
```
→ Symbol:    any Binance Futures pair
→ Interval:  1h, 4h, 1d
→ Days:      1-30 (limited by tx size)
→ Leverage:  configurable
→ SL / TP:   configurable
```

## Run it yourself

Install dependencies:
```bash
pip install requests eth-account
```

Send a backtest request:
```bash
python client.py \
  --symbol BTCUSDT \
  --interval 1h \
  --days 7 \
  --leverage 10 \
  --sl-pct 0.01 \
  --tp-pct 0.02 \
  --prefetch
```

Example response (on-chain Notice):
```json
{
  "symbol":     "BTCUSDT",
  "strategy":   "EMA 9/26 Cross",
  "trades":     12,
  "wr_pct":     58.3,
  "net_pnl":    145.32,
  "max_dd_pct": 8.1,
  "candles":    168
}
```

## Architecture

```
client.py   ← fetches klines off-chain, builds hex payload, sends tx
dapp.py     ← Python backtest logic running inside Cartesi RISC-V VM
Dockerfile  ← RISC-V build for Cartesi Machine
```

## Roadmap

- [x] EMA 9/26 Cross backtest
- [x] Deployed on Ethereum Sepolia
- [x] Verifiable on-chain results
- [ ] RSI signal
- [ ] MACD signal
- [ ] Funding Rate signal
- [ ] MA Cross (any periods)
- [ ] Multi-exchange (Hyperliquid)
- [ ] x402 pay-per-use monetization
- [ ] Mainnet deployment

## Why Cartesi?

**Traditional backtesting:**
```
→ Results on centralized server
→ Anyone can manipulate them
→ "Trust me bro"
```

**Cartesi backtesting:**
```
→ Results computed in Linux VM
→ Verified by Ethereum
→ Mathematically trustless
```

## Tech Stack

- Python 3.12
- Cartesi Rollups v2.0
- Ethereum Sepolia
- Binance Futures API

## Contact

Interested in integration or grants?  
→ Open an issue on GitHub

*Full source available in this repository*
