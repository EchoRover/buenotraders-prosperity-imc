"""
e1_v4 — Tutorial round. v1 base + order book imbalance signal for TOMATOES.

Changes from v1:
- LIMITS = 80 (confirmed by probe, no downside)
- TOMATOES: order book imbalance adjusts fair value
  If bid volume >> ask volume → buy pressure → fair value nudged up
  If ask volume >> bid volume → sell pressure → fair value nudged down
  This should improve fair value accuracy and reduce adverse selection
- EMERALDS: identical to v1 (spread=7, proven winner)
- Fixed position limit bug (separate buy/sell budgets)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

E_SPREAD = 7
E_SKEW = 0.10

T_SPREAD = 6
T_SKEW = 0.20
T_LR_LOOKBACK = 10
T_IMBALANCE_WEIGHT = 2.0  # max ±2 tick adjustment from order book imbalance


def mid_price(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def book_imbalance(od):
    """Returns -1 to +1. Positive = buy pressure (more bid volume)."""
    if not od.buy_orders or not od.sell_orders:
        return 0.0
    bid_vol = sum(od.buy_orders.values())
    ask_vol = sum(abs(v) for v in od.sell_orders.values())
    total = bid_vol + ask_vol
    if total == 0:
        return 0.0
    return (bid_vol - ask_vol) / total


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
        """Identical to v1 — proven spread=7 approach."""
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []

        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

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

        skew = round(pos * E_SKEW)
        bp = FAIR - E_SPREAD - skew
        sp = FAIR + E_SPREAD - skew

        if buy_budget > 0:
            orders.append(Order(P, bp, buy_budget))
        if sell_budget > 0:
            orders.append(Order(P, sp, -sell_budget))

        return orders

    def trade_tomatoes(self, od, pos: int, td: dict) -> List[Order]:
        """Linreg fair value + order book imbalance adjustment."""
        P = "TOMATOES"
        orders: List[Order] = []

        mid = mid_price(od)
        if mid is None:
            return orders

        # Price history for linreg
        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 20:
            hist = hist[-20:]
        td["h"] = hist

        # Base fair value from linreg
        if len(hist) >= T_LR_LOOKBACK:
            fair_base = linreg_fair(hist[-T_LR_LOOKBACK:])
        else:
            fair_base = mid

        # Order book imbalance adjustment
        # Positive imbalance (more bids) → price likely to rise → nudge fair up
        imb = book_imbalance(od)
        fair_adj = imb * T_IMBALANCE_WEIGHT
        fair = round(fair_base + fair_adj)

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