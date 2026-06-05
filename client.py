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

Reads from .env (same directory):
  MNEMONIC=<twelve word phrase>
  SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
  DAPP_ADDRESS=0x704cA61F80eD64C466714b709bf3ABC579b14a75
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path


BINANCE_API  = "https://fapi.binance.com"
CHAIN_ID     = "11155111"  # Sepolia
DEFAULT_RPC  = "https://sepolia.drpc.org"
DEFAULT_DAPP = "0x704cA61F80eD64C466714b709bf3ABC579b14a75"
INPUTBOX     = "0x59b22D57D4f067708AB0c00552767405926dc768"


def load_env() -> dict:
    """Load .env (or the first *.env file) from the same directory as this script."""
    env: dict = {}
    base = Path(__file__).parent
    # prefer a literal .env, otherwise pick any *.env file
    candidate = base / ".env"
    if not candidate.exists():
        matches = sorted(base.glob("*.env"))
        if not matches:
            return env
        candidate = matches[0]
    for line in candidate.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


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


def rpc_call(rpc_url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req  = urllib.request.Request(rpc_url, body, {
        "Content-Type": "application/json",
        "User-Agent":   "lspr-cartesi-client/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
    if "error" in resp:
        raise Exception(f"RPC error: {resp['error']}")
    return resp["result"]


def abi_encode_add_input(dapp_addr: str, payload: bytes) -> str:
    from eth_utils import keccak
    selector  = keccak(b"addInput(address,bytes)")[:4]
    addr_part = bytes.fromhex(dapp_addr[2:].zfill(64))
    offset    = (64).to_bytes(32, "big")
    length    = len(payload).to_bytes(32, "big")
    padded    = payload + b"\x00" * (-len(payload) % 32)
    return "0x" + (selector + addr_part + offset + length + padded).hex()


def send_input(hex_payload: str, rpc_url: str, dapp: str, mnemonic: str) -> None:
    """Send payload directly to InputBox contract on Sepolia via web3."""
    from eth_account import Account

    payload_bytes = bytes.fromhex(hex_payload[2:])
    data = abi_encode_add_input(dapp, payload_bytes)

    Account.enable_unaudited_hdwallet_features()
    acct = Account.from_mnemonic(mnemonic)
    print(f"\nWallet:   {acct.address}")

    nonce     = int(rpc_call(rpc_url, "eth_getTransactionCount", [acct.address, "latest"]), 16)
    gas_price = int(rpc_call(rpc_url, "eth_gasPrice", []), 16)

    estimate = int(rpc_call(rpc_url, "eth_estimateGas", [{
        "from": acct.address, "to": INPUTBOX, "data": data,
    }]), 16)
    gas_limit = int(estimate * 1.3)  # 30% buffer
    print(f"Nonce:    {nonce}  GasPrice: {gas_price // 10**9} gwei  Gas: {estimate} (limit {gas_limit})")

    tx = {
        "to":       INPUTBOX,
        "value":    0,
        "gas":      gas_limit,
        "gasPrice": gas_price,
        "nonce":    nonce,
        "data":     data,
        "chainId":  int(CHAIN_ID),
    }
    signed  = acct.sign_transaction(tx)
    tx_hash = rpc_call(rpc_url, "eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()])
    print(f"\nTX sent:  {tx_hash}")
    print(f"Explorer: https://sepolia.etherscan.io/tx/{tx_hash}")


def main():
    env = load_env()

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
    ap.add_argument("--rpc-url",   default=None,
                    help="Sepolia RPC URL (overrides .env SEPOLIA_RPC_URL)")
    ap.add_argument("--dapp",      default=None,
                    help="dApp address (overrides .env DAPP_ADDRESS)")
    ap.add_argument("--mnemonic",  default=None,
                    help="Wallet mnemonic (overrides .env MNEMONIC)")
    args = ap.parse_args()

    rpc_url  = args.rpc_url  or env.get("SEPOLIA_RPC_URL", DEFAULT_RPC)
    dapp     = args.dapp     or env.get("DAPP_ADDRESS",    DEFAULT_DAPP)
    mnemonic = args.mnemonic or env.get("MNEMONIC",        "")

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
    print(f"\nNetwork:  Sepolia (chain {CHAIN_ID})")
    print(f"RPC:      {rpc_url}")
    print(f"dApp:     {dapp}")
    print(f"Wallet:   {'from .env' if mnemonic else 'interactive (no mnemonic)'}")
    print(f"\nPayload ({len(hex_payload)} hex chars):")
    print(f"  {hex_payload[:80]}...")

    if args.dry_run:
        cmd = (
            f"cartesi send generic"
            f" --chain-id {CHAIN_ID}"
            f" --rpc-url {rpc_url}"
            f" --dapp {dapp}"
            f" --input {hex_payload}"
            f" --input-encoding hex"
        )
        print("\n-- Dry run. Full command:")
        print(f"  {cmd}")
        return

    send_input(hex_payload, rpc_url, dapp, mnemonic)


if __name__ == "__main__":
    main()
