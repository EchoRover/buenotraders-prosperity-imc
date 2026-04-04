"""
e1_v3 — Tutorial round. Data-driven rebuild from probe results.

Changes from v1:
- LIMITS = 80 (confirmed by probe p1 — reached position 80 without cancellation)
- EMERALD_SPREAD = 1 (probe p1 showed fills ONLY happen at fair±1)
- Hidden fair value ≈ mid-price (probe p2 confirmed, no Wall Mid trick in tutorial)
- Fixed position limit bug (separate buy/sell budgets, from v2)
- Kept v1 strategy base (v2 conservative approach was no better live)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

# CONFIRMED by probe: limit is 80
LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# EMERALDS: probe showed fills only at ±1 from fair
E_SPREAD = 1
E_SKEW = 0.10

# TOMATOES: probe showed fills across wide range, keep wider spread
T_SPREAD = 6
T_SKEW = 0.20
T_LR_LOOKBACK = 10


def mid_price(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def linreg_fair(prices: list) -> float:
    n = len(prices)
    if n < 2:
        return prices[-1]
    mx = (n - 1) / 2
    my = sum(prices) / n
    cov = sum((i - mx) * (p - my) for i, p in enumerate(prices))
    var = sum((i - mx) ** 2 for i in range(n))
    if var == 0:
        return prices[-1]
    b = cov / var
    return (my - b * mx) + b * n


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

    def trade_emeralds(self, od, pos: int) -> List[Order]:
        """
        EMERALDS: fair = 10000, spread = 1.
        Probe showed fills ONLY at 9999/10001. Post there with full capacity.
        """
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []

        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

        # TAKE: sweep anything profitable
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

        # MAKE: tight at ±1, skewed by inventory
        skew = round(pos * E_SKEW)
        bp = FAIR - E_SPREAD - skew
        sp = FAIR + E_SPREAD - skew

        if buy_budget > 0:
            orders.append(Order(P, bp, buy_budget))
        if sell_budget > 0:
            orders.append(Order(P, sp, -sell_budget))

        return orders

    def trade_tomatoes(self, od, pos: int, td: dict) -> List[Order]:
        """
        TOMATOES: linreg fair value, wider spread.
        Probe showed fills across wide price range — keep spread=6.
        """
        P = "TOMATOES"
        orders: List[Order] = []

        mid = mid_price(od)
        if mid is None:
            return orders

        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 20:
            hist = hist[-20:]
        td["h"] = hist

        if len(hist) >= T_LR_LOOKBACK:
            fair = round(linreg_fair(hist[-T_LR_LOOKBACK:]))
        else:
            fair = round(mid)

        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - 1 and buy_budget > 0:
                qty = min(-od.sell_orders[price], buy_budget)
                orders.append(Order(P, price, qty))
                buy_budget -= qty
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + 1 and sell_budget > 0:
                qty = min(od.buy_orders[price], sell_budget)
                orders.append(Order(P, price, -qty))
                sell_budget -= qty
            else:
                break

        # MAKE
        skew = round(pos * T_SKEW)
        bp = fair - T_SPREAD - skew
        sp = fair + T_SPREAD - skew

        if buy_budget > 0:
            orders.append(Order(P, bp, buy_budget))
        if sell_budget > 0:
            orders.append(Order(P, sp, -sell_budget))

        return orders