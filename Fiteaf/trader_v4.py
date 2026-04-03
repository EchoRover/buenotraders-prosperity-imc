"""
trader_v4.py — IMC Prosperity 4 Tutorial Round
================================================
v3 LIVE RESULTS: Total 1,247 (EMERALDS 867, TOMATOES 380)
  - EMERALDS: 867 >> Evan's 558. Penny-jumping + CLEAR phase = massive win.
  - TOMATOES: 380 << Evan's 674. Wall-mid + LR(4) + penny-jump = UNSTABLE.
    Max drawdown 655, trough at -534. Accumulated huge positions against trend.

v4 CHANGES:
  - EMERALDS: KEEP v3 strategy exactly (penny-jump + CLEAR = proven 867)
  - TOMATOES: STABILIZE. Root causes of v3 instability:
    1. Wall-mid as LR input was noisy (P4 book structure != P3 Frankfurt found)
    2. LR(4) too reactive — overfit to book noise, whipsawed fair value
    3. Penny-jumping got us filled into every move, good or bad
    4. Adverse selection filter blocked legitimate takes
    FIX: Return to Evan's PROVEN P4 approach for fair value (simple mid, LR(10))
    but keep the CLEAR phase and add stronger inventory management.
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

# ── EMERALDS: identical to v3 (live-proven 867 SS) ──────────────────────────
E_FAIR = 10_000
E_TAKE_EDGE = 1
E_CLEAR_EDGE = 0
E_DEFAULT_EDGE = 4
E_DISREGARD = 1
E_SKEW = 0.12
E_SOFT_LIMIT = 25
E_LAYER2_OFFSET = 2
E_LAYER1_PCT = 0.65

# ── TOMATOES: stabilized for smooth curve ────────────────────────────────────
# Fair value: simple mid → LR(10). This is Evan's PROVEN approach that
# produced a monotonically-rising PnL curve with 0 drawdown on live.
# v3 used wall_mid → LR(4) which was catastrophically noisy in P4.
T_LR_LOOKBACK = 10       # Evan's proven lookback (v3 used 4 = too reactive)
T_HIST_BUFFER = 20

# Take: sweep mispriced orders. NO adverse selection filter.
# v3's filter (skip >= 15 lots) blocked profitable takes in P4.
T_TAKE_EDGE = 1

# Clear: flatten at fair (keep from v3 — reduces inventory risk)
T_CLEAR_EDGE = 0

# Make: WIDER spread, NO penny-jumping for TOMATOES.
# v3 penny-jumped → filled into every move → huge position accumulation.
# Evan's spread=6 gave smooth, monotonically-rising live curve.
# Parameter sweep confirmed spread=6 is optimal (beats spread=5 and 7).
T_MAKE_SPREAD = 6

# Inventory skew: 0.15 — same as our proven v1.
# Sweep: 0.08→28K, 0.10→27.8K, 0.12→27.6K, 0.15→27.2K, 0.18→26.6K.
# Lower skew = more backtest profit but more live instability.
# 0.15 is the sweet spot: paired with spread=6 + CLEAR phase, it stays
# stable (Evan used 0.20 with NO clear phase and was rock-solid; we have
# CLEAR as additional safety, so 0.15 is conservative enough).
T_SKEW = 0.15

# Hard inventory brake: when |pos| exceeds this, STOP quoting the side
# that would increase exposure. Only quote to reduce.
T_HARD_LIMIT = 40

# Multi-level: keep 2 layers but with wider offset for safety
T_LAYER2_OFFSET = 2
T_LAYER1_PCT = 0.65


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def simple_mid(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2.0


def wall_mid(od):
    """Frankfurt's approach — used only for EMERALDS penny-jump reference."""
    if not od.buy_orders or not od.sell_orders:
        return None
    return (min(od.buy_orders.keys()) + max(od.sell_orders.keys())) / 2.0


def linreg(prices):
    """LR extrapolation 1 step ahead. Returns (prediction, slope)."""
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
    return a + b * n, b


def best_bid_ask(od):
    bb = max(od.buy_orders.keys()) if od.buy_orders else None
    ba = min(od.sell_orders.keys()) if od.sell_orders else None
    return bb, ba


# ══════════════════════════════════════════════════════════════════════════════
# EMERALDS — exact copy of v3 (proven 867 SS live)
# ══════════════════════════════════════════════════════════════════════════════

def trade_emeralds(od, pos, td):
    P = "EMERALDS"
    fair = E_FAIR
    orders = []
    buy_budget = LIMITS[P] - pos
    sell_budget = LIMITS[P] + pos

    # PHASE 1: TAKE
    for price in sorted(od.sell_orders.keys()):
        if price <= fair - E_TAKE_EDGE and buy_budget > 0:
            qty = min(-od.sell_orders[price], buy_budget)
            orders.append(Order(P, price, qty))
            buy_budget -= qty
            pos += qty
        else:
            break

    for price in sorted(od.buy_orders.keys(), reverse=True):
        if price >= fair + E_TAKE_EDGE and sell_budget > 0:
            qty = min(od.buy_orders[price], sell_budget)
            orders.append(Order(P, price, -qty))
            sell_budget -= qty
            pos -= qty
        else:
            break

    # PHASE 2: CLEAR
    if pos > 0 and sell_budget > 0:
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair - E_CLEAR_EDGE and sell_budget > 0 and pos > 0:
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

    # PHASE 3: MAKE — penny-jump
    bb, ba = best_bid_ask(od)

    bid_price = fair - E_DEFAULT_EDGE
    if bb is not None:
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - E_DISREGARD:
                bid_price = p + 1
                break
    bid_price = min(bid_price, fair - 1)

    if pos > E_SOFT_LIMIT:
        bid_price -= 1
    if pos < -E_SOFT_LIMIT:
        bid_price = min(bid_price + 1, fair - 1)

    ask_price = fair + E_DEFAULT_EDGE
    if ba is not None:
        for p in sorted(od.sell_orders.keys()):
            if p > fair + E_DISREGARD:
                ask_price = p - 1
                break
    ask_price = max(ask_price, fair + 1)

    if pos < -E_SOFT_LIMIT:
        ask_price += 1
    if pos > E_SOFT_LIMIT:
        ask_price = max(ask_price - 1, fair + 1)

    skew = round(pos * E_SKEW)
    bid_price -= skew
    ask_price -= skew
    bid_price = min(bid_price, fair - 1)
    ask_price = max(ask_price, fair + 1)

    if buy_budget > 0:
        l1 = max(1, int(buy_budget * E_LAYER1_PCT))
        l2 = buy_budget - l1
        orders.append(Order(P, bid_price, l1))
        if l2 > 0:
            orders.append(Order(P, bid_price - E_LAYER2_OFFSET, l2))

    if sell_budget > 0:
        l1 = max(1, int(sell_budget * E_LAYER1_PCT))
        l2 = sell_budget - l1
        orders.append(Order(P, ask_price, -l1))
        if l2 > 0:
            orders.append(Order(P, ask_price + E_LAYER2_OFFSET, -l2))

    return orders


# ══════════════════════════════════════════════════════════════════════════════
# TOMATOES — stabilized v4
# ══════════════════════════════════════════════════════════════════════════════

def trade_tomatoes(od, pos, td):
    """
    v4 TOMATOES strategy: Evan's proven fair value (simple mid → LR(10))
    combined with CLEAR phase and stronger inventory management.

    Key differences from v3:
      - simple_mid instead of wall_mid (P4 walls are noisy, not like P3)
      - LR(10) instead of LR(4) (smoother, less reactive to noise)
      - Static spread=5 instead of penny-jumping (prevents over-filling)
      - No adverse selection filter (was blocking good takes)
      - Stronger skew (0.22 vs 0.18) + hard limit at |pos|=40
      - Kept CLEAR phase for inventory flattening at fair
    """
    P = "TOMATOES"
    orders = []

    mid = simple_mid(od)
    if mid is None:
        return orders, td

    # Update history
    hist = td.get("th", [])
    hist.append(mid)
    if len(hist) > T_HIST_BUFFER:
        hist = hist[-T_HIST_BUFFER:]
    td["th"] = hist

    # Fair value: LR(10) on simple mids — Evan's proven approach
    if len(hist) >= T_LR_LOOKBACK:
        fair_lr, slope = linreg(hist[-T_LR_LOOKBACK:])
    else:
        fair_lr = mid
        slope = 0.0

    fair = round(fair_lr)

    buy_budget = LIMITS[P] - pos
    sell_budget = LIMITS[P] + pos

    # PHASE 1: TAKE — sweep all mispriced, no adverse filter
    for price in sorted(od.sell_orders.keys()):
        if price <= fair - T_TAKE_EDGE and buy_budget > 0:
            qty = min(-od.sell_orders[price], buy_budget)
            orders.append(Order(P, price, qty))
            buy_budget -= qty
            pos += qty
        else:
            break

    for price in sorted(od.buy_orders.keys(), reverse=True):
        if price >= fair + T_TAKE_EDGE and sell_budget > 0:
            qty = min(od.buy_orders[price], sell_budget)
            orders.append(Order(P, price, -qty))
            sell_budget -= qty
            pos -= qty
        else:
            break

    # PHASE 2: CLEAR — flatten inventory at fair
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

    # PHASE 3: MAKE — static spread with strong skew + hard limit
    skew = round(pos * T_SKEW)
    bid_price = fair - T_MAKE_SPREAD - skew
    ask_price = fair + T_MAKE_SPREAD - skew

    # Hard inventory brake: if too exposed, only quote to reduce
    if pos >= T_HARD_LIMIT:
        buy_budget = 0  # stop buying
    if pos <= -T_HARD_LIMIT:
        sell_budget = 0  # stop selling

    # Multi-level quoting
    if buy_budget > 0:
        l1 = max(1, int(buy_budget * T_LAYER1_PCT))
        l2 = buy_budget - l1
        orders.append(Order(P, bid_price, l1))
        if l2 > 0:
            orders.append(Order(P, bid_price - T_LAYER2_OFFSET, l2))

    if sell_budget > 0:
        l1 = max(1, int(sell_budget * T_LAYER1_PCT))
        l2 = sell_budget - l1
        orders.append(Order(P, ask_price, -l1))
        if l2 > 0:
            orders.append(Order(P, ask_price + T_LAYER2_OFFSET, -l2))

    return orders, td


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

class Trader:
    def run(self, state: TradingState):
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
