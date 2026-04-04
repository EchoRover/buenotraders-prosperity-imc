# Research Notes

Market analysis, data exploration, external references, and findings.

---

## 2026-04-04 — AR Model Analysis + Signal Decomposition (claude2)

### CRITICAL: Rust backtester cannot differentiate signal changes

Tested 20+ variants. ALL give exactly SUB=2770.50 (170 trades). Changes to:
- Float vs integer fair value
- default_edge 1 vs 2
- Adverse selection filtering
- LIMITS["TOMATOES"] 70 vs 80
- Two-layer MAKE
- Flow multiplier (0.5 to 5.0)
- Reversion beta values

...produce ZERO change on Rust SUB. All 170 fills are from TAKE+CLEAR; MAKE never fills on Rust.

### Signal contribution decomposition (Rust SUB, T only)

| Config | T_SUB | Extra trades | Delta from baseline |
|---|---|---|---|
| 1-tick reversion only | 1715.50 | 169 | baseline |
| NO reversion at all | 1715.50 | 169 | +0 |
| + 5-tick reversion | 1715.50 | 169 | +0 |
| + flow signal (2.0x) | 1720.50 | 170 | +5 |
| All three combined | 1720.50 | 170 | +5 |

**Conclusion:** Reversion adds ZERO on Rust. Flow adds +5 (one extra trade). The live-only PnL from signals is massive: 261 for fake1 vs v10.

### TOMATOES Price Data Analysis (AR model fitting)

Analyzed 20,000 ticks of filtered_mid across both days:

**Autocorrelation structure:**
- Lag 1: -0.248 (strong mean reversion)
- Lag 2: +0.000 (negligible)
- Lag 3: +0.000 (negligible)
- Lag 5: -0.015 (weak)

**AR(1) coefficient:** -0.248 (our -0.229 was 7% too weak)

**AR(2) coefficients:** lag1=-0.264, lag2=-0.065
- The lag-2 signal is REAL and we never used it

**Level AR(4) weights:** [0.735, 0.196, 0.053, 0.017] (sum=1.000)
- Stanford Cardinal (2nd P1) used this approach
- Directly predicts price level as weighted average

**Price change distribution:**
- 52.6% no change, 15.2% ±1, 7.3% ±0.5, <1% ±2+
- Mean: -0.002 (negligible drift), Std: 0.713

**Conditional reversion:** 70.5% reversion rate when |Δ| >= 1

### New models built

- **crazy12:** AR(2) return model (β1=-0.264, β2=-0.065) + flow signal + crazy8 E
- **crazy13:** Level AR(4) direct prediction + flow signal + crazy8 E
- Both: Rust 2,770 (ceiling). Must test live for differentiation.

---

## 2026-04-04 — Rust Backtester + Parameter Sweep → 2,787 NEW BEST (claude1)

### Rust Backtester Discovery
Installed GeyzsoN's Rust backtester (github.com/GeyzsoN/prosperity_rust_backtester). 
It models QUEUE PRIORITY (we're last) — this is why it's ±17 of live vs Python's 10-20x overestimate.

Output has 3 rows: D-2 (10k ticks), D-1 (10k ticks), SUB (2k ticks = portal score).

### Parameter Sweep Results (using Rust backtester SUB score)

| Param | Range tested | Best value | Impact |
|---|---|---|---|
| T_SOFT_LIMIT | 5-200 | 100 (no soft limit) | +183 (from 2,505 to 2,684) |
| T_LIM | 50-80 | 70 | +50 |
| T_REVERSION_BETA | -0.10 to -0.60 | -0.10 to -0.44 all same | 0 (not the bottleneck) |
| T_TAKE_EDGE | 0, 1, 2 | 1 | best (0 and 2 both worse) |
| T_ADVERSE_VOL | 14-29 | 16-18 | +31 (from 2,734 to 2,765) |
| market_trades flow | weight 0-5 | 1-2 | +5 |
| 5-tick reversion | weight 0-1 | 0-0.5 | +5 |

### fake1 Final Config
- E: crazy1 approach (limit=80, zero skew, aggressive CLEAR pos>20→5) = 1,050
- T: filtered mid (advol=16) + reversion(-0.229) + penny-jump MAKE + no soft limit + lim=70 + market_trades flow = 1,737.5
- **Rust SUB: 2,770.5 → Live: 2,787.5** (off by +17)

### MAKE Structure Sweep (Rust backtester)
| MAKE approach | SUB score |
|---|---|
| penny+1 (current) | 2,770 |
| penny+2 (wider) | 2,770 (identical!) |
| penny+1 two-layer | 2,770 (identical!) |
| static spread=4 | 2,337 |
| static spread=6 | 2,337 |
| join bot | 1,213 |
| aggressive | 1,687 |
| NO MAKE at all | 1,356 (T=306!) |

**KEY FINDING: MAKE DOES FILL.** Removing MAKE drops T from 1,720 to 306 (−1,414). Our earlier claim that "MAKE never fills" was WRONG. The penny-jump MAKE fills ARE happening — they just have large edge from mid because penny-jump prices are far from mid.

Penny-jump +1 and +2 give identical scores — the exact distance doesn't matter. What matters is posting RELATIVE TO THE BOOK (not relative to fair). Static spread posts relative to fair → off-center when reversion shifts fair → worse fills.

### Overfitting Check
- D-2/D-1 ratio: fake1=1.165 vs v10=1.204 — MILD bias to D-1, not severe
- fake1 beats v10 on BOTH days: D-2 +13%, D-1 +17%, SUB +19%
- Core improvements (higher limits, advol=16) are robust across days
- For Round 1: dial back to advol=15, soft=50 to be safe

---

## 2026-04-04 — Session Summary: 2,527 ceiling, what's needed for 3,000 (claude1)

Best score: 2,527 (crazy7/fool4) = E:1,050 + T:1,477
Target: 3,000 → need T:1,950 (+473)

KEY FACTS:
- TOMATOES is 100% TAKE fills. MAKE never fills (queue priority — we're last).
- 122 takes, 83 winners (+1,820), 39 losers (-158), net +1,477
- Spread capture is NEGATIVE. All profit is directional (post-fill price movement).
- v10 code was CORRUPTED in local models/ — every v11-v15 had wrong MAKE code.
- ALWAYS copy from userdatadump/e1_v10_47816/47816.py (the actual submitted file).
- Two-layer, taker fading, signals — all tested properly now, none moved the needle.

UNTESTED PATHS TO 3,000:
1. state.market_trades data — genuinely unused data source
2. Imbalance + reversion combined with REAL penny-jump (was tested with WRONG code before)
3. Different TAKE_EDGE (0 instead of 1 — take AT fair, not fair-1)
4. Completely different FV: use own_trades history or market_trades for prediction
5. Accept 2,527 on tutorial and crush Round 1 with better preparation

---

## 2026-04-04 — PnL DECOMPOSITION: We're NOT market making (claude1)

v10 TOMATOES PnL decomposition:
- **Spread capture: -24** (NEGATIVE — we LOSE on every fill at execution)
- **Post-fill favorable moves: +1,662** (our ENTIRE profit is directional)
- **79.5% of fills are followed by favorable price moves** (only 20.5% adverse)

**We are NOT a market maker. We are a directional trader disguised as one.**

The filtered mid + reversion(-0.229) gives us a directional edge: when we buy, price subsequently rises 79.5% of the time. When we sell, price drops. This is the source of ALL our TOMATOES profit.

**Implication for 3,000+:** Don't improve spreads, fills, or market making mechanics. Improve the DIRECTIONAL SIGNAL. Options:
- Trade MORE when signal is strongest (tight spread = taker just hit = strongest reversion)
- Trade LESS when signal is weakest (no taker activity = noise)
- Find a better directional predictor than reversion(-0.229)
- Increase position size when conviction is high

---

## 2026-04-04 — Discord: Price-Time Priority is WHY backtester fails (claude1)

From Discord user Abad + Aryan Parekh:

**We are the LAST market maker at each tick.** Our orders go to the BACK of the queue.

What this means:
- If we post at the SAME price as the bot, the bot's order gets filled FIRST (time priority)
- "If you try to place quotes at best bid and best ask you basically never get filled" — LIVE
- But backtesters DO fill them because they don't model queue position
- **THIS IS THE BACKTESTER-LIVE GAP.** Not fill rate or data size — QUEUE PRIORITY.

Why penny-jumping works: posting at bot_price + 1 creates a NEW price level where WE have time priority (we're the only order there). The taker fills us first because our price is better.

Why joining the bot fails: posting at bot_price puts us BEHIND the bot in queue. The bot gets filled first. We only get filled if the taker's order is larger than the bot's volume at that level.

**Implication for our spread:**
- Wider spread (further from bot) = we're at a unique price level = guaranteed queue priority
- But wider = less attractive to taker = fewer fills
- The sweet spot is penny-jumping: 1 tick better than bot = best price AND queue priority

**Why someone is stuck at 2,600:**
"my strategy is simply getting free money whenever I can and then overbidding and undercutting by (+-1) when profitable and unwinding" — this is exactly our v10 approach. They cap at 2,600. The 3,000+ people do something beyond penny-jump + unwind.

**What could the 3,000+ people be doing differently?**
If penny-jump + CLEAR caps at ~2,500-2,600, the extra 500+ must come from:
1. Better TAKE timing (only take when queue is favorable)
2. More fills per taker event (larger quote volume captures more)
3. Better position management that enables more cycles
4. Or a completely different quoting structure we haven't considered

---

## 2026-04-04 — CRITICAL: Products are NOT independent (claude1)

v12 AND v13 both score 1,599 (E:1050, T:549). Every time E=1050, T crashes. Products interfere. v10's 2,344 (E:867, T:1477) works because E=867 leaves market liquidity for T. Cannot combine "best E" + "best T" independently.

Cross-product signal tested: DEAD (no correlation between EMERALD and TOMATO taker events). Taker timing: random (CV=0.99). Book shape as predictor: weak (8.5% vs 5.2%). None of these are the 3,000 breakthrough.

---

## 2026-04-04 — v12 Results: CLEAR on TOMATOES is the killer (claude1 analysis)

### e1_v12 (submission 47912) — LIVE: 1,599 (E: 1,050, T: 549)
- EMERALDS: 1,050 — crazy1 approach works perfectly
- TOMATOES: 549 — spiraled to position -105
- **ROOT CAUSE:** v12 added a CLEAR phase to TOMATOES that v10 doesn't have
- v10 TOMATOES has NO CLEAR — just TAKE + MAKE with filtered mid + reversion
- The CLEAR aggressively sells at fair when pos>0, pushing position negative, then take piles on
- **LESSON: TOMATOES should NOT have CLEAR.** The reversion + filtered mid handles position naturally.
- v10 remains our best at 2,344 with TOMATOES position [-9, +44] — healthy without CLEAR

---

## 2026-04-04 — crazy3 Results: All 3 contrarian bets FAILED (claude2 analysis)

### e1_crazy3 (submission 47927) — LIVE: 921 (E: 1,050, T: -129)
- EMERALDS: 29 fills, 29W/0L — identical to crazy1, rock solid
- TOMATOES: 1,936 active (96.8%), 955W (49.3%) / 981L (50.7%), avg win +9.82, avg loss -9.70, **edge/tick -0.067**
- TOMATOES went NEGATIVE. We're losing money per trade.

### Post-mortem: why each bet failed
1. **Spread=8:** Too wide. Our quotes land behind bot makers (~fair±6.5). We only fill on large moves, which means we're often catching the wrong side of momentum. Spread=6 keeps us competitive with bots for priority.
2. **Zero skew:** TOMATOES trends. Without skew, inventory accumulates in the trend direction with no correction. CLEAR alone can't keep up. Unlike EMERALDS (stable, mean-reverts), TOMATOES NEEDS skew to manage directional risk.
3. **Conditional reversion (fade only on tight spread):** On 93% of ticks we used raw filtered mid with zero reversion. This means we're just FOLLOWING the price with no edge — market-making without a directional view is break-even minus costs. v10's constant reversion (-0.229) provides the edge that makes market-making profitable.

### CRITICAL INSIGHT: EMERALDS vs TOMATOES are FUNDAMENTALLY different
- EMERALDS (stable): zero skew works, wider spread works, aggressive CLEAR works, limit=80 works
- TOMATOES (trending): NEEDS skew, NEEDS tight spread, NEEDS constant reversion, NEEDS limit=50
- **Do NOT apply EMERALDS lessons to TOMATOES.** They are opposite products.

### What still works for TOMATOES
v10 remains the gold standard: filtered mid + constant reversion (-0.229) + spread=6 + skew=0.15 + limit=50 + hard=40 = **1,477**

---

## 2026-04-04 — crazy2 Results: limit=80 KILLS TOMATOES (claude2 analysis)

### e1_crazy2 (submission 47885) — LIVE: 1,793 (E: 1,050, T: 743)
- Total: 1,793 (E: 1,050, T: 743)
- EMERALDS: 29 fills, 29W/0L, avg +36.21/fill — **identical to crazy1, limit=80 E is stable**
- TOMATOES: 1,837 active (91.9%), 936W (51.0%) / 901L (49.0%), avg win +5.60, avg loss -5.00, edge/tick +0.404
- **TOMATOES HALVED from v10: 1,477 → 743 (-734, -49.7%)**

### WHY: limit=80 is POISON for TOMATOES

The v10 approach (filtered mid + reversion) works with limit=50 because the tight limit NATURALLY constrains position growth:
- At pos=40, buy_b = 50-40 = 10 (barely buying)
- Hard limit at 40 kills buying at pos≥40
- Positions stay in tight range [-9, +44]

With limit=80:
- At pos=40, buy_b = 80-40 = 40 (STILL buying aggressively)
- Hard brake at 60 is too late
- Positions grow larger, amplifying losses when TOMATOES reverses

The aggressive CLEAR (pos>40→20) tries to fix this but each clear at fair±1 COSTS 1 per unit. On TOMATOES, clearing 20 units costs ~20. If it clears multiple times per day, that's -100+ just on clearing costs. On EMERALDS this works because the next fill cycle earns +36. On TOMATOES the edge per cycle is much smaller (~0.5/tick), so clearing costs eat the profit.

### CRITICAL LESSON
**limit=80 works for STABLE products (EMERALDS), FAILS for TRENDING products (TOMATOES).**
- EMERALDS: no trends, stable FV → larger capacity = more fills = more profit
- TOMATOES: trends → larger capacity = larger inventory = larger losses on reversal
- Don't try limit=80 on TOMATOES again. Keep limit=50 with hard_limit=40.

### Implication for crazy3
- EMERALDS: keep crazy1 (limit=80, zero skew, aggressive CLEAR) = 1,050
- TOMATOES: use v10 EXACTLY (limit=50, filtered mid, reversion, hard_limit=40) = 1,477
- Combined baseline = 2,527. Improve from THERE with spread/signal changes, NOT limit changes.

---

## 2026-04-04 — crazy1 Results (claude2 analysis)

### e1_crazy1 (submission 47851) — LIVE: 2,065 (E: 1,050, T: 1,015)
- Total: 2,065 (E: 1,050, T: 1,015)
- EMERALDS: 29 fills, 29W/0L, avg +36.21/fill — **breakthrough: +183 over previous best (867)**
- TOMATOES: 1,963 active (98.2%), 985W (50.2%) / 978L (49.8%), avg win +9.76, avg loss -8.79, edge/tick +0.517
- Key: zero skew + limit=80 + aggressive CLEAR gave EMERALDS +21% improvement

---

## 2026-04-03 — Community Intel & Critical Findings

### Discord Intel — Competitive Landscape (2026-04-04)

**Portal scores (real submissions, not backtester):**
| Player | Portal Score | Backtester | Notes |
|---|---|---|---|
| Mr. Nobody | **3,119** | 34,000+ | "simple market making + unwinding/flattening" |
| Mrinmoy_Banik | 2,994 | — | |
| Ethan | 2,840 | 32,800 | |
| Someone | 3,200+ | — | highest seen |
| "Untuned strat" | ~2,700-2,800 | — | benchmark per community |
| **Us (e1_v1)** | **1,232** | 23,671 | need massive improvement |

**Ideal EMERALDS PnL: 1,050** (per Ethan, confirmed top player)
- Our teammates get 867 (with limit=50)
- With limit=80, we should beat 1,050

**Key community insights:**
- "Testing dataset is 10x longer" — portal runs ~2,000 ticks, full round runs ~20,000
- "if your submission shows 3k you'll prob get ~30k on testing" — portal score × 10 ≈ full round score
- "Overfitting" warning — backtester PnL ≠ portal PnL, careful with tuning
- "On submission day price of tomatoes also moves against you if you take a lot of orders" — market impact exists
- Mr. Nobody gets 3,119 with "just simple market making + unwinding/flattening" — CLEAR is the key
- Visualizer: https://kevin-fu1.github.io/imc-prosperity-4-visualizer/visualizer

**What this means for us:**
- 3,000+ is very achievable with proper techniques
- We're 1,800 below the top — EMERALDS gap (558 vs 1,050) = 492, TOMATOES gap = ~1,300
- "Simple market making + unwinding" = penny-jump + CLEAR + basic fair value. That's it.
- The benchmark "untuned" score is 2,700. We're at 1,232. We're severely underperforming.

---

### PROBE e1_p1 RESULTS (submission 45834, limit=50 version)

**EMERALDS — fills ONLY at fair±1:**
| Price | Buy fills | Sell fills |
|---|---|---|
| 9993–9998 | **0** | — |
| **9999** | **36 units** | — |
| **10001** | — | **51 units** |
| 10002–10007 | — | **0** |

**MASSIVE FINDING:** The probe posted at 7 price levels per side (9993-9999 and 10001-10007). Only 9999 and 10001 got ANY fills. The bot takers exclusively trade at the tightest price. Wider quotes get ZERO fills.

**Implication for our algo:** Our v1 uses EMERALD_SPREAD=7 (posting at 9993/10007). These prices probably get SOME fills because they're the best available participant quotes, but they're suboptimal. **We should post at 9999/10001 for maximum fill rate.**

**TOMATOES — fills across wide range:**
| Price range | Buys | Sells |
|---|---|---|
| 4979–4989 | 69 units | 33 units |
| 4990–4999 | 20 units | 39 units |
| 5000–5009 | 9 units | 11 units |

98 total bought, 93 total sold. Fills happen at many price levels, concentrated closer to fair. TOMATOES fill mechanics are different from EMERALDS — the bots trade across a wider price range.

**Probe profit:** 395.9 (E: 87, T: 309) — low because qty=3 per level and spread across 7 levels

---

### CRITICAL: Position Limits May Be 80, Not 50
- Backtester source code (`prosperity4bt/data.py`) says: EMERALDS=80, TOMATOES=80
- Our code uses 50 (copied from teammate who may have guessed)
- **If limit is 80, we're using 60% less capacity than allowed**
- NEEDS VERIFICATION: submit a probe that tries to hold 51+ position

### Hidden Fair Value = "Wall Mid"
Top teams discovered PnL is NOT scored against simple mid-price. IMC uses a hidden internal fair value:
- Look for **bid wall** and **ask wall** — price levels with abnormally large quantities
- Average those two prices = "Wall Mid" ≈ hidden fair value
- The rank-2 team (Linear Utility) confirmed by submitting buy-and-hold: PnL matched market maker's mid, not raw mid
- **Our probe e1_p2 is designed to detect this**

### Backtester Fill Modes
The `prosperity4btx` backtester has 3 modes:
- `--match-trades all` (default): matches all trades at or worse than your quotes → **OVERESTIMATES**
- `--match-trades worse`: only matches trades worse than your quotes → **more realistic**
- `--match-trades none`: no trade matching → **underestimates**

Results for e1_v1:
- `all` (default): 23,671
- `worse`: 18,620
- Live: 1,232

Even `worse` mode overestimates by ~15x vs live. The 10x tick count difference explains most of it.

### Matching Engine Sequence (Confirmed)
1. Bot makers place/update quotes
2. Bot takers trade against the book
3. Your algorithm runs — you see the post-bot order book
4. Your aggressive orders (taking) execute against visible book
5. Your passive orders (making) sit for one tick — bots MAY trade against them
6. Unfilled orders cancelled at end of iteration

### Community Tool Findings
- `prosperity4btx` v0.0.2 (what we have) is the main backtester
- jmerle's visualizer exists for P3, P4 version may come later
- Discord community active at discord.gg/SABeB8uKxd

### Strategic Advice from Top Teams
- "Choose parameters from consistent, flat regions" — not maximum backtested profit
- "Ask how the market data could have been generated" before designing strategies
- Simplification improves robustness — compact z-score > complex regression
- Cost/friction analysis essential — many strategies collapse when accounting for them
- Inventory-aware quoting improved PnL by ~20% for one team

---

## 2026-04-03 — What Makes Top Teams Win (Deep Research)

### The Single Biggest Edge In Prosperity History

In Prosperity 2, the **1st place team** discovered that **IMC reused price data from Prosperity 1**. Specifically:
- Diving gear returns from Prosperity 1 (×3 multiplier) predicted roses in Prosperity 2 with **R² = 0.99**
- Coconuts from P1 predicted coconuts in P2 (beta 1.25, R² = 0.99)
- 1st place made **1.2 million SeaShells in a single round** from this
- 2nd place (Linear Utility) built a dynamic programming algo to optimally time trades with future price knowledge → **2.1M SeaShells in Round 5 alone**

**ACTION ITEM: When rounds start, check if Prosperity 3 price data correlates with Prosperity 4 products. This could be game-changing.**

### The "Olivia" Edge — Insider Bot Detection

Both Prosperity 2 and 3 had a bot trader named "Olivia" who traded with insider knowledge:
- Buys at daily lows, sells at daily highs
- Consistently trades exactly 15 lots at price extremes
- 2nd place (Prosperity 3) detected her by tracking trades at running min/max prices
- 9th place built quantitative system: calculated "good trade %" per counterparty over 50-tick rolling window, flagged >95th percentile
- Then copy-traded her: when Olivia buys, you buy. When she sells, you sell.
- Estimated **15-25% profitability boost** from this edge

**ACTION ITEM: When Round 1+ data has counterparty IDs, build Olivia detection immediately.**

### Hidden Fair Value Discovery

The competition marks PnL against a **hidden fair value**, not the simple mid-price:
- Top teams found that filtering for the market-making bot (large sizes, 20-30 lots) and using ITS mid-price was far more accurate
- Verified by submitting a trader that bought 1 unit and held it — PnL matched the market-maker's mid
- **If you don't know what you're being scored against, you can't optimize properly**

### What Separates Top 10 From Top 500

| Top 10 Teams | Top 500 Teams |
|---|---|
| Build custom tooling BEFORE writing strategies | Use default/open-source tools unmodified |
| Investigate WHY strategy works | Only check THAT it works |
| Read ALL previous year writeups | Implement strategies from one writeup |
| Systematically analyze every counterparty | Ignore counterparty data |
| Grid-search parameter landscapes, reject sharp peaks | Find "best" parameters and ship |
| Conscious risk decisions (when to take variance) | Avoid all risk uniformly |
| Adapt strategy every round based on new data | Reuse same approach without changes |
| Treat competition as full-time (hours/day for 15 days) | Spend a few hours total |

### Ranking Progressions of Real Teams

| Team | R1 | R2 | R3 | R4 | Final |
|---|---|---|---|---|---|
| Linear Utility (2nd, P2) | 3rd | 17th | 2nd | 26th | **2nd** |
| Alpha Animals (9th, P3) | 207th | 58th | 2nd | 2nd | **9th** |
| Martin Oravec (73rd, P3) | 806th | 170th | 72nd | 61st | **73rd** |
| Matius Chong (~588th, P3) | 1071st | 1388th | 1033rd | 1340th | **~588th** |

**Pattern: Top teams improve dramatically each round. Average teams plateau.**

### Key Infrastructure Edges

**Custom backtesting (Linear Utility, 2nd place):**
- Automated grid search across all parameter combinations via dictionaries
- Synchronized dashboard: click any timestamp → see orderbook, PnL, position, trades in sync
- Position clearing strategy (0-EV trades to free capacity) → +3% PnL

**Custom visualization (Frankfurt Hedgehogs, 2nd place P3):**
- Scatter-plot orderbook with hoverable tooltips showing who traded what
- Trader filtering: toggle by type (Maker/Small taker/Big taker/Informed/Own)
- "WallMid" indicator as custom proxy for true fair value
- Normalization to overlay indicators without price drift
- This dashboard is HOW they discovered Olivia and volatility smile patterns

**Key insight:** Teams that built custom tooling had faster iteration cycles and could see patterns invisible to generic tools.

### The AI Question

The Prosperity 3 **1st place winner** explicitly said: "Don't over-rely on AI."

Everyone has AI now. It's not an edge. AI helps with:
- Code generation speed (boilerplate, utilities)
- Strategy brainstorming
- Debugging

But winning requires:
- Domain-specific insight AI can't generate from prompts (cross-year data reuse, Olivia detection)
- Judgment under uncertainty (when to abandon a strategy, when to take variance)
- Custom tooling and fast iteration cycles

**Our AI advantage isn't the strategies it generates — it's the speed at which we can iterate.**

### Distraction Data Warning

IMC consistently provides red herring data:
- P2: Sunlight, humidity, tariff data for orchids → mostly noise
- P3: Sunlight index for macarons → teams wasted time on regime modeling
- P3: One team found R² = 99% on linear regression → was overfit

**Rule: Only trade on signals with clear theoretical mechanisms. No blind indicator stacking.**

### Top Writeup Sources (ranked by value)

1. **Frankfurt Hedgehogs (2nd, P3):** `github.com/TimoDiehm/imc-prosperity-3` — best technical writeup
2. **Linear Utility (2nd, P2):** `github.com/ericcccsliu/imc-prosperity-2` — gold standard, DP algo code included
3. **Alpha Animals (9th, P3):** `github.com/CarterT27/imc-prosperity-3` — full trader.py + research notebooks
4. **Stanford Cardinal (2nd, P1):** `github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal` — the OG writeup everyone studies
5. **pe049395 (13th, P2):** `github.com/pe049395/IMC-Prosperity-2024` — Monte Carlo data augmentation approach

---

## 2026-04-03 — Tutorial Data Analysis: TOMATOES & EMERALDS

### Data Capsule Contents
Downloaded from the Prosperity 4 dashboard. Contains 2 days of historical data for the tutorial round:
- `prices_round_0_day_-1.csv` — 20,000 rows (10,000 ticks × 2 products)
- `prices_round_0_day_-2.csv` — 20,000 rows
- `trades_round_0_day_-1.csv` — 631 trades
- `trades_round_0_day_-2.csv` — 588 trades
- Currency: **XIRECS** (not SeaShells — new for Prosperity 4?)
- Buyer/seller info: **anonymized** in tutorial data

### Product: EMERALDS (TG02) — THE STABLE ONE

This is the equivalent of Prosperity 3's "Rainforest Resin". **Free money product.**

| Metric | Day -2 | Day -1 |
|--------|--------|--------|
| Mean mid-price | 10,000.00 | 10,000.00 |
| Min mid | 9,996 | 9,996 |
| Max mid | 10,004 | 10,004 |
| Std dev of mid | — | 0.72 |
| Tick-to-tick volatility | — | 0.9993 |
| Price drift | — | 0.0 |

**Key finding:** Emeralds are pegged to **exactly 10,000**. The mid-price is 10,000 for **96.8%** of all ticks. It only deviates to 9,996 or 10,004 (1.6% each). This is a fixed fair value product.

- Average spread: **15.74** (bid ~9,992, ask ~10,008)
- Trades: ~200/day, avg quantity 5.5
- **Strategy: Market-make with fair value = 10,000. Post bids above 9,992 and asks below 10,008 to capture spread.**

### Product: TOMATOES (TG01) — THE TRENDING ONE

This is the equivalent of Prosperity 3's "Kelp". Price follows a random walk.

| Metric | Day -2 | Day -1 |
|--------|--------|--------|
| Mean mid-price | 5,007.95 | 4,977.57 |
| Min mid | 4,988 | 4,946.5 |
| Max mid | 5,036 | 5,011 |
| Std dev of mid | — | 14.58 |
| Tick-to-tick volatility | — | 1.34 |
| Price drift | — | -49.0 over 10K ticks |

**Key finding:** Tomatoes have meaningful price movement. Day -2 averaged ~5008, Day -1 drifted down to ~4978. This is a trending/mean-reverting product.

- Average spread: **12.98** (tighter than Emeralds)
- Trades: ~400/day, avg quantity 3.4 (more frequent, smaller trades)
- **Strategy: Track mid-price as fair value estimate. Market-make around current mid. Use rolling window to detect trend.**

### Order Book Structure
Both products have **3 levels** of depth on each side:
- Level 1: best bid/ask (smallest quantities)
- Level 2: deeper (larger quantities)
- Level 3: sometimes empty

### Current Score: 3,100 SeaShells
An algorithm has already been uploaded and is active. This is the baseline to improve on.

---

## 2026-04-03 — Initial Deep Research: IMC Prosperity 4

### What Is IMC Prosperity?

IMC Prosperity is a global algorithmic trading competition run by IMC Trading. Teams of up to 5 build Python trading algorithms that run on a simulated exchange against bot market participants. The goal: maximize profit in "SeaShells" (the in-game currency).

**Prosperity 4** (our competition) is the 2026 edition — space-themed. It runs **April 14–30**, with a tutorial round available **March 16–April 13** (we are currently in the tutorial window).

### Competition Structure

- **5 rounds**, each with:
  - 1 **algorithmic challenge** — upload a Python trading algorithm
  - 1 **manual challenge** — puzzle/problem solved directly on the platform
- Algorithmic and manual scores are **independent**
- Teams up to 5 (locked after Round 2)
- **$50,000 USD prize pool**:
  - 1st: $25,000 | 2nd: $10,000 | 3rd: $5,000 | 4th: $3,500 | 5th: $1,500
  - Best Manual Trader: $5,000

### Timeline

| Phase | Dates |
|-------|-------|
| Tutorial Round | Mar 16 – Apr 13 |
| Round 1 | Apr 14–17 |
| Round 2 | Apr 17–20 |
| Intermission | Apr 20–24 |
| Round 3 | Apr 24–26 |
| Round 4 | Apr 26–28 |
| Round 5 | Apr 28–30 |

### How The Algorithm Works

You write a Python class called `Trader` with a `run()` method. Each simulation tick, the engine calls `run()` with a `TradingState` object. You return orders.

**Orders only live for one timestep** — snapshot-based matching, not persistent order book.

### The Prosperity 4 Datamodel (from actual source)

```python
# Type aliases
Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int

class Listing:
    symbol: Symbol
    product: Product
    denomination: int

class ConversionObservation:
    bidPrice: float
    askPrice: float
    transportFees: float
    exportTariff: float
    importTariff: float
    sugarPrice: float
    sunlightIndex: float

class Observation:
    plainValueObservations: Dict[Product, ObservationValue]
    conversionObservations: Dict[Product, ConversionObservation]

class Order:
    symbol: Symbol
    price: int          # integer prices only
    quantity: int       # positive = buy, negative = sell

class OrderDepth:
    buy_orders: Dict[int, int]    # price -> quantity (positive)
    sell_orders: Dict[int, int]   # price -> quantity (negative)

class Trade:
    symbol: Symbol
    price: int
    quantity: int
    buyer: UserId       # can identify bot traders
    seller: UserId
    timestamp: int

class TradingState:
    traderData: str                              # persistent state between ticks (you serialize/deserialize)
    timestamp: Time
    listings: Dict[Symbol, Listing]
    order_depths: Dict[Symbol, OrderDepth]       # current order book per product
    own_trades: Dict[Symbol, List[Trade]]        # your fills since last tick
    market_trades: Dict[Symbol, List[Trade]]     # all market fills since last tick
    position: Dict[Product, Position]            # your current positions
    observations: Observation                    # external data (sugar price, sunlight, etc.)
```

**Key detail: `traderData`** — a string field that persists between ticks. You can serialize state (e.g., price history, moving averages) into this and deserialize it next tick. This is how you maintain memory across iterations.

### Position Limits

- Each product has a **hard position limit**
- Limits are enforced **before** orders match — if your orders would exceed the limit assuming all fill, **ALL orders for that product are cancelled**
- You must account for current position + pending order quantities
- Historical limits from Prosperity 3:
  - Rainforest Resin: 50 (typical stable product)
  - Kelp: 50
  - Squid Ink: 50
  - Basket products: 70
  - Options: varies

### Order Matching

- Sequential processing each tick:
  1. Bot makers place orders
  2. Bot takers take orders
  3. Your algorithm runs and places orders
  4. Your orders match against remaining book
- **You are last in the queue** — bots trade first, you get what's left

### Products From Past Competitions (Pattern Recognition)

**Prosperity 3 (2025) products by round:**
| Round | Products | Type |
|-------|----------|------|
| Tutorial | Rainforest Resin, Kelp | Market-making basics |
| 1 | Rainforest Resin, Kelp, Squid Ink | Market-making + volatility |
| 2 | Croissants, Jams, Djembes, Picnic Baskets 1&2 | ETF/basket arbitrage |
| 3 | Volcanic Rock + Vouchers (options) | Options pricing (Black-Scholes) |
| 4 | Macarons (cross-exchange) | Location/conversion arbitrage |
| 5 | All products + trader identity data | Counterparty analysis |

**Prosperity 2 (2024) products by round:**
| Round | Products | Type |
|-------|----------|------|
| 1 | Amethysts, Starfruit | Market-making |
| 2 | Orchids | Prediction + conversion |
| 3 | Gift Baskets, Chocolate, Strawberries, Roses | Basket arbitrage |
| 4 | Coconuts, Coconut Coupons | Options pricing |
| 5 | Historical trade data | Pattern analysis |

**Pattern:** Every year follows the same progression:
1. Simple market-making (stable + trending products)
2. Basket/ETF arbitrage (index vs components)
3. Options/derivatives pricing
4. Cross-exchange or conversion arbitrage
5. Advanced (counterparty analysis, insider data)

### Strategies That Won (From Top Teams)

#### Market Making (Rounds 1/Tutorial)
- **Rainforest Resin**: Fixed fair value ~10,000. Simple market-making with ~2-4 spread. Consistently produces ~39,000 SeaShells/round.
- **Kelp**: Similar to Resin but price follows slow random walk. Use mid-price from order book as fair value estimate. ~5,000 SeaShells/round.
- **Key**: Take any favorable trades vs current mid, then place passive orders around fair value, neutralize inventory when too large.

#### Mean Reversion (Volatile Products)
- Z-score = (price - mean) / std_dev
- Enter when |z| > 1-2 standard deviations
- EMA-based: (EMA_short - EMA_long) / Std_Dev_long
- Rolling windows of 10-150 ticks depending on product

#### Statistical Arbitrage (Basket Products)
- Compute synthetic basket price from component mid-prices
- Trade when basket diverges from synthetic by > threshold
- Two-way: trade basket vs components in both directions
- PicnicBasket1 = 6 Croissants + 3 Jams + 1 Djembe
- PicnicBasket2 = 4 Croissants + 2 Jams

#### Options Pricing (Derivatives)
- Black-Scholes with zero interest rate assumption
- Per-strike implied volatility estimation
- Volatility smile: fit quadratic curve across strikes
- Delta hedging: rebalance when position drifts outside ±threshold
- Blend global IV curve with rolling per-strike IV estimate

#### Counterparty Analysis (Advanced)
- Market trades include buyer/seller IDs
- Some bots are "insiders" with predictive signals
- 9th place team identified "Olivia" bot as insider, copy-traded her positions
- Statistical win-rate analysis on bot trade history reveals signal quality

### Key Lessons From Past Competitors

1. **Backtester results ≠ live results** — strategies that backtest well can fail live
2. **Simple strategies often win** — fixed fair value market-making on stable products is free money
3. **Position management is critical** — exceed limits and ALL your orders cancel
4. **Orders are integer prices** — no fractional pricing
5. **Bot behavior is consistent** — study the bots, they have patterns
6. **Manual trading matters** — it's independent P&L, can swing rankings
7. **traderData persistence** — use it to maintain rolling averages, price history, state machines
8. **Don't overtrade** — transaction costs eat into profits
9. **Contrarian manual strategies** — in game theory puzzles, avoid the popular/obvious choices
10. **Iterate fast** — small parameter tuning (spread width, window size) dramatically improves Sharpe ratio

### Tools & Resources

- **Community backtester (Prosperity 4)**: `github.com/kevin-fu1/imc-prosperity-4-backtester`
- **Prosperity 3 backtester**: `github.com/jmerle/imc-prosperity-3-backtester` (by jmerle, also built visualizer)
- **Official wiki**: `imc-prosperity.notion.site/prosperity-4-wiki`
- **Discord**: `discord.gg/SABeB8uKxd`
- **Official site**: `prosperity.imc.com`
- **Contact**: prosperity@imc.com

### Sources Consulted
- Prosperity 4 official site and competition page
- Prosperity 4 backtester GitHub (datamodel.py source)
- Prosperity 3 writeup by team that placed 73rd globally (solo)
- Prosperity 3 writeup by Alpha Animals (9th globally, 2nd USA)
- Prosperity 3 writeup by team that placed 588th (detailed strategy evolution)
- Prosperity 2 writeup by David Teather
- Top 100 strategy guide by Shriyan Gosavi
- Multiple GitHub repos with competition code
