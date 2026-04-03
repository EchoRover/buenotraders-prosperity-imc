"""
e1_v2 — Tutorial round trader.

Changes from v1:
- Fixed position limit bug (separate buy/sell budgets from starting position)
- TOMATOES: VWAP microprice instead of simple mid for better fair value
- TOMATOES: Stricter take threshold (fair±2 instead of ±1) to reduce bad trades
- TOMATOES: Trend-aware spread biasing via linreg slope
- EMERALDS: unchanged (only 16 fills/day live, not worth touching)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# EMERALDS params (unchanged from v1)
E_SPREAD = 7
E_SKEW = 0.10

# TOMATOES params
T_SPREAD = 6
T_SKEW = 0.20
T_TAKE_EDGE = 3        # only take with ≥3 edge (was 1 in v1, 2 in early v2)
T_LR_LOOKBACK = 10
T_TREND_MULT = 1.0     # slope multiplier for trend shift
T_TREND_CAP = 1         # max trend shift in ticks


def vwap_mid(od: OrderDepth):
    """Volume-weighted microprice from top of book."""
    if not od.buy_orders or not od.sell_orders:
        return None
    bb = max(od.buy_orders.keys())
    ba = min(od.sell_orders.keys())
    bv = od.buy_orders[bb]
    av = abs(od.sell_orders[ba])
    if bv + av > 0:
        return (bb * av + ba * bv) / (bv + av)
    return (bb + ba) / 2


def linreg(prices: list):
    """Returns (fair_extrapolated, slope)."""
    n = len(prices)
    if n < 2:
        return prices[-1], 0.0
    mx = (n - 1) / 2
    my = sum(prices) / n
    cov = sum((i - mx) * (p - my) for i, p in enumerate(prices))
    var = sum((i - mx) ** 2 for i in range(n))
    if var == 0:
        return prices[-1], 0.0
    b = cov / var
    fair = (my - b * mx) + b * n
    return fair, b


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
                result[product] = self.trade_emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(od, pos, td)

        return result, 0, json.dumps(td)

    def trade_emeralds(self, od: OrderDepth, pos: int) -> List[Order]:
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []

        # Separate budgets from STARTING position (fix limit bug)
        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - 1 and buy_budget > 0:
                qty = min(-od.sell_orders[price], buy_budget)
                orders.append(Order(P, price, qty))
                buy_budget -= qty
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + 1 and sell_budget > 0:
                qty = min(od.buy_orders[price], sell_budget)
                orders.append(Order(P, price, -qty))
                sell_budget -= qty
            else:
                break

        # MAKE
        skew = round(pos * E_SKEW)
        bp = FAIR - E_SPREAD - skew
        sp = FAIR + E_SPREAD - skew

        if buy_budget > 0:
            orders.append(Order(P, bp, buy_budget))
        if sell_budget > 0:
            orders.append(Order(P, sp, -sell_budget))

        return orders

    def trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        orders: List[Order] = []

        mid = vwap_mid(od)
        if mid is None:
            return orders

        # Track VWAP history
        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 25:
            hist = hist[-25:]
        td["h"] = hist

        # Fair value + trend from linreg
        lookback = min(T_LR_LOOKBACK, len(hist))
        if lookback >= 3:
            fair_raw, slope = linreg(hist[-lookback:])
            fair = round(fair_raw)
            trend_shift = round(slope * T_TREND_MULT)
            trend_shift = max(-T_TREND_CAP, min(T_TREND_CAP, trend_shift))
        else:
            fair = round(mid)
            trend_shift = 0

        # Separate budgets from STARTING position
        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

        # TAKE: stricter threshold (fair ± T_TAKE_EDGE)
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - T_TAKE_EDGE and buy_budget > 0:
                qty = min(-od.sell_orders[price], buy_budget)
                orders.append(Order(P, price, qty))
                buy_budget -= qty
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + T_TAKE_EDGE and sell_budget > 0:
                qty = min(od.buy_orders[price], sell_budget)
                orders.append(Order(P, price, -qty))
                sell_budget -= qty
            else:
                break

        # MAKE: trend-aware spread
        skew = round(pos * T_SKEW)
        bp = fair - T_SPREAD - skew + trend_shift
        sp = fair + T_SPREAD - skew + trend_shift

        if buy_budget > 0:
            orders.append(Order(P, bp, buy_budget))
        if sell_budget > 0:
            orders.append(Order(P, sp, -sell_budget))

        return orders
