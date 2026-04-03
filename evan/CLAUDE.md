# CLAUDE.md — IMC Prosperity Workspace

## Project Context
- **Competition:** IMC Prosperity 4 — runs April 14–30, 2026. Tutorial round active now.
- **Team:** buenotraders (5 members)
- **Workspace:** `evan/` directory within the team monorepo

## Project Structure
```
evan/
├── models/          # All trader algorithms + REGISTRY.md (score tracking)
│   ├── REGISTRY.md  # ← SINGLE SOURCE OF TRUTH for all scores
│   ├── e1_v1.py
│   ├── e1_v2.py
│   └── ...
├── logs/            # Competition log dumps (drop zips here)
├── data/            # Market data (round0/, round1/, etc.)
├── docs/            # Chronological documentation
├── scripts/         # Analysis and utility scripts
├── backtests/       # Local backtester output
└── CLAUDE.md        # This file
```

## MANDATORY: Document Everything
**Non-negotiable.** Every action must be documented.
- `docs/changelog.md` — master log, EVERY change
- `docs/strategy-log.md` — strategy ideas, implementations, results
- `docs/technical-log.md` — code decisions, architecture, debugging
- `docs/research-notes.md` — analysis, data findings, references
- `models/REGISTRY.md` — model scores (backtest AND live), parameters, findings
- Entries dated with `## YYYY-MM-DD`, newest first. Be specific.

### Privacy: NO PERSONAL INFO
Repo shared with teammates. No names, emails, credentials. Use role-based refs only.

## File Naming
- Production algos: `e1_v1.py`, `e1_v2.py`, ... (in `models/`)
- Probe/exploration algos: `e1_p1.py`, `e1_p2.py`, ... (in `models/`)
- ALL models live in `models/` ONLY — no root copies, submit directly from `models/`
- Never delete or modify old versions — once submitted, a model is FROZEN
- Always create a NEW version with changes, never patch an old one

## When User Drops Logs
1. User drops zip(s) in `logs/` or `userdatadump/`
2. Extract, rename to `{model}_{submissionID}.json/.py`
3. Parse the JSON for: `profit`, per-product PnL, fill rates, win rates
4. Update `models/REGISTRY.md` with the live scores
5. Compare to backtest predictions and previous versions
6. Document findings in `docs/strategy-log.md`

## Competition Details
- Tutorial products: TOMATOES (trending ~5000) and EMERALDS (stable at 10000)
- Position limits: 50 per product
- Import: `from datamodel import OrderDepth, TradingState, Order`
- `run()` returns `(orders: dict[str, list[Order]], conversions: int, traderData: str)`
- `traderData` persists state between ticks
- Orders: integer prices, live one tick, you trade last after bots
- File size limit: 100KB
- Backtester overestimates ~10-20x vs live — use for directional comparison only

## Backtester
- Package: `prosperity4btx` (v0.0.2), installed in gpy
- Run: `python -m prosperity4bt models/e1_v1.py 0`
- Flags: `--no-out`, `--print`, `--vis`, `--merge-pnl`, `--no-progress`
- Data: `data/round0/` for tutorial, future rounds in `data/round1/`, etc.
