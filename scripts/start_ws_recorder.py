"""
Launcher for the prospective WS recorder (Bybit + OKX).

Usage:
    python scripts/start_ws_recorder.py              # run until Ctrl+C / SIGTERM
    python scripts/start_ws_recorder.py --test 30    # 30-second test run, print stats

Data lands in research/datasets/raw/ws/<venue>/<stream>/<YYYY-MM-DD>.jsonl
Logs:                       research/datasets/raw/ws/logs/ws_recorder_<venue>.log

NOTE: this starts a foreground process that dies with the session/host.
For 24/7 collection run it as a system service (see
research/multi_exchange/DATASETS/WS_RECORDER.md).
"""
import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trading_engine.collectors.ws_recorder import WSRecorder

BASE_DIR = Path(__file__).resolve().parent.parent / "research" / "datasets" / "raw" / "ws"

# Symbol configuration for HYP-M-003 (funding carry) / HYP-M-004 (liquidations).
CONFIG = {
    "bybit_symbols": ["BTCUSDT", "ETHUSDT"],
    "bybit_trade_symbols": ["BTCUSDT"],       # agg trades (publicTrade)
    "bybit_orderbook_symbols": ["BTCUSDT"],   # orderbook50 — for future Track A
    "bybit_oi_symbols": ["BTCUSDT", "ETHUSDT"],
    "okx_inst_ids": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    "okx_trade_inst_ids": ["BTC-USDT-SWAP"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prospective WS data recorder (Bybit + OKX)")
    parser.add_argument(
        "--test",
        type=int,
        metavar="SECONDS",
        default=None,
        help="run for N seconds then shut down cleanly and print stats",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop = threading.Event()

    def _handle_signal(signum, _frame):
        logging.getLogger(__name__).info("signal %s received — shutting down", signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    recorder = WSRecorder(BASE_DIR, **CONFIG)
    recorder.start()

    deadline = time.monotonic() + args.test if args.test else None
    try:
        while not stop.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                logging.getLogger(__name__).info("test window (%ds) finished", args.test)
                break
            time.sleep(0.5)
    finally:
        recorder.stop()

    stats = recorder.stats()
    total = sum(stats.values())
    print(f"\n=== WS recorder stats: {total} events ===")
    for stream, count in stats.items():
        print(f"  {stream:<40} {count}")
    print(f"data dir: {BASE_DIR}")


if __name__ == "__main__":
    main()
