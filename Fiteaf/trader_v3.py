"""
trader_v3.py — IMC Prosperity 4 Tutorial Round
================================================
Products: EMERALDS (stationary ~10,000) and TOMATOES (drifting ~5,000)

SYNTHESIS OF TOP STRATEGIES:
  - Frankfurt Hedgehogs (2nd, Prosperity 3): Wall Mid fair value, penny-jumping,
    zero-lookback for drifting products, flatten at fair.
  - Linear Utility (2nd, Prosperity 2): TAKE → CLEAR → MAKE pipeline, adverse
    selection filter (skip large orders), mean-reversion on MM-mid returns,
    penny/join framework.
  - Stanford Cardinal (2nd, Prosperity 1): Undercut best bid/ask, 3-tier position-
    aware quote placement, LR(4) for drifting products.
  - Evan e1_v4 (team best, 1,232 SS): LR(10) + OBI, wide spread=7/6, skew 0.10/0.20.
  - Our v1 (1,076 SS): LR(10), spread=3 (too tight), skew 0.15/0.20.

KEY CHANGES IN V3:
  1. Wall Mid as primary fair value input (Frankfurt/Linear Utility consensus).
  2. 3-phase pipeline: TAKE → CLEAR → MAKE (Linear Utility, Stanford).
  3. Penny-jumping for MAKE (Frankfurt, Stanford, Linear Utility — unanimous).
  4. Adverse selection filter on takes for TOMATOES (Linear Utility).
  5. Adaptive spread based on realized volatility (new).
  6. Momentum detection: widen spread in trending ticks (Evan OBI insight + new).
  7. Multi-level quoting with inventory-aware sizing.
  8. LR(4) on wall-mids for TOMATOES (Stanford lookback + Frankfurt input).
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

from typing import Dict, List
import json
import math


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# ── EMERALDS parameters ─────────────────────────────────────────────────────
# Fair value is known: 10,000. The bot spread is ~9992/10008 (walls).
# We penny-jump inside those walls. Take anything mispriced.
E_FAIR = 10_000

# Take: sweep any ask <= 9999 or bid >= 10001 (unanimous across all winners).
E_TAKE_EDGE = 1

# Clear: trade at exactly 10,000 to flatten inventory (Linear Utility, Stanford).
# Only triggered when we have nonzero position.
E_CLEAR_EDGE = 0

# Make: penny-jump best bid/ask, clamped to never cross fair.
# Fallback spread if book is empty or only walls visible.
# Evan used 7 (too wide — only 16 fills). v1 used 3 (too tight — adverse selection).
# Frankfurt penny-jumped to wall+1 ≈ 9993/10007 with fills at ~39K SS/round.
# We penny-jump adaptively; this is the fallback if no level to penny.
E_DEFAULT_EDGE = 4  # bid 9996 / ask 10004 if no penny target exists

# Disregard levels within this distance of fair for penny purposes.
# (Linear Utility: disregard_edge=1 — don't penny a 9999 bid to 10000)
E_DISREGARD = 1

# Inventory skew: soft, position-aware quote adjustment.
# Stanford used 3 tiers. We use continuous skew like Evan (0.10) but slightly
# stronger to compensate for our tighter quotes catching more fills.
E_SKEW = 0.12

# Soft position limit: when |pos| exceeds this, tighten the offsetting side
# by 1 tick (Linear Utility technique, soft_position_limit=10 for pos limit 20,
# scaled to our limit of 50 → threshold at 25).
E_SOFT_LIMIT = 25

# Multi-level: split make qty across 2 layers.
# Layer 1 = penny-jump price, Layer 2 = 2 ticks further back.
E_LAYER2_OFFSET = 2
E_LAYER1_PCT = 0.65  # 65% of capacity at layer 1, 35% at layer 2

# ── TOMATOES parameters ─────────────────────────────────────────────────────
# Drifting product. Fair value from Wall Mid + short LR for trend extrapolation.

# LR lookback: Stanford used 4 (81% weight on most recent price), Frankfurt
# used 0 (current book only). We use 4 as a compromise — captures short trend
# without the 10-tick lag that hurt our v1.
T_LR_LOOKBACK = 4

# History buffer: keep extra ticks for volatility estimation.
T_HIST_BUFFER = 20

# Take edge: only take orders that are clearly mispriced vs our fair value.
T_TAKE_EDGE = 1

# Adverse selection filter: skip resting orders with volume >= this threshold.
# Large orders are from the informed MM bot (Linear Utility insight, their
# threshold was 15 for a limit of 20; we scale to our limit of 50).
T_ADVERSE_VOL = 15

# Clear: flatten at fair value when we have inventory (same as EMERALDS).
T_CLEAR_EDGE = 0

# Make: penny-jump, with adaptive spread based on recent volatility.
T_DEFAULT_EDGE = 3       # fallback if nothing to penny
T_MIN_EDGE = 2           # floor: never quote tighter than fair ± 2
T_MAX_EDGE = 6           # ceiling: never quote wider than fair ± 6 (Evan's level)
T_DISREGARD = 1          # ignore levels within 1 tick of fair for penny

# Volatility-adaptive spread: measure stddev of recent wall-mids.
# High vol → widen spread to avoid adverse selection.
# Low vol → tighten spread to capture more fills.
T_VOL_LOOKBACK = 10      # ticks for volatility estimation
T_VOL_SPREAD_SCALE = 1.5 # multiplier: spread = base + scale * (vol / avg_vol - 1)

# Inventory skew: stronger than EMERALDS because price drifts.
T_SKEW = 0.18

# Soft position limit for tightening offsetting quotes.
T_SOFT_LIMIT = 25

# Multi-level quoting.
T_LAYER2_OFFSET = 2
T_LAYER1_PCT = 0.65

# Momentum: if LR slope exceeds this, widen the side we'd be quoting INTO
# the trend (avoid adverse selection on trending ticks). Inspired by Evan's
# OBI idea but using price trend directly.
T_MOMENTUM_THRESHOLD = 1.5  # ticks per step


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def wall_mid(od: OrderDepth):
    """
    Frankfurt Hedgehogs' key innovation: fair value from the DEEPEST levels in
    the book (the "walls"), not the top-of-book. The market-maker bots place
    large orders at rounded prices around the true value. The deepest bid and
    deepest ask are the most stable and informative.

    Source: TimoDiehm/imc-prosperity-3 — "The raw mid-price is heavily distorted
    by overbidding/undercutting from other participants."
    """
    if not od.buy_orders or not od.sell_orders:
        return None
    bid_wall = min(od.buy_orders.keys())   # deepest (worst/lowest) bid
    ask_wall = max(od.sell_orders.keys())   # deepest (worst/highest) ask
    return (bid_wall + ask_wall) / 2.0


def simple_mid(od: OrderDepth):
    """Standard mid: (best_bid + best_ask) / 2."""
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2.0


def max_vol_mid(od: OrderDepth):
    """
    pe049395 (13th, Prosperity 2): fair value from the price levels with the
    largest resting volume on each side. The hidden fair value used for PnL
    scoring correlates with these levels.
    """
    if not od.buy_orders or not od.sell_orders:
        return None
    max_bid = max(od.buy_orders.keys(), key=lambda p: od.buy_orders[p])
    max_ask = min(od.sell_orders.keys(), key=lambda p: abs(od.sell_orders[p]))
    return (max_bid + max_ask) / 2.0


def linreg(prices):
    """
    Linear regression: fit y = a + bx, extrapolate 1 step ahead.
    Stanford Cardinal used this with lookback=4. Returns (predicted_next, slope).
    """
    n = len(prices)
    if n < 2:
        return prices[-1], 0.0
    mx = (n - 1) / 2.0
    my = sum(prices) / n
    cov = sum((i - mx) * (p - my) for i, p in enumerate(prices))
    var = sum((i - mx) ** 2 for i in range(n))
    if var == 0:
        return prices[-1], 0.0
    b = cov / var
    a = my - b * mx
    return a + b * n, b  # (extrapolated value, slope per tick)


def stddev(values):
    """Simple population standard deviation."""
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def best_bid_ask(od: OrderDepth):
    """Return (best_bid, best_ask) or (None, None)."""
    bb = max(od.buy_orders.keys()) if od.buy_orders else None
    ba = min(od.sell_orders.keys()) if od.sell_orders else None
    return bb, ba


# ══════════════════════════════════════════════════════════════════════════════
# EMERALDS STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

def trade_emeralds(od: OrderDepth, pos: int, td: dict) -> List[Order]:
    """
    EMERALDS — 3-phase market making around known fair value 10,000.

    Phase 1 (TAKE):  Sweep every resting order priced favorably.
                     Buy all asks <= 9999, sell all bids >= 10001.
                     Source: unanimous across all 4 winning teams.

    Phase 2 (CLEAR): Trade at exactly 10,000 to flatten inventory.
                     Source: Linear Utility (2nd P2), Stanford (2nd P1),
                     Frankfurt (2nd P3). "Sacrifice edge for reduced risk."

    Phase 3 (MAKE):  Penny-jump best bid/ask to be first in queue for fills
                     from the hidden taker bot. Multi-level quoting with
                     inventory-aware skew.
                     Source: Frankfurt (penny at wall+1), Stanford (undercut
                     best+1), Linear Utility (penny/join framework).
    """
    P = "EMERALDS"
    fair = E_FAIR
    orders: List[Order] = []
    buy_budget = LIMITS[P] - pos
    sell_budget = LIMITS[P] + pos

    # ── PHASE 1: TAKE — sweep full depth of mispriced orders ────────────
    # Buy any ask at or below fair - 1 (i.e., <= 9999).
    # No adverse selection filter needed: fair value is KNOWN with certainty.
    for price in sorted(od.sell_orders.keys()):
        if price <= fair - E_TAKE_EDGE and buy_budget > 0:
            qty = min(-od.sell_orders[price], buy_budget)
            orders.append(Order(P, price, qty))
            buy_budget -= qty
            pos += qty
        else:
            break

    # Sell any bid at or above fair + 1 (i.e., >= 10001).
    for price in sorted(od.buy_orders.keys(), reverse=True):
        if price >= fair + E_TAKE_EDGE and sell_budget > 0:
            qty = min(od.buy_orders[price], sell_budget)
            orders.append(Order(P, price, -qty))
            sell_budget -= qty
            pos -= qty
        else:
            break

    # ── PHASE 2: CLEAR — flatten inventory at fair value ────────────────
    # If we're long, sell into any bid at >= fair (10000) to reduce position.
    # If we're short, buy any ask at <= fair (10000) to reduce position.
    # We only clear up to our current position magnitude (don't overshoot).
    # Source: Linear Utility's explicit CLEAR phase; Stanford's "take at fair
    # only to flatten" rule; Frankfurt's "flatten at wall_mid at zero edge."
    if pos > 0 and sell_budget > 0:
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair - E_CLEAR_EDGE and sell_budget > 0 and pos > 0:
                # Only clear up to current long position
                qty = min(od.buy_orders[price], sell_budget, pos)
                if qty > 0:
                    orders.append(Order(P, price, -qty))
                    sell_budget -= qty
                    pos -= qty
            else:
                break

    if pos < 0 and buy_budget > 0:
        for price in sorted(od.sell_orders.keys()):
            if price <= fair + E_CLEAR_EDGE and buy_budget > 0 and pos < 0:
                qty = min(-od.sell_orders[price], buy_budget, -pos)
                if qty > 0:
                    orders.append(Order(P, price, qty))
                    buy_budget -= qty
                    pos += qty
            else:
                break

    # ── PHASE 3: MAKE — penny-jump + multi-level quoting ────────────────
    # Strategy: find the best existing bid/ask from other participants,
    # place our order 1 tick inside them to be first in the fill queue.
    # The "hidden taker bot" periodically crosses the spread — being at the
    # top of the queue means we get filled first.
    #
    # Clamping rules (from Frankfurt + Linear Utility):
    #   - Never bid above fair - 1 (9999) — don't buy at or above fair
    #   - Never ask below fair + 1 (10001) — don't sell at or below fair
    #   - Ignore levels within DISREGARD ticks of fair (they're our own or toxic)

    bb, ba = best_bid_ask(od)

    # === Compute bid price ===
    bid_price = fair - E_DEFAULT_EDGE  # fallback: 9996

    if bb is not None:
        # Find the best bid that's far enough from fair to be meaningful
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - E_DISREGARD:
                # Penny-jump: place 1 tick above this level
                bid_price = p + 1
                break

    # Never bid above fair - 1
    bid_price = min(bid_price, fair - 1)

    # Soft position limit: if heavily long, pull bid back 1 tick (Linear Utility).
    if pos > E_SOFT_LIMIT:
        bid_price -= 1

    # If heavily short, tighten bid by 1 tick to buy back faster (Stanford 3-tier).
    if pos < -E_SOFT_LIMIT:
        bid_price = min(bid_price + 1, fair - 1)

    # === Compute ask price ===
    ask_price = fair + E_DEFAULT_EDGE  # fallback: 10004

    if ba is not None:
        for p in sorted(od.sell_orders.keys()):
            if p > fair + E_DISREGARD:
                # Penny-jump: place 1 tick below this level
                ask_price = p - 1
                break

    # Never ask below fair + 1
    ask_price = max(ask_price, fair + 1)

    # Soft position limit adjustments (mirror of bid logic).
    if pos < -E_SOFT_LIMIT:
        ask_price += 1
    if pos > E_SOFT_LIMIT:
        ask_price = max(ask_price - 1, fair + 1)

    # === Inventory skew: shift both quotes away from our position ===
    # Evan used 0.10, our v1 used 0.15. We use 0.12 as a middle ground.
    # Applied AFTER penny-jumping so the penny target sets the base.
    skew = round(pos * E_SKEW)
    bid_price -= skew
    ask_price -= skew

    # Re-clamp after skew to enforce safety bounds
    bid_price = min(bid_price, fair - 1)
    ask_price = max(ask_price, fair + 1)

    # === Multi-level quoting ===
    # Layer 1: penny-jump price (captures hidden taker bot fills)
    # Layer 2: 2 ticks further back (captures larger moves, adds depth)
    if buy_budget > 0:
        l1_qty = max(1, int(buy_budget * E_LAYER1_PCT))
        l2_qty = buy_budget - l1_qty
        orders.append(Order(P, bid_price, l1_qty))
        if l2_qty > 0:
            orders.append(Order(P, bid_price - E_LAYER2_OFFSET, l2_qty))

    if sell_budget > 0:
        l1_qty = max(1, int(sell_budget * E_LAYER1_PCT))
        l2_qty = sell_budget - l1_qty
        orders.append(Order(P, ask_price, -l1_qty))
        if l2_qty > 0:
            orders.append(Order(P, ask_price + E_LAYER2_OFFSET, -l2_qty))

    return orders


# ══════════════════════════════════════════════════════════════════════════════
# TOMATOES STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

def trade_tomatoes(od: OrderDepth, pos: int, td: dict) -> (List[Order], dict):
    """
    TOMATOES — Adaptive market making on a drifting product.

    Fair value: Wall Mid (Frankfurt) fed into LR(4) (Stanford) for short-term
    trend extrapolation. Wall Mid removes top-of-book noise; LR(4) captures
    directional drift without the lag of LR(10).

    Phase 1 (TAKE):  Sweep mispriced orders, but skip large resting orders
                     (adverse selection filter from Linear Utility).
    Phase 2 (CLEAR): Flatten inventory at fair value.
    Phase 3 (MAKE):  Penny-jump with adaptive spread (widens in high vol,
                     tightens in calm) and momentum-aware quote skewing.
    """
    P = "TOMATOES"
    orders: List[Order] = []

    # ── Compute fair value inputs ────────────────────────────────────────
    # Primary: Wall Mid (Frankfurt consensus — deepest levels are most stable).
    # Fallback: simple mid if book is thin.
    wmid = wall_mid(od)
    smid = simple_mid(od)
    mid = wmid if wmid is not None else smid
    if mid is None:
        return orders, td

    # ── Update price history (using wall mids for cleaner LR input) ──────
    hist = td.get("th", [])
    hist.append(mid)
    if len(hist) > T_HIST_BUFFER:
        hist = hist[-T_HIST_BUFFER:]
    td["th"] = hist

    # ── Fair value: LR(4) extrapolation on wall mids ────────────────────
    # Stanford Cardinal used LR(4) with 81% weight on most recent price.
    # Frankfurt used zero lookback (current book only).
    # LR(4) is our compromise: captures short drift, minimal lag.
    if len(hist) >= T_LR_LOOKBACK:
        fair_lr, slope = linreg(hist[-T_LR_LOOKBACK:])
    else:
        fair_lr = mid
        slope = 0.0

    fair = round(fair_lr)
    td["ts"] = slope  # persist slope for debugging

    # ── Compute volatility for adaptive spread ──────────────────────────
    # When price is volatile, widen our spread to avoid getting picked off.
    # When calm, tighten to capture more fills.
    vol = 0.0
    if len(hist) >= T_VOL_LOOKBACK:
        recent = hist[-T_VOL_LOOKBACK:]
        vol = stddev(recent)
    td["tv"] = round(vol, 2)

    # Baseline volatility: ~2 ticks for TOMATOES in calm conditions.
    # If vol > baseline, widen; if vol < baseline, tighten.
    baseline_vol = 2.0
    vol_ratio = vol / baseline_vol if baseline_vol > 0 else 1.0

    # ── Position budgets ────────────────────────────────────────────────
    buy_budget = LIMITS[P] - pos
    sell_budget = LIMITS[P] + pos

    # ── PHASE 1: TAKE — sweep mispriced, with adverse selection filter ──
    # Buy any ask at or below fair - TAKE_EDGE.
    # CRITICAL: skip orders with volume >= T_ADVERSE_VOL. Large resting orders
    # belong to the informed MM bot — taking them = getting adversely selected.
    # Source: Linear Utility (2nd P2), threshold 15 for limit 20.
    for price in sorted(od.sell_orders.keys()):
        if price <= fair - T_TAKE_EDGE and buy_budget > 0:
            available = -od.sell_orders[price]
            # Adverse selection filter: skip large orders from the MM bot
            if available >= T_ADVERSE_VOL:
                continue
            qty = min(available, buy_budget)
            orders.append(Order(P, price, qty))
            buy_budget -= qty
            pos += qty
        else:
            break

    for price in sorted(od.buy_orders.keys(), reverse=True):
        if price >= fair + T_TAKE_EDGE and sell_budget > 0:
            available = od.buy_orders[price]
            if available >= T_ADVERSE_VOL:
                continue
            qty = min(available, sell_budget)
            orders.append(Order(P, price, -qty))
            sell_budget -= qty
            pos -= qty
        else:
            break

    # ── PHASE 2: CLEAR — flatten inventory at fair value ────────────────
    # Same logic as EMERALDS. Zero-edge trades to reduce inventory risk.
    if pos > 0 and sell_budget > 0:
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair - T_CLEAR_EDGE and sell_budget > 0 and pos > 0:
                qty = min(od.buy_orders[price], sell_budget, pos)
                if qty > 0:
                    orders.append(Order(P, price, -qty))
                    sell_budget -= qty
                    pos -= qty
            else:
                break

    if pos < 0 and buy_budget > 0:
        for price in sorted(od.sell_orders.keys()):
            if price <= fair + T_CLEAR_EDGE and buy_budget > 0 and pos < 0:
                qty = min(-od.sell_orders[price], buy_budget, -pos)
                if qty > 0:
                    orders.append(Order(P, price, qty))
                    buy_budget -= qty
                    pos += qty
            else:
                break

    # ── PHASE 3: MAKE — adaptive penny-jump + momentum awareness ────────

    # === Base spread: adaptive to volatility ===
    # Low vol → tighter (more fills). High vol → wider (less adverse selection).
    adaptive_edge = T_DEFAULT_EDGE + round(T_VOL_SPREAD_SCALE * (vol_ratio - 1.0))
    adaptive_edge = max(T_MIN_EDGE, min(T_MAX_EDGE, adaptive_edge))

    bb, ba = best_bid_ask(od)

    # === Compute bid price: penny-jump best existing bid ===
    bid_price = fair - adaptive_edge  # fallback

    if bb is not None:
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - T_DISREGARD:
                bid_price = p + 1
                break

    bid_price = min(bid_price, fair - 1)  # never bid at or above fair

    # === Compute ask price: penny-jump best existing ask ===
    ask_price = fair + adaptive_edge  # fallback

    if ba is not None:
        for p in sorted(od.sell_orders.keys()):
            if p > fair + T_DISREGARD:
                ask_price = p - 1
                break

    ask_price = max(ask_price, fair + 1)  # never ask at or below fair

    # === Momentum detection: avoid quoting into strong trends ===
    # If the LR slope indicates strong upward momentum, widen the ask
    # (we don't want to sell into a rally) and tighten the bid (we want to
    # buy into momentum). Vice versa for downward.
    # Source: Evan's OBI concept (direction-aware quoting), but using LR slope
    # which is a cleaner signal than raw order book imbalance.
    if abs(slope) > T_MOMENTUM_THRESHOLD:
        if slope > 0:
            # Upward momentum: widen ask by 1 (avoid selling into rally),
            # tighten bid by 1 (eager to buy)
            ask_price += 1
            bid_price = min(bid_price + 1, fair - 1)
        else:
            # Downward momentum: widen bid by 1 (avoid buying into selloff),
            # tighten ask by 1 (eager to sell)
            bid_price -= 1
            ask_price = max(ask_price - 1, fair + 1)

    # === Inventory skew ===
    skew = round(pos * T_SKEW)
    bid_price -= skew
    ask_price -= skew

    # === Soft position limit (Linear Utility) ===
    if pos > T_SOFT_LIMIT:
        ask_price = max(ask_price - 1, fair + 1)  # tighten ask to sell faster
        bid_price -= 1                              # widen bid to slow buying
    if pos < -T_SOFT_LIMIT:
        bid_price = min(bid_price + 1, fair - 1)  # tighten bid to buy faster
        ask_price += 1                              # widen ask to slow selling

    # Re-clamp safety bounds
    bid_price = min(bid_price, fair - 1)
    ask_price = max(ask_price, fair + 1)

    # === Multi-level quoting ===
    if buy_budget > 0:
        l1_qty = max(1, int(buy_budget * T_LAYER1_PCT))
        l2_qty = buy_budget - l1_qty
        orders.append(Order(P, bid_price, l1_qty))
        if l2_qty > 0:
            orders.append(Order(P, bid_price - T_LAYER2_OFFSET, l2_qty))

    if sell_budget > 0:
        l1_qty = max(1, int(sell_budget * T_LAYER1_PCT))
        l2_qty = sell_budget - l1_qty
        orders.append(Order(P, ask_price, -l1_qty))
        if l2_qty > 0:
            orders.append(Order(P, ask_price + T_LAYER2_OFFSET, -l2_qty))

    return orders, td


# ══════════════════════════════════════════════════════════════════════════════
# MAIN TRADER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Trader:
    """
    Prosperity 4 entry point. Called every tick with current TradingState.
    Returns (result, conversions, traderData).
    """

    def run(self, state: TradingState):
        # ── Deserialise persistent state ─────────────────────────────────
        td = {}
        if state.traderData:
            try:
                td = json.loads(state.traderData)
            except (json.JSONDecodeError, TypeError):
                td = {}

        result: Dict[str, List[Order]] = {}

        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)

            if product == "EMERALDS":
                result[product] = trade_emeralds(od, pos, td)
            elif product == "TOMATOES":
                orders, td = trade_tomatoes(od, pos, td)
                result[product] = orders

        return result, 0, json.dumps(td)
