# Research Notes

Market analysis, data exploration, external references, and findings.

---

## 2026-04-03 — Community Intel & Critical Findings

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
