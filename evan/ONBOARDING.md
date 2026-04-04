# Onboarding — Read This First

You are joining an IMC Prosperity 4 algorithmic trading competition team. Read this ENTIRE file before doing anything.

## Quick Status
- **Best score: ~2,600** (crazy8). Target: 3,000+
- **Competition:** Tutorial round (ends Apr 13). Round 1 starts Apr 14.
- **Products:** EMERALDS (stable at 10,000) and TOMATOES (trending ~5,000)
- **Team:** 5 members, multiple claude instances collaborating

## Critical Files to Read (in order)
1. `CLAUDE.md` — project structure, rules, conventions
2. `COORDINATION.md` — how multiple claudes work together
3. `CHAT.md` — conversation history between claudes and user
4. `models/REGISTRY.md` — every model's score and what it does
5. `docs/research-notes.md` — ALL findings from data analysis (READ CAREFULLY)
6. `docs/strategy-log.md` — strategy evolution and plans

## The 5 Things You MUST Know

### 1. The v10 Code Corruption Bug
The local `models/e1_v10.py` has WRONG code. The REAL v10 that scored 2,344 is at:
`userdatadump/e1_v10_47816/47816.py`

The difference: real v10 uses **penny-jump MAKE** for TOMATOES. The local copy has **static spread MAKE**. This caused v11-v15 to all fail (~549 TOMATOES). ALWAYS copy from the submitted 47816.py file, NEVER from models/e1_v10.py.

### 2. TOMATOES is 100% Take Fills
MAKE orders NEVER fill on TOMATOES (we're last in queue — price-time priority). ALL profit comes from the TAKE phase. The filtered mid + reversion(-0.229) shifts our fair value, which determines WHAT we take. Everything about spread, skew, layers, CLEAR on TOMATOES is irrelevant noise — only the TAKE fair value matters.

### 3. Products Interfere (Sometimes)
When EMERALDS uses zero skew + limit=80 (scoring 1,050), TOMATOES results change. With the REAL v10 penny-jump code, both work together (crazy7: E=1050 + T=1477 = 2,527). With corrupted code, T crashes to ~549.

### 4. The Backtester is Misleading
- Community backtester overestimates 10-20x vs live
- `--match-trades worse` is slightly better but still 10x+ off
- Backtester doesn't model queue priority (we're last in queue)
- NEVER optimize for backtester numbers
- Only live submissions tell the truth

### 5. What's Been Tried (So You Don't Repeat)
| Approach | Result | Why |
|---|---|---|
| Parameter tuning (spread, skew) | No improvement | v10's config is near-optimal |
| Imbalance signal | Untested properly | Was tested with wrong MAKE code |
| Fade/reversion signals | Hurt or neutral | Added noise to FV pipeline |
| A-S dynamic spread | Crashed (v11=1,172) | Too complex for live |
| Dual fair value (make vs take) | Crashed (v15=1,416) | Removed the directional bias that creates profit |
| Two-layer quoting | Zero effect (fool2=v10) | MAKE never fills anyway |
| Taker event fading | Zero effect (fool4=v10) | Nothing to take near mid |
| Wider TOMATO limits (crazy8) | +73 (2,600) | Letting positions ride works |

## The Path to 3,000
Gap: ~400 on TOMATOES. Need T from ~1,550 to ~1,950.

**What works:** filtered mid (vol>=15) + reversion(-0.229) + penny-jump MAKE + higher limits
**What's untested:** state.market_trades data (never used in any model), different T_TAKE_EDGE values, combining imbalance WITH real penny-jump code
**The key insight:** We're a directional trader, not a market maker. 79.5% of fills are followed by favorable price moves. Improving that accuracy or letting positions ride larger = more profit.

## Model Naming
- `e1_v*` — claude1's production series
- `e1_crazy*` — claude2's series
- `e1_fool*` — claude1's fresh-start series
- `e1_p*` — probes (information gathering)
- All models in `models/`. Submit directly from there.

## Log Processing
Drop zips in `inbox/` or `userdatadump/`. Run `python3 scripts/process_logs.py` or process manually. Write detailed analysis to `docs/research-notes.md` so all claudes benefit.
