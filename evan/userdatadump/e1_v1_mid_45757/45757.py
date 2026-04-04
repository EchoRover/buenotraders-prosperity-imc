"""e1_v1 — Tutorial round trader. EMERALDS (fixed fair 10000) + TOMATOES (linear regression fair)."""

# Compatible with both competition platform and local backtester
try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
import math
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}


def clamp_qty(product: str, pos: int, qty: int) -> int:
    """Clip order qty so position stays within limits. +qty=buy, -qty=sell."""
    limit = LIMITS.get(product, 50)
    if qty > 0:
        return max(0, min(qty, limit - pos))
    else:
        return min(0, max(qty, -(limit + pos)))


def mid_price(od: OrderDepth) -> float | None:
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def linreg_fair(prices: list[float]) -> float:
    """Linear regression on recent prices, extrapolate 1 step ahead."""
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
    a = my - b * mx
    return a + b * n


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
        orders = []

        # ── TAKE: sweep mispriced orders ──
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

        # ── MAKE: tight spread with inventory skew ──
        skew = round(pos * 0.15)
        bid_price = FAIR - 2 - skew
        ask_price = FAIR + 2 - skew

        bid_qty = clamp_qty(P, pos, LIMITS[P] - pos)
        ask_qty = clamp_qty(P, pos, -(LIMITS[P] + pos))

        if bid_qty > 0:
            orders.append(Order(P, bid_price, bid_qty))
        if ask_qty < 0:
            orders.append(Order(P, ask_price, ask_qty))

        return orders

    def trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        orders = []

        mid = mid_price(od)
        if mid is None:
            return orders

        # Track price history for linear regression
        hist = td.get("t_hist", [])
        hist.append(mid)
        if len(hist) > 20:
            hist = hist[-20:]
        td["t_hist"] = hist

        # Fair value: linreg extrapolation if enough data, else current mid
        if len(hist) >= 8:
            fair = linreg_fair(hist[-10:])
        else:
            fair = mid
        fair = round(fair)

        # ── TAKE ──
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

        # ── MAKE: wider spread, stronger inventory skew ──
        skew = round(pos * 0.20)
        bid_price = fair - 3 - skew
        ask_price = fair + 3 - skew

        bid_qty = clamp_qty(P, pos, LIMITS[P] - pos)
        ask_qty = clamp_qty(P, pos, -(LIMITS[P] + pos))

        if bid_qty > 0:
            orders.append(Order(P, bid_price, bid_qty))
        if ask_qty < 0:
            orders.append(Order(P, ask_price, ask_qty))

        return orders