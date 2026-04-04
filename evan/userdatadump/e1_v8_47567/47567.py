"""
e1_v8 — LADDOO base + fade signal (best in --match-trades worse sweep).

EMERALDS: v5 penny-jump + CLEAR (proven 867)
TOMATOES: LADDOO params (skew=0.01, spread=6, limit=50, hard=50)
         + fade lag-1 autocorrelation (factor=0.4)
         NO imbalance signal (hurt in sweep)

Sweep result: +9.4% over LADDOO in realistic backtester mode.
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}


def mid_price(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def linreg_fair(prices):
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

        return result, 0, json.dumps(td, separators=(',', ':'))

    def trade_emeralds(self, od, pos):
        FAIR = 10000
        P = "EMERALDS"
        orders = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - 1 and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q; pos += q
            else:
                break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + 1 and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q; pos -= q
            else:
                break

        # CLEAR
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # MAKE — penny-jump
        bid_price = FAIR - 4
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - 1:
                bid_price = p + 1 if od.buy_orders[p] > 1 else p
                break
        bid_price = min(bid_price, FAIR - 1)

        ask_price = FAIR + 4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + 1:
                ask_price = p - 1 if abs(od.sell_orders[p]) > 1 else p
                break
        ask_price = max(ask_price, FAIR + 1)

        if pos > 25:
            bid_price -= 1; ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -25:
            ask_price += 1; bid_price = min(bid_price + 1, FAIR - 1)

        skew = round(pos * 0.12)
        bid_price = min(bid_price - skew, FAIR - 1)
        ask_price = max(ask_price - skew, FAIR + 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.65))
            l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0:
                orders.append(Order(P, bid_price - 2, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.65))
            l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_price + 2, -l2))

        return orders

    def trade_tomatoes(self, od, pos, td):
        P = "TOMATOES"
        orders = []

        mid = mid_price(od)
        if mid is None:
            return orders

        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 25:
            hist = hist[-25:]
        td["h"] = hist

        # Fair value: linreg + fade
        if len(hist) >= 10:
            fair_base = linreg_fair(hist[-10:])
        else:
            fair_base = mid

        # Fade lag-1 autocorrelation (the ONE signal that works)
        fade_adj = 0.0
        if len(hist) >= 2:
            last_return = hist[-1] - hist[-2]
            fade_adj = -last_return * 0.4

        fair = round(fair_base + fade_adj)

        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - 1 and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q; pos += q
            else:
                break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + 1 and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q; pos -= q
            else:
                break

        # CLEAR
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # MAKE
        skew = round(pos * 0.01)
        bid_price = fair - 6 - skew
        ask_price = fair + 6 - skew

        if pos >= 50:
            buy_b = 0
        if pos <= -50:
            sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.65))
            l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0:
                orders.append(Order(P, bid_price - 2, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.65))
            l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_price + 2, -l2))

        return orders