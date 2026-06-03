"""
Send a backtest request to the local Cartesi node.
Fetches klines off-chain (Binance API), embeds them in the payload,
then sends the transaction directly to the InputBox contract.

Usage:
  python3 send_test.py [--days 7] [--symbol BTCUSDT] [--interval 1h]

Requires: eth-account (pip3 install eth-account)
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from eth_account import Account
from eth_utils import keccak

# ── Config ────────────────────────────────────────────────────────────────────
RPC          = "http://127.0.0.1:8545"
GRAPHQL      = "http://127.0.0.1:8080/graphql"
INPUTBOX     = "0x59b22D57D4f067708AB0c00552767405926dc768"
PRIVKEY      = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
BINANCE_API  = "https://fapi.binance.com"

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_klines(symbol: str, interval: str, days: int) -> list:
    end_ms   = int(time.time() * 1000)
    start_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    all_k = []
    print(f"Fetching {symbol} {interval} {days}d from Binance...", end="", flush=True)
    while start_ms < end_ms:
        url = (f"{BINANCE_API}/fapi/v1/klines?symbol={symbol}&interval={interval}"
               f"&startTime={start_ms}&limit=1500")
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        if not data: break
        all_k.extend(data)
        start_ms = data[-1][0] + 1
        if len(data) < 1500: break
    print(f" {len(all_k)} candles")
    return all_k


def rpc_call(method: str, params: list):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req  = urllib.request.Request(RPC, body, {"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    if "error" in resp:
        raise Exception(f"RPC error: {resp['error']}")
    return resp["result"]


def abi_encode_add_input(dapp_addr: str, payload: bytes) -> str:
    selector  = keccak(b"addInput(address,bytes)")[:4]
    addr_part = bytes.fromhex(dapp_addr[2:].zfill(64))
    offset    = (64).to_bytes(32, 'big')
    length    = len(payload).to_bytes(32, 'big')
    padded    = payload + b'\x00' * (-len(payload) % 32)
    return "0x" + (selector + addr_part + offset + length + padded).hex()


def get_dapp_address() -> str:
    """Read dapp address from cartesi address-book via process call."""
    import subprocess
    result = subprocess.run(
        ["cartesi", "address-book", "--json"],
        capture_output=True, text=True, cwd="/opt/lspr-cartesi"
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return data.get("CartesiDApp", "")
    # Fallback: known address from current build
    return "0xab7528bb862fB57E8A2BCd567a2e929a0Be56a5e"


def graphql_query(query: str) -> dict:
    body = json.dumps({"query": query}).encode()
    req  = urllib.request.Request(GRAPHQL, body, {"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def hex2str(h: str) -> str:
    return bytes.fromhex(h[2:]).decode("utf-8")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol",   default="BTCUSDT")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--days",     type=int,   default=7)
    ap.add_argument("--leverage", type=int,   default=5)
    ap.add_argument("--margin",   type=float, default=100.0)
    ap.add_argument("--sl-pct",   type=float, default=0.002)
    ap.add_argument("--tp-pct",   type=float, default=0.005)
    ap.add_argument("--dapp",     default="")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    if not symbol.endswith(("USDT","BUSD")):
        symbol += "USDT"

    klines = fetch_klines(symbol, args.interval, args.days)

    payload_dict = {
        "symbol":   symbol,
        "interval": args.interval,
        "days":     args.days,
        "leverage": args.leverage,
        "margin":   args.margin,
        "sl_pct":   args.sl_pct,
        "tp_pct":   args.tp_pct,
        "klines":   klines,
    }
    payload_bytes = json.dumps(payload_dict).encode()
    print(f"Payload size: {len(payload_bytes)/1024:.1f} KB ({len(klines)} candles)")

    dapp = args.dapp or get_dapp_address()
    print(f"DApp address: {dapp}")

    data = abi_encode_add_input(dapp, payload_bytes)

    acct      = Account.from_key(PRIVKEY)
    nonce     = int(rpc_call("eth_getTransactionCount", [acct.address, "latest"]), 16)
    gas_price = int(rpc_call("eth_gasPrice", []), 16)

    tx = {
        "to": INPUTBOX, "value": 0, "gas": 5_000_000,
        "gasPrice": gas_price, "nonce": nonce,
        "data": data, "chainId": 31337,
    }
    signed   = acct.sign_transaction(tx)
    tx_hash  = rpc_call("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()])
    print(f"TX sent: {tx_hash}")

    print("Waiting for Cartesi node to process input", end="", flush=True)
    for _ in range(60):
        time.sleep(2)
        print(".", end="", flush=True)
        resp = graphql_query("{ notices { edges { node { index payload } } } }")
        notices = resp["data"]["notices"]["edges"]
        if notices:
            print()
            for edge in notices:
                node = edge["node"]
                result = json.loads(hex2str(node["payload"]))
                print(f"\n=== Backtest Result (notice #{node['index']}) ===")
                for k, v in result.items():
                    if k != "klines":
                        print(f"  {k:15}: {v}")
            return

        # Check for errors
        resp2 = graphql_query("{ reports { edges { node { payload } } } }")
        reports = resp2["data"]["reports"]["edges"]
        if reports:
            print()
            for edge in reports:
                err = hex2str(edge["node"]["payload"])
                print(f"\n[ERROR REPORT] {err}")
            return

    print("\nTimeout: no response in 120s")

if __name__ == "__main__":
    main()
