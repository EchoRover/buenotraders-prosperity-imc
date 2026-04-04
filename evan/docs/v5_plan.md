# v5 Plan — Target: 3,000+

## Current State
- Our best: e1_v1 = 1,232 (E: 558, T: 674)
- LADDOO (teammate): 2,102 (E: 867, T: 1,235)
- Target: 3,000+

## Why We Were Stuck at 1,232

Two problems:
1. **EMERALDS**: No penny-jumping, no CLEAR phase → 558 instead of 867
2. **TOMATOES**: Skew too high (0.20), no CLEAR phase → suppressed profits at 674

## The v5 Strategy — 3 Tiers

### TIER 1: Proven Techniques (from live teammate data)
These are GUARANTEED improvements — proven by 3 teammates on the same simulation.

**1a. EMERALDS: Penny-Jumping + CLEAR (558 → ~1,000)**
- Find best bot bid (e.g., 9992), post OUR bid at 9993 (1 tick better)
- Find best bot ask (e.g., 10008), post OUR ask at 10007
- CLEAR phase: when inventory builds, sell/buy at FAIR (10000) to flatten
- Two-layer: 65% at penny-jump price, 35% at penny-jump - 2
- With LIMIT=80 (vs teammates' 50), we have 60% more capacity

**1b. TOMATOES: Ultra-Low Skew + CLEAR (674 → ~1,600)**
- Drop T_SKEW from 0.20 to 0.01-0.05 — let positions ride trends
- CLEAR phase: flatten inventory at fair when bids/asks available at fair
- Two-layer quoting: 65/35 split
- Keep linreg(10) fair value — proven in our data
- With LIMIT=80, more room for position accumulation before hitting limits

### TIER 2: Novel Signals (to push past LADDOO's 2,102)

**2a. Order Flow Imbalance (OFI)**
Not static book snapshot — tick-to-tick CHANGES in the book:
```
If bid price went UP:    delta_bid = +new_volume
If bid price SAME:       delta_bid = volume_change
If bid price went DOWN:  delta_bid = -old_volume
(same for ask side)
OFI = delta_bid - delta_ask
```
Predicts ~65% of short-term price movement. Use rolling 5-tick OFI to adjust fair value.

**2b. Spread Regime Detection**
TOMATOES spread is BIMODAL:
- 93% of ticks: spread = 13-14 (normal)
- 7% of ticks: spread = 5-9 (taker just hit the book)

When spread is tight → taker was active → price will REVERT in 1-5 ticks (97.8% win rate).
Bias quotes aggressively toward reversion for 3-5 ticks after detecting a tight spread.

**2c. Multi-Level Microprice**
Use all 3 book levels with 1/k² decay weighting:
```
microprice = Σ (1/k²) × (V_bid_k × P_ask_k + V_ask_k × P_bid_k) / Σ (1/k²) × (V_bid_k + V_ask_k)
```
Better fair value than simple mid, especially when taker disrupts level 1.

### TIER 3: Advanced (if Tier 1+2 aren't enough)

**3a. Avellaneda-Stoikov Dynamic Spread**
Replace fixed spread with: `spread = gamma × sigma² × (T-t) + (2/gamma) × ln(1 + gamma/kappa)`
Widens when volatile, tightens when calm. Adds time urgency near session end.

**3b. End-of-Day Position Bias**
Last 500 ticks: detect day's trend direction, accumulate position in trend direction.
Mark-to-market bonus: 80 units × 5 favorable ticks = 400 free SeaShells.

**3c. Autocorrelation Fading**
EMERALDS: strong negative autocorr at lag 1 → fade every move.
TOMATOES: positive autocorr at lags 2-5 → follow momentum.

## Expected P&L Breakdown

| Component | Current | Target | Delta |
|---|---|---|---|
| EMERALDS penny-jump + CLEAR (limit 80) | 558 | ~1,000 | +442 |
| TOMATOES low skew + CLEAR (limit 80) | 674 | ~1,600 | +926 |
| OFI signal bonus | 0 | +200 | +200 |
| Spread regime detection | 0 | +200 | +200 |
| End-of-day position bias | 0 | +200 | +200 |
| **TOTAL** | **1,232** | **~3,200** | **+1,968** |

## Winning Team Code Patterns (from actual source code)

### The 3-Phase Pipeline (Linear Utility, 2nd place P2)
Every tick runs: **TAKE → CLEAR → MAKE**. Each phase updates remaining buy/sell budget.

### Penny-Jump Logic (Frankfurt Hedgehogs, 2nd place P3)
```
For each bid level (highest first):
    if bid < fair - 1:          # ignore bids too close to fair
        if bid_volume > 1:      # penny-jump large orders
            our_bid = bid + 1
        else:                   # join small orders (might be noise)
            our_bid = bid
        break
```

### CLEAR Phase (Linear Utility)
```
After TAKE, calculate position_after_take
If position > 0: sell into any bids >= fair (0 EV, frees capacity)
If position < 0: buy from any asks <= fair (0 EV, frees capacity)
```

### Adverse Volume Filter (Linear Utility — Starfruit/trending products)
Only use order levels with 15+ lots for fair value calculation.
This filters noise and finds the market maker's true mid.

### Key Parameters from Winners
| Team | Product Type | take_width | clear_width | make_edge | skew |
|---|---|---|---|---|---|
| Linear Utility | Stable | 1 | 0 | penny/join/4 | soft_limit=10 |
| Linear Utility | Trending | 1 | 0 | min_edge=2 | none |
| Frankfurt | Stable | wall_mid-1 | at fair if reducing | penny bid_wall+1 | none |
| Alpha Animals | Trending | 1.0 | at fair | 8.0 | via clear |

### Hidden Trick: Linear Utility used mean-reversion for Starfruit
```
reversion_beta = -0.229
last_return = (filtered_mid - prev_mid) / prev_mid
predicted_return = last_return * reversion_beta
fair = filtered_mid * (1 + predicted_return)
```
This means they FADE recent moves — if price just went up, they predict it goes back down.

## Implementation Order
1. Build Tier 1 first (penny-jump + CLEAR + low skew + limit 80)
2. Test live — should hit ~2,500+
3. Add Tier 2 signals (OFI + spread regime + microprice)
4. Test live — should push toward 3,000+
5. Add Tier 3 if needed
