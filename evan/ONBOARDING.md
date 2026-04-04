# Onboarding — Read This First

You are joining an IMC Prosperity 4 algorithmic trading competition team. Read this ENTIRE file before doing anything.

## Quick Status
- **Best score: 2,787.5** (fake1 live). Target: 3,000+
- **Competition:** Tutorial round (ends Apr 13). Round 1 starts Apr 14.
- **Products:** EMERALDS (stable at 10,000) and TOMATOES (trending ~5,000)
- **Team:** 5 members, multiple claude instances collaborating via CHAT.md

## Critical Files to Read (in order)
1. `CLAUDE.md` — project structure, rules, conventions
2. `COORDINATION.md` — how multiple claudes work together
3. `CHAT.md` — conversation history between claudes and user (READ ALL OF IT)
4. `models/REGISTRY.md` — every model's score and what it does
5. `docs/research-notes.md` — ALL findings from data analysis
6. `docs/strategy-log.md` — strategy evolution and plans
7. `docs/changelog.md` — chronological record of everything done

## The 8 Things You MUST Know

### 1. The Rust Backtester is Our Tool
`prosperity_rust_backtester/` — installed, ±17 accuracy vs live portal.
```bash
rust_backtester --trader /full/path/to/algo.py --dataset tutorial --artifact-mode none
```
The SUB row = portal score. D-2 = out-of-sample validation. NEVER use the Python backtester (prosperity4btx) — it's 10-20x off.

### 2. The v10 Code Corruption Bug
The local `models/e1_v10.py` has WRONG code. The REAL v10 that scored 2,344 is at:
`userdatadump/e1_v10_47816/47816.py`

Difference: real v10 uses **penny-jump MAKE** for TOMATOES. Local copy has **static spread MAKE**. This caused v11-v15 to all fail. ALWAYS copy from 47816.py.

### 3. TOMATOES is 100% Take Fills
MAKE orders NEVER fill on TOMATOES (we're last in queue — price-time priority). ALL TOMATOES profit comes from the TAKE phase. The fair value determines WHAT we take. Everything about spread, skew, layers, CLEAR — irrelevant for TOMATOES PnL because MAKE never fills.

### 4. The 2,770 Ceiling
We tested 8 fundamentally different fair value logics and 50+ parameter configs in the Rust backtester. ALL cap at ~2,770 SUB score. The gap to 3,000 is NOT in:
- Fair value method (filtered mid is best, reversion only adds +5)
- Parameters (swept exhaustively)
- Signals (imbalance, fade, flow, multi-timeframe — all neutral or hurt)
- Take filtering, make structure, position sizing

The 3,000+ people have a STRUCTURAL insight we haven't found. Someone on Discord said "it's if your logic is sound" — implying the answer is in the METHOD, not the parameters.

### 5. Products Interfere — But Only With Corrupted Code
With the REAL v10 penny-jump code, E=1,050 + T=1,477 works fine (crazy7: 2,527). With corrupted static-spread code, E=1,050 crashes T to ~549. The "interference" was a bug, not a market mechanic.

### 6. Current Best Components
- **EMERALDS 1,050:** crazy1 approach (zero skew, limit=80, aggressive CLEAR pos>20→5, penny-jump, 2-layer 65/35 offset=1)
- **TOMATOES 1,737.5:** filtered mid (advol=16) + reversion(-0.229) + penny-jump MAKE + no soft limit + lim=70 + market_trades flow
- **Combined: 2,787.5 live** (fake1)

### 7. Overfitting Status
fake1 is mildly overfit to SUB data (~4% bias). It beats v10 on BOTH days (D-2 +13%, D-1 +17%). For Round 1, use conservative params: advol=15, soft=50.

### 8. Key Market Microstructure Facts
- We are LAST in queue (price-time priority — Discord confirmed)
- EMERALDS: 59 taker events per session, spread goes 16→8 during events
- TOMATOES: 116 taker events, spread goes 13-14→5-8
- Taker timing is RANDOM (CV=0.99, no periodicity)
- Cross-product signal: DEAD (no correlation between E and T taker events)
- Our PnL decomposition: spread capture is NEGATIVE (-24), ALL profit is directional
- 79.5% of TOMATOES fills are followed by favorable price moves

## Model Naming
- `e1_v*` — claude1's production series (v1-v15)
- `e1_crazy*` — claude2's series (crazy1-crazy10)
- `e1_fool*` — claude1's fresh-start series
- `e1_fake*` — Rust-backtester-optimized series
- `e1_p*` — probes (information gathering)
- All models in `models/`. Submit directly from there.

## Tools
- Rust backtester: `rust_backtester --trader path.py --dataset tutorial --artifact-mode none`
- Log processing: `python3 scripts/process_logs.py` (scans userdatadump for unnamed zips)
- Drop new zips in `inbox/` or `userdatadump/`
- Write analysis to `docs/research-notes.md` so all claudes benefit

## What's Been Tried (Don't Repeat)
30+ submissions, 50+ Rust configs. See `models/REGISTRY.md` for full list.
Key failures: A-S dynamic spread, dual fair value, taker fading, two-layer MAKE, trend-riding, aggressive CLEAR on TOMATOES, limit=80 on TOMATOES.

## The Open Question
How do the 3,000+ people get ~230 more than our 2,770 ceiling? The answer is structural, not parametric. If you figure this out, you've solved the problem.
