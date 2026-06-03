"""
LSPR EMA Cross Backtest — Cartesi dApp

Strategy: EMA 9/26 crossover on Binance Futures (LONG + SHORT)
Input:  JSON payload (hex-encoded) with params + optional klines
Output: Notice with backtest results
"""

from os import environ
import logging
import json
import requests

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

rollup_server = environ["ROLLUP_HTTP_SERVER_URL"]
logger.info(f"Rollup server: {rollup_server}")

FEE_RATE = 0.0004   # 0.04% taker per side


# ── Encoding helpers ──────────────────────────────────────────────────────────

def hex2str(h: str) -> str:
    return bytes.fromhex(h[2:]).decode("utf-8")

def str2hex(s: str) -> str:
    return "0x" + s.encode("utf-8").hex()


# ── EMA cross backtest ────────────────────────────────────────────────────────

def _ema(closes: list, period: int) -> list:
    k = 2 / (period + 1)
    result = [closes[0]]
    for c in closes[1:]:
        result.append(c * k + result[-1] * (1 - k))
    return result


def run_backtest(
    klines: list,
    leverage: int,
    margin: float,
    sl_pct: float,
    tp_pct: float,
) -> dict:
    closes = [float(k[4]) for k in klines]
    highs  = [float(k[2]) for k in klines]
    lows   = [float(k[3]) for k in klines]
    times  = [int(k[0]) for k in klines]

    ema9  = _ema(closes, 9)
    ema26 = _ema(closes, 26)
    liq_pct = 1.0 / leverage

    trades = []
    position = None   # {'dir': 'L'|'S', 'entry': float, 'qty': float, 'open_i': int}

    def close_pos(reason: str, exit_price: float, is_liq: bool = False):
        p = position
        qty = p["qty"]
        fee = (p["entry"] * qty + exit_price * qty) * FEE_RATE
        if p["dir"] == "L":
            pnl = (exit_price - p["entry"]) * qty - fee
        else:
            pnl = (p["entry"] - exit_price) * qty - fee
        if is_liq:
            pnl = -margin
        trades.append({
            "dir":     p["dir"],
            "entry":   round(p["entry"], 4),
            "exit":    round(exit_price, 4),
            "pnl":     round(pnl, 2),
            "liq":     is_liq,
            "reason":  reason,
            "open_ts": times[p["open_i"]],
            "close_ts": times[i],
        })

    for i in range(27, len(closes)):
        above_now  = ema9[i]   > ema26[i]
        above_prev = ema9[i-1] > ema26[i-1]
        price = closes[i]

        # Manage open position
        if position:
            e = position["entry"]
            if position["dir"] == "L":
                if lows[i] <= e * (1 - liq_pct):
                    close_pos("liq", e * (1 - liq_pct), is_liq=True); position = None
                elif lows[i] <= e * (1 - sl_pct):
                    close_pos("sl", e * (1 - sl_pct)); position = None
                elif highs[i] >= e * (1 + tp_pct):
                    close_pos("tp", e * (1 + tp_pct)); position = None
            else:
                if highs[i] >= e * (1 + liq_pct):
                    close_pos("liq", e * (1 + liq_pct), is_liq=True); position = None
                elif highs[i] >= e * (1 + sl_pct):
                    close_pos("sl", e * (1 + sl_pct)); position = None
                elif lows[i] <= e * (1 - tp_pct):
                    close_pos("tp", e * (1 - tp_pct)); position = None

        # Golden cross → LONG
        if not above_prev and above_now:
            if position and position["dir"] == "S":
                close_pos("cross", price); position = None
            if position is None:
                position = {"dir": "L", "entry": price,
                            "qty": margin * leverage / price, "open_i": i}

        # Death cross → SHORT
        elif above_prev and not above_now:
            if position and position["dir"] == "L":
                close_pos("cross", price); position = None
            if position is None:
                position = {"dir": "S", "entry": price,
                            "qty": margin * leverage / price, "open_i": i}

    # Close any remaining position at last candle
    if position:
        i = len(closes) - 1
        close_pos("end", closes[-1])

    total   = len(trades)
    wins    = sum(1 for t in trades if t["pnl"] > 0)
    liqs    = sum(1 for t in trades if t["liq"])
    tps     = sum(1 for t in trades if t["reason"] == "tp")
    sls     = sum(1 for t in trades if t["reason"] == "sl")
    net_pnl = round(sum(t["pnl"] for t in trades), 2)
    wr      = round(wins / total * 100, 1) if total else 0.0

    # Max drawdown
    balance = margin * 10
    peak = balance
    max_dd = 0.0
    for t in trades:
        balance += t["pnl"]
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return {
        "trades":  total,
        "wins":    wins,
        "liqs":    liqs,
        "tps":     tps,
        "sls":     sls,
        "wr_pct":  wr,
        "net_pnl": net_pnl,
        "max_dd_pct": round(max_dd, 1),
    }


# ── Request handlers ──────────────────────────────────────────────────────────

def handle_advance(data: dict) -> str:
    logger.info("Processing advance_state request")
    try:
        payload = json.loads(hex2str(data["payload"]))
        logger.info(f"Params: {list(payload.keys())}")

        symbol   = payload.get("symbol", "BTCUSDT").upper()
        if not symbol.endswith(("USDT", "BUSD")):
            symbol += "USDT"
        interval = payload.get("interval", "1h")
        days     = int(payload.get("days", 30))
        leverage = int(payload.get("leverage", 50))
        margin   = float(payload.get("margin", 100.0))
        sl_pct   = float(payload.get("sl_pct", 0.002))
        tp_pct   = float(payload.get("tp_pct", 0.005))

        # klines must be provided in the payload (Cartesi VM has no network access)
        klines = payload.get("klines")
        if not klines:
            raise ValueError(
                "Missing 'klines' in payload. "
                "Fetch klines off-chain with client.py --prefetch and embed them."
            )
        logger.info(f"Using {len(klines)} provided klines")

        result = run_backtest(klines, leverage, margin, sl_pct, tp_pct)
        result.update({
            "symbol":   symbol,
            "interval": interval,
            "days":     days,
            "leverage": leverage,
            "margin":   margin,
            "sl_pct":   sl_pct,
            "tp_pct":   tp_pct,
            "candles":  len(klines),
            "strategy": "EMA 9/26 Cross",
        })

        logger.info(f"Result: trades={result['trades']} wr={result['wr_pct']}% "
                    f"pnl=${result['net_pnl']}")

        requests.post(
            rollup_server + "/notice",
            json={"payload": str2hex(json.dumps(result))},
        )
        return "accept"

    except Exception as exc:
        logger.error(f"Error: {exc}", exc_info=True)
        requests.post(
            rollup_server + "/report",
            json={"payload": str2hex(json.dumps({"error": str(exc)}))},
        )
        return "reject"


def handle_inspect(data: dict) -> str:
    info = {
        "dapp":     "LSPR EMA Cross Backtest",
        "version":  "1.0.0",
        "strategy": "EMA 9/26 crossover, LONG + SHORT",
        "chain":    "Cartesi",
        "input_schema": {
            "symbol":   "str  (default: BTCUSDT)",
            "interval": "str  (default: 1h)",
            "days":     "int  (default: 30)",
            "leverage": "int  (default: 50)",
            "margin":   "float (default: 100.0)",
            "sl_pct":   "float (default: 0.002 = 0.2%)",
            "tp_pct":   "float (default: 0.005 = 0.5%)",
            "klines":   "list  (optional; if omitted, fetched from Binance)",
        },
    }
    requests.post(
        rollup_server + "/report",
        json={"payload": str2hex(json.dumps(info))},
    )
    return "accept"


# ── Main loop ─────────────────────────────────────────────────────────────────

handlers = {
    "advance_state": handle_advance,
    "inspect_state": handle_inspect,
}

finish = {"status": "accept"}
while True:
    response = requests.post(rollup_server + "/finish", json=finish)
    if response.status_code == 202:
        pass  # no pending input
    else:
        rollup_req = response.json()
        finish["status"] = handlers[rollup_req["request_type"]](rollup_req["data"])
