"""
LSPR Cartesi dApp — off-chain client

Usage:
  # Quick test with default params (fetches live from Binance inside dApp)
  python client.py

  # Custom params
  python client.py --symbol ETHUSDT --interval 4h --days 14 --leverage 20

  # Pre-fetch klines and embed in payload (deterministic/verifiable mode)
  python client.py --prefetch --symbol BTCUSDT --interval 1h --days 7

  # Just print the hex payload (then paste into `cartesi send`)
  python client.py --dry-run
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta


BINANCE_API = "https://fapi.binance.com"


def fetch_klines(symbol: str, interval: str, days: int) -> list:
    """Fetch klines from Binance (for --prefetch mode)."""
    end_ms   = int(time.time() * 1000)
    start_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    all_k = []
    print(f"  Fetching {symbol} {interval} {days}d klines from Binance...", end="", flush=True)
    while start_ms < end_ms:
        url = (f"{BINANCE_API}/fapi/v1/klines?symbol={symbol}&interval={interval}"
               f"&startTime={start_ms}&limit=1500")
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        if not data:
            break
        all_k.extend(data)
        start_ms = data[-1][0] + 1
        if len(data) < 1500:
            break
    print(f" {len(all_k)} candles")
    return all_k


def str2hex(s: str) -> str:
    return "0x" + s.encode("utf-8").hex()


def hex2str(h: str) -> str:
    return bytes.fromhex(h[2:]).decode("utf-8")


def send_input(hex_payload: str) -> None:
    """Send hex payload via cartesi send CLI."""
    cmd = ["cartesi", "send", "dapp", "--payload", hex_payload]
    print(f"\nRunning: {' '.join(cmd[:3])} --payload {hex_payload[:40]}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"ERROR: cartesi send exited with code {result.returncode}", file=sys.stderr)
        print("Make sure `cartesi run` is active in another terminal.", file=sys.stderr)
    else:
        print("Input sent successfully.")


def main():
    ap = argparse.ArgumentParser(description="LSPR Cartesi dApp client")
    ap.add_argument("--symbol",    default="BTCUSDT")
    ap.add_argument("--interval",  default="1h")
    ap.add_argument("--days",      type=int,   default=30)
    ap.add_argument("--leverage",  type=int,   default=50)
    ap.add_argument("--margin",    type=float, default=100.0)
    ap.add_argument("--sl-pct",    type=float, default=0.002,
                    help="Stop loss fraction (default 0.002 = 0.2%%)")
    ap.add_argument("--tp-pct",    type=float, default=0.005,
                    help="Take profit fraction (default 0.005 = 0.5%%)")
    ap.add_argument("--prefetch",  action="store_true",
                    help="Fetch klines here and embed in payload (deterministic mode)")
    ap.add_argument("--dry-run",   action="store_true",
                    help="Print hex payload only, do not send")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    if not symbol.endswith(("USDT", "BUSD")):
        symbol += "USDT"

    payload: dict = {
        "symbol":   symbol,
        "interval": args.interval,
        "days":     args.days,
        "leverage": args.leverage,
        "margin":   args.margin,
        "sl_pct":   args.sl_pct,
        "tp_pct":   args.tp_pct,
    }

    if args.prefetch:
        payload["klines"] = fetch_klines(symbol, args.interval, args.days)

    hex_payload = str2hex(json.dumps(payload))

    print("\n=== LSPR Cartesi Client ===")
    print(f"Symbol:   {symbol}")
    print(f"Interval: {args.interval}  Days: {args.days}")
    print(f"Leverage: {args.leverage}x  Margin: ${args.margin}")
    print(f"SL: {args.sl_pct*100:.2f}%  TP: {args.tp_pct*100:.2f}%")
    if args.prefetch:
        print(f"Klines:   {len(payload['klines'])} candles embedded (deterministic mode)")
    else:
        print("Klines:   fetched live by dApp (demo mode)")
    print(f"\nPayload ({len(hex_payload)} hex chars):")
    print(f"  {hex_payload[:80]}...")

    if args.dry_run:
        print("\n-- Dry run. Run cartesi send manually:")
        print(f"cartesi send dapp --payload {hex_payload}")
        return

    send_input(hex_payload)


if __name__ == "__main__":
    main()
