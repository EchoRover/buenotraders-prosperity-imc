# Strategy Log

Chronological record of trading strategies — ideas, implementations, backtesting results, and live performance.

---

## 2026-04-03 — Tutorial Round Initial Analysis

### Current State
- Algorithm uploaded and active, score: **3,100 SeaShells**
- Products: TOMATOES and EMERALDS

### Strategy Plan: EMERALDS (the easy one)
**Approach:** Fixed fair value market-making at 10,000
- Price is pegged to 10,000 with tiny deviations (±4 max)
- Bot spread is ~16 wide (9,992 / 10,008)
- We can post tighter quotes (e.g., 9,996 / 10,004 or 9,997 / 10,003) to capture spread
- Take any asks below 10,000 and any bids above 10,000
- This alone should generate significant consistent profit (Prosperity 3 equivalent made ~39K/round)

### Strategy Plan: TOMATOES (needs more work)
**Approach:** Dynamic fair value market-making with rolling mid-price
- Use current order book mid-price as fair value estimate
- Post bids/asks around it with some spread
- Track price trend via short-term moving average
- Skew quotes in direction of inventory neutralization when position builds up
- Mean reversion on large deviations (z-score > 1-2)

### Key Risks
- Position limits are **80 per product** (confirmed from backtester source)
- Orders cancelled if total exposure exceeds limit
- Need to track position and adjust order sizes accordingly

### Backtester Baseline
- `example_trader.py` (basic mid-price market-making): **12,604 SeaShells** across 2 days
  - Day -2: 6,812 | Day -1: 5,791
  - EMERALDS: ~2,100/day | TOMATOES: ~4,100/day
- Live score (currently uploaded algo): **3,100 SeaShells**
- Gap suggests our backtester algo is already better than what's uploaded

### Competitive Edge Plan (from winning team research)
1. **Cross-year data check** — when Round 1 drops, immediately check if Prosperity 3 price data correlates
2. **Olivia detection** — build counterparty analysis pipeline for when trader IDs appear
3. **Custom visualization** — fast iteration > complex strategies
4. **Parameter grid search** — reject sharp peaks, find flat stable performance zones
5. **Position clearing** — do 0-EV trades to free capacity for profitable trades (+3% PnL for 2nd place team)

### e1_v1 Results — Parameter Sweep

Ran 27+ parameter combinations. Key findings:

| EMERALD Spread | TOMATO Spread | Total Profit |
|---|---|---|
| 2 | 3 | 12,639 |
| 3 | 4 | 16,108 |
| 5 | 6 | 20,747 |
| 6 | 6 | 22,391 |
| **7** | **6** | **23,671** |
| 8 | 6 | 23,575 |
| 7 | 7 | 21,762 |
| 7 | 8 | 16,210 |

**Peak: EMERALD_SPREAD=7, TOMATO_SPREAD=6** — plateau region, robust.
- EMERALDS profit: ~6,000/day (3x the example trader)
- TOMATOES profit: ~5,700/day
- Wider EMERALD spread = more profit per fill, still inside bot spread (9992/10008)
- TOMATO sweet spot at 6 — wider loses too many fills, tighter loses edge

**Inventory skew**: ESK=0.10 for EMERALDS, 0.20 for TOMATOES (lower is better — less aggressive = more fills)

### Live vs Backtest Comparison

**CRITICAL FINDING: backtester overestimates by ~10-20x.** Live fills are much rarer than backtester assumes.

| Algo | Backtest | Live | Ratio |
|---|---|---|---|
| e1_v1 intermediate | ~12,600 | 863 | ~15x |
| Arjun (spread=3) | — | 1,076 | — |
| e1_v1 FINAL (ES=7, TS=6) | 23,671 | 1,232 | ~19x |

Per-product live PnL:
| Algo | EMERALDS | TOMATOES |
|---|---|---|
| e1_v1 intermediate | 383 | 480 |
| Arjun | 566 | 510 |
| **e1_v1 FINAL** | **558** | **674** |

**Implications:**
- Wider spreads help in backtest but have diminishing returns live
- Our TOMATOES linreg strategy is genuinely better (+32% vs Arjun)
- EMERALDS performance is similar across approaches
- Need to tune for LIVE performance, not backtester

### Deep Analysis: Why v2/v3/v4 All Failed to Beat v1

**All 5 versions side-by-side (TOMATOES only — 90% of the game):**

| | Active | WR | Avg Win | Avg Loss | Gross+ | Gross- | **Net** |
|---|---|---|---|---|---|---|---|
| **v1** | 1,859 | 49.1% | +2.61 | -1.81 | +2,381 | -1,708 | **674** |
| v2 | 1,690 | 52.1% | +2.03 | -1.38 | +1,787 | -1,118 | 669 |
| v3 | 1,859 | 49.1% | +2.61 | -1.81 | +2,381 | -1,708 | 674 |
| **v4** | 1,857 | 49.7% | +2.30 | -1.55 | +2,126 | -1,452 | **674** |
| Arjun | 1,954 | 49.8% | +3.14 | -2.60 | +3,058 | -2,547 | 511 |

**Edge per active tick:**
- v1: 0.362, v2: 0.396, v3: 0.362, v4: 0.363, Arjun: 0.262

**THE PATTERN:** TOMATOES net PnL is capped at ~674 regardless of strategy. Every change we make just trades gross profit for gross loss reduction — the NET stays the same.

**WHY THIS HAPPENS:**
The market has a **fixed amount of edge to extract**. The bots follow deterministic patterns. Once you have a reasonable fair value estimate (linreg) and reasonable spread (6), you're capturing essentially ALL the available edge. Tweaking the fair value estimator (VWAP, imbalance, stricter takes) just reshuffles HOW you capture that edge, not how MUCH.

**WHY ARJUN IS LOWER (511 vs 674):**
Arjun's spread=3 gives bigger avg wins (+3.14) BUT also bigger avg losses (-2.60). His edge per tick is only 0.262 vs our 0.362. Tighter spread = more adverse selection = less edge per tick. Our spread=6 is the sweet spot.

**CONCLUSION: We've hit the ceiling on the tutorial round.**

EMERALDS: 558 is the ceiling. 16 fills × 34.88 = 558. Can't get more fills without narrowing spread (which kills profit per fill).

TOMATOES: ~674 is the ceiling. The edge per tick (~0.36) × active ticks (~1,860) = ~670. No fair value tweak changes this.

### What CAN Move The Needle

**For the tutorial round:** We're done. v1 at 1,232 is near-optimal. Focus effort on Round 1 prep instead.

**For Round 1+ (Apr 14):**
1. **New products** — completely different dynamics, fresh optimization
2. **Cross-year data check** — compare P3 price data to P4 Round 1 products (biggest historical edge)
3. **Olivia detection** — counterparty IDs may be available, copy-trade insider bots
4. **Basket arbitrage (Round 2)** — exploit ETF vs components mispricing
5. **Options pricing (Round 3)** — Black-Scholes, vol smile
6. **Modular code** — build a framework that plugs in new product strategies fast

### Next Steps
1. ~~Set up backtester~~ DONE
2. ~~Build Trader class~~ DONE — `e1_v1.py`
3. ~~Grid-search parameters~~ DONE
4. ~~Submit and check live~~ DONE — **1,232 SeaShells (best of 3 tested)**
5. Experiment with tighter spreads to increase live fill rate
6. Try different linreg lookback windows for TOMATOES
7. Investigate if position limit is actually 50 or different on live
