# LSPR EMA Cross Backtest — Cartesi dApp

Verifiable on-chain backtesting of an EMA 9/26 crossover strategy on Binance Futures.

Built on [Cartesi](https://cartesi.io) — results are reproducible and verifiable by any node.

---

## Strategy

**EMA 9/26 Cross** on any Binance Futures perpetual:

- **Golden cross** (EMA9 > EMA26) → LONG
- **Death cross** (EMA9 < EMA26) → SHORT
- Exits: Take Profit / Stop Loss / Liquidation / Opposite cross

Metrics returned: trades, win rate, net P&L, max drawdown, TP/SL/liq counts.

---

## Prerequisites

- [Node.js](https://nodejs.org) 18+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with RISC-V emulation
- [Cartesi CLI](https://docs.cartesi.io/cartesi-rollups/1.5/development/installation/) v1.5+
- Python 3.10+ (for client.py)

```bash
npm install -g @cartesi/cli
```

---

## Run locally

### 1. Build the Cartesi machine

```bash
cd lspr-cartesi
cartesi build
```

Compiles a RISC-V Docker image. Takes 5–15 min on first run.

### 2. Start the local node

```bash
cartesi run
```

Starts a local Ethereum devnet + Cartesi node. Keep this terminal open.

### 3. Send a backtest request

**Option A — Cartesi CLI (interactive):**
```bash
cartesi send
```
Choose "Send generic input", paste JSON:
```json
{"symbol":"BTCUSDT","interval":"1h","days":30,"leverage":50,"margin":100}
```

**Option B — Python client:**
```bash
# Demo mode (dApp fetches klines internally)
python client.py --symbol BTCUSDT --interval 1h --days 30 --leverage 50

# Deterministic mode (klines embedded in payload, fully verifiable)
python client.py --symbol BTCUSDT --prefetch

# Dry run (print hex payload only)
python client.py --dry-run
```

### 4. Read the result

```bash
# GraphQL explorer
open http://localhost:8080/graphql
```

Query notices:
```graphql
{ notices { edges { node { payload } } } }
```

---

## Input schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `symbol` | string | `BTCUSDT` | Binance Futures symbol |
| `interval` | string | `1h` | Candle interval: `1m` `5m` `15m` `1h` `4h` `1d` |
| `days` | int | `30` | Historical lookback window |
| `leverage` | int | `50` | Leverage multiplier (1–125) |
| `margin` | float | `100.0` | Margin per trade in USDT |
| `sl_pct` | float | `0.002` | Stop loss fraction (0.2%) |
| `tp_pct` | float | `0.005` | Take profit fraction (0.5%) |
| `klines` | array | `null` | Pre-fetched klines (deterministic mode) |

---

## Output (Notice payload — hex-decoded JSON)

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "leverage": 50,
  "margin": 100.0,
  "candles": 720,
  "strategy": "EMA 9/26 Cross",
  "trades": 14,
  "wins": 9,
  "tps": 5,
  "sls": 4,
  "liqs": 0,
  "wr_pct": 64.3,
  "net_pnl": 187.50,
  "max_dd_pct": 12.4
}
```

---

## Deploy to testnet (Base Sepolia)

1. Get test ETH: [faucet.base.org](https://faucet.base.org)
2. Create `.env`:
```env
MNEMONIC="your twelve word mnemonic phrase here ..."
```
3. Deploy:
```bash
cartesi deploy --network base-sepolia
```

This deploys the Cartesi contracts and registers your machine hash on-chain.

---

## Architecture

```
[client.py]
    │  hex-encoded JSON params
    ▼
[Cartesi InputBox — on-chain]
    │
    ▼
[Cartesi Node — RISC-V VM]
    │  dapp.py: fetch klines → run EMA backtest
    ▼
[Notice: JSON result — on-chain, verifiable]
```

The backtest runs inside a deterministic RISC-V VM. Any Cartesi node can replay the computation and verify the result.

---

## Project structure

```
lspr-cartesi/
├── dapp.py          # Cartesi dApp: EMA backtest + rollup protocol handler
├── client.py        # Off-chain helper: build payload + send to node
├── Dockerfile       # RISC-V build (cartesi/python:3.10-slim-jammy base)
├── requirements.txt # requests==2.31.0
└── README.md
```
