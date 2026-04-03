# Technical Log

Code architecture decisions, algorithm details, implementation notes, and debugging records.

---

## 2026-04-03

### Backtester Setup

**Package chosen:** `prosperity4btx` (v0.0.2) from PyPI over the GitHub repo (`kevin-fu1/imc-prosperity-4-backtester`).

**Rationale:** Both are based on the same codebase (Jasper van Merle's Prosperity 3 backtester). The PyPI package is easier to install (`pip install prosperity4btx`) and already bundles the round 0 tutorial data. The GitHub repo requires cloning and manual PYTHONPATH setup. The PyPI package also has a cleaner CLI interface.

**How to run:**
```bash
# Run on all days of round 0 (using bundled data)
python -m prosperity4bt example_trader.py 0

# Run on a specific day
python -m prosperity4bt example_trader.py 0--1

# Use custom data directory (for when we have new round data)
python -m prosperity4bt example_trader.py 0 --data data/

# Useful flags
#   --no-out          Don't save log file
#   --no-progress     No progress bars
#   --print           Print trader stdout while running
#   --merge-pnl       Carry P&L across days
#   --vis             Open results in web visualizer
```

**Data directory structure:** The `--data` flag expects:
```
data/
  round0/
    prices_round_0_day_-1.csv
    prices_round_0_day_-2.csv
    trades_round_0_day_-1.csv
    trades_round_0_day_-2.csv
  round1/
    ...
```

**Trader class API:** The algorithm file must expose a `Trader` class with a `run(state: TradingState)` method returning `(orders: dict[str, list[Order]], conversions: int, traderData: str)`.

**Position limits (from `prosperity4bt/data.py`):**
- EMERALDS: 80
- TOMATOES: 80

**Output logs** are saved to `backtests/<timestamp>.log` by default. These can be uploaded to the Prosperity visualizer for analysis.

<!-- New entries go below this line, newest first -->
