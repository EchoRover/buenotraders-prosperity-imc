"""e1_v1 — Tutorial round. EMERALDS fixed fair value + TOMATOES linear regression."""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

# Position limits per product
LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# Tuned via parameter sweep on tutorial data
EMERALD_SPREAD = 7       # make spread half-width from fair
EMERALD_SKEW = 0.10      # inventory skew factor
TOMATO_SPREAD = 6        # make spread half-width from fair
TOMATO_SKEW = 0.20       # inventory skew factor (stronger — price drifts)
TOMATO_LR_LOOKBACK = 10  # linear regression window


def clamp_qty(product: str, pos: int, qty: int) -> int:
    """Clip order qty so position stays within limits."""
    limit = LIMITS.get(product, 50)
    if qty > 0:
        return max(0, min(qty, limit - pos))
    return min(0, max(qty, -(limit + pos)))


def mid_price(od: OrderDepth):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def linreg_fair(prices: list) -> float:
    """Linear regression extrapolation 1 step ahead."""
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

    def trade_emeralds(self, od: OrderDepth, pos: int) -> List[Order]:
        """Fixed fair value market-making at 10000."""
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []

        # TAKE: sweep mispriced orders
        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - 1:
                qty = clamp_qty(P, pos, -od.sell_orders[price])
                if qty > 0:
                    orders.append(Order(P, price, qty))
                    pos += qty
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + 1:
                qty = clamp_qty(P, pos, -od.buy_orders[price])
                if qty < 0:
                    orders.append(Order(P, price, qty))
                    pos += qty
            else:
                break

        # MAKE: passive quotes with inventory skew
        skew = round(pos * EMERALD_SKEW)
        bid_price = FAIR - EMERALD_SPREAD - skew
        ask_price = FAIR + EMERALD_SPREAD - skew

        bid_qty = clamp_qty(P, pos, LIMITS[P] - pos)
        ask_qty = clamp_qty(P, pos, -(LIMITS[P] + pos))

        if bid_qty > 0:
            orders.append(Order(P, bid_price, bid_qty))
        if ask_qty < 0:
            orders.append(Order(P, ask_price, ask_qty))

        return orders

    def trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        """Linear regression fair value market-making."""
        P = "TOMATOES"
        orders: List[Order] = []

        mid = mid_price(od)
        if mid is None:
            return orders

        # Track price history
        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 20:
            hist = hist[-20:]
        td["h"] = hist

        # Fair value: linreg extrapolation or current mid
        if len(hist) >= TOMATO_LR_LOOKBACK:
            fair = round(linreg_fair(hist[-TOMATO_LR_LOOKBACK:]))
        else:
            fair = round(mid)

        # TAKE: sweep mispriced orders
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - 1:
                qty = clamp_qty(P, pos, -od.sell_orders[price])
                if qty > 0:
                    orders.append(Order(P, price, qty))
                    pos += qty
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + 1:
                qty = clamp_qty(P, pos, -od.buy_orders[price])
                if qty < 0:
                    orders.append(Order(P, price, qty))
                    pos += qty
            else:
                break

        # MAKE: passive quotes with inventory skew
        skew = round(pos * TOMATO_SKEW)
        bid_price = fair - TOMATO_SPREAD - skew
        ask_price = fair + TOMATO_SPREAD - skew

        bid_qty = clamp_qty(P, pos, LIMITS[P] - pos)
        ask_qty = clamp_qty(P, pos, -(LIMITS[P] + pos))

        if bid_qty > 0:
            orders.append(Order(P, bid_price, bid_qty))
        if ask_qty < 0:
            orders.append(Order(P, ask_price, ask_qty))

        return orders