# Model Registry

All models, their scores, and what changed. Single source of truth.

## Score Board

| Model | Backtest Total | Backtest E | Backtest T | Live Total | Live E | Live T | Status |
|---|---|---|---|---|---|---|---|
| example_trader | 12,604 | 4,268 | 8,336 | — | — | — | baseline |
| arjun (prosperity04) | — | — | — | 1,076 | 566 | 510 | teammate ref |
| **e1_v1** | 23,671 | 12,184 | 11,487 | **1,232** | 558 | 674 | submitted |
| **e1_v2** | 24,385 | 12,184 | 12,201 | **1,226** | 558 | 668 | v1 ≈ v2 live |
| e1_p1 limit50 | — | — | — | 396 | 87 | 309 | **EMERALD fills ONLY at ±1** |
| e1_p1 limit80 | — | — | — | -214 | -523 | 309 | **LIMIT IS 80 CONFIRMED** |
| e1_p2 | — | — | — | -24 | -8 | -16 | **Fair value ≈ mid-price** |
| **e1_v3** | 13,625 | 2,140 | 11,485 | **863** | 189 | 674 | limit=80 good, E_SPREAD=1 BAD |
| **e1_v4** | 23,764 | 12,184 | 11,580 | **1,232** | 558 | 674 | identical to v1 live |
| **e1_v5** | 28,754 | 14,420 | 14,334 | **1,650** | 867 | 783 | penny-jump works! CLEAR too aggressive on T |
| e1_p3 | 23,756 | 14,420 | 9,335 | **1,523** | 867 | 656 | trend-riding hurt TOMATOES |
| e1_v6 | 23,268 | 8,339 | 14,929 | **1,580** | 624 | 956 | asymmetric E = BAD |
| **e1_v7** | 29,349 | 14,420 | 14,929 | **1,823** | 867 | 956 | best so far |
| **e1_v8** | — | — | — | **1,646** | 867 | 779 | fade hurt live |
| e1_v9 | — | — | — | ~2,100 | 867 | ~1,233 | matched LADDOO |
| **e1_v10** | — | — | — | **2,344** | 867 | 1,477 | **filtered mid + reversion = breakthrough** |
| **e1_crazy1** | — | — | — | **2,065** | **1,050** | 1,015 | **EMERALD 1,050! zero skew + limit=80** |
| **e1_v11** | — | — | — | **???** | ??? | ??? | **v10 + A-S dynamic spread** |
| **e1_crazy2** | — | — | — | **1,793** | **1,050** | 743 | **limit=80 KILLED TOMATOES (-734 vs v10)** |
| **e1_crazy3** | — | — | — | **921** | **1,050** | **-129** | **all 3 bets failed: spread=8 + zero skew + no reversion = NEGATIVE T** |
| **e1_crazy4** | — | — | — | **1,598** | **1,050** | 548 | adverse filter + penny-jump didn't help |
| **e1_crazy5** | — | — | — | — | — | — | skipped — EMA smoothing would break v10 T |
| **e1_crazy6** | — | — | — | **1,599** | **1,050** | 549 | v10 on-disk T (static spread) + crazy1 E → interference confirmed |
| **e1_crazy7** | — | — | — | **2,527** | **1,050** | **1,477** | **NEW BEST! Real v10 T + crazy1 E. No interference.** |
| **e1_crazy8** | — | — | — | **2,661** | **1,050** | **1,611** | **NEW BEST! T+134 from raised limits. E stayed 1,050.** |
| **e1_crazy9** | — | — | — | **2,505** | **1,050** | 1,455 | TAKE_EDGE=0 HURT (-156 T). Don't remove take edge. |
| **e1_crazy10** | — | — | — | **1,686** | 872 | 814 | **CRASHED. E_TAKE=0 bad, dual FV killed directional edge** |
| **e1_crazy11** | — | — | — | **???** | ??? | ??? | **NOVEL: adaptive beta — bot learns optimal reversion in real-time** |

## Key Insight: v2 is NOT better than v1 live

v2 was more conservative (stricter takes, VWAP mid, trend shift) but the net result was basically identical (-5.6 SeaShells). The changes reduced both profits AND losses equally.

| Metric | v1 TOMATOES | v2 TOMATOES |
|---|---|---|
| Active ticks | 1,859 (93.0%) | 1,690 (84.5%) |
| Win rate | 49.1% | 52.1% |
| Avg win | +2.61 | +2.03 |
| Avg loss | -1.81 | -1.38 |
| Gross profit | +2,381 | +1,787 |
| Gross loss | -1,708 | -1,118 |
| **Net** | **674** | **668** |

**Conclusion:** Being more conservative doesn't help — we trade less and make less per trade. The aggressive v1 approach is just as good. Next improvements need to come from BETTER SIGNALS, not tighter filters.

## Live Performance Detail

### e1_v1 (submission 45769) — LIVE: 1,232
- EMERALDS: 558 (16 fills, 100% win rate, avg +34.88/fill)
- TOMATOES: 674 (1,859 active ticks of 2,000, 49.1% win rate)
  - Wins: 913, avg +2.61, total +2,381
  - Losses: 946, avg -1.81, total -1,708
  - Net edge per active tick: +0.36

### e1_v2 (submission 45811) — LIVE: 1,226
- EMERALDS: 558 (16 fills, 100% win rate, avg +34.88 — identical to v1)
- TOMATOES: 668 (1,690 active ticks of 2,000, 52.1% win rate)
  - Wins: 880, avg +2.03, total +1,787
  - Losses: 810, avg -1.38, total -1,118
  - Net edge per active tick: +0.40 (better per-tick but fewer ticks)

### arjun (submission 45684) — LIVE: 1,076
- EMERALDS: 566 (28 fills, 100% win rate, avg +20.21/fill)
- TOMATOES: 510 (1,954 active ticks, 49.8% win rate)
  - Wins: 974, avg +3.14, total +3,058
  - Losses: 980, avg -2.60, total -2,547

### e1_v1 intermediate (submission 45757) — LIVE: 863
- EMERALDS: 383
- TOMATOES: 480

## Model Descriptions

### example_trader.py
- Baseline. Simple mid-price market-making, qty=10, no taking.
- EMERALDS spread=2, TOMATOES spread=3.

### e1_v1.py
- Fixed fair value 10000 for EMERALDS. Linreg fair value for TOMATOES.
- Take mispriced orders. Full capacity. Inventory skew.
- Params: E_SPREAD=7, T_SPREAD=6, E_SKEW=0.10, T_SKEW=0.20, T_TAKE=1

### e1_v2.py
- Changes from v1:
  - Fixed position limit bug (separate buy/sell budgets)
  - VWAP microprice instead of simple mid for TOMATOES
  - Stricter takes (fair±3 instead of ±1)
  - Trend-aware spread biasing via linreg slope (±1 tick)
- Params: E_SPREAD=7, T_SPREAD=6, E_SKEW=0.10, T_SKEW=0.20, T_TAKE=3, T_TREND_CAP=1

### e1_p1.py (PROBE)
- Fill rate mapper + position limit tester
- Phase 1 (ticks 0-999): posts qty=3 at 7 price levels per side
- Phase 2 (ticks 1000-1500): tries to accumulate >50 EMERALDS to test real limit
- Logs all fills and max positions to traderData

### e1_p2.py (PROBE)
- Hidden fair value detector
- Buys 1 EMERALD + 1 TOMATO, then holds forever
- PnL changes = changes in hidden fair value (since position is constant)
- Logs order book snapshots and market trades

### e1_crazy1.py (claude2 agent)
- **CRAZY SERIES** — fresh approach from claude2 agent, not backtester-optimized
- **Novel technique: adverse selection filtering** (from Linear Utility, 2nd place P2)
  - Skip takes when best level volume >= 15 (market maker bot, not safe to trade against)
  - Never tested in this codebase before
- **Novel technique: market-maker mid fair value** (from Linear Utility)
  - Filter book for large-vol levels only (bot quotes) → cleaner fair value
  - Falls back to deep VWAP when no large-vol levels exist
- EMERALDS: L5 penny-jump + v7 aggressive CLEAR, limit=80, zero skew
- TOMATOES: L5 ensemble (0.25*LR + 0.45*EMA + 0.30*micro) + OBI 1.3 + fade -0.25
  - Adverse filter on takes, mm_mid fair value
  - Limit=80, hard brake ±60, aggressive CLEAR at ±40→20
  - Two-layer 65/35, L2_offset=1

## Key Findings

1. **Backtester overestimates ~10-20x** vs live. Use `--match-trades worse` for better estimate (~15x still).
2. **EMERALDS barely trades** live (0.8-1.4% of ticks). Spread doesn't matter much.
3. **TOMATOES is 90%+ of the game**. Active on ~93% of ticks.
4. **Wider spreads reduce losses more than wins** — net positive effect.
5. **Linreg fair value outperforms simple mid** for TOMATOES (+32% vs teammate).
6. **Conservative filters (v2) don't help** — trade less but same net PnL. Need better signals.
7. **POSITION LIMITS UNKNOWN** — backtester says 80, teammate uses 50. PROBE e1_p1 will test.
8. **Hidden fair value exists** — PnL scored against "Wall Mid" (avg of large-qty bid/ask walls), not simple mid.
9. **Wall Mid for EMERALDS** — look at level 2 prices: (bid_price_2 + ask_price_2) / 2. Should ≈ 10000.
5. **Linreg fair value outperforms simple mid** for TOMATOES (+32% vs teammate).
