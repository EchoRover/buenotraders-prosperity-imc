"""
e1_p3 — EXPERIMENTAL: Directional trend-riding on TOMATOES.

HYPOTHESIS: Instead of pure market-making, detect the day's trend direction
early and accumulate a LARGE directional position. Hold through the trend.
Market-make EMERALDS normally for base income.

If TOMATOES trends down 50 points and we hold -80 (short), that's 4,000 PnL
from direction alone. Even half that = 2,000 — more than all our market making.

RISK: If trend reverses, we lose big. But position limit (80) caps downside.

This probe tests pure directional trading to see how much PnL direction gives.
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# EMERALDS: same penny-jump as v5
E_FAIR = 10000
E_TAKE_EDGE = 1
E_DISREGARD = 1
E_DEFAULT_EDGE = 4
E_SKEW = 0.12
E_SOFT_LIM = 25
E_L1_PCT = 0.65
E_L2_OFFSET = 2

# TOMATOES: trend-riding mode
T_TREND_WINDOW = 100    # ticks to detect trend
T_TREND_THRESHOLD = 3   # min mid-price change to declare trend
T_SPREAD = 6
T_SKEW = 0.03
T_LR_LOOKBACK = 10
T_L1_PCT = 0.65
T_L2_OFFSET = 2


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
        """Same as v5 — proven penny-jump + CLEAR."""
        FAIR = E_FAIR
        P = "EMERALDS"
        orders = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - E_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q; pos += q
            else:
                break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + E_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q; pos -= q
            else:
                break

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

        bid_price = FAIR - E_DEFAULT_EDGE
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - E_DISREGARD:
                bid_price = p + 1 if od.buy_orders[p] > 1 else p
                break
        bid_price = min(bid_price, FAIR - 1)
        ask_price = FAIR + E_DEFAULT_EDGE
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + E_DISREGARD:
                ask_price = p - 1 if abs(od.sell_orders[p]) > 1 else p
                break
        ask_price = max(ask_price, FAIR + 1)

        if pos > E_SOFT_LIM:
            bid_price -= 1; ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -E_SOFT_LIM:
            ask_price += 1; bid_price = min(bid_price + 1, FAIR - 1)

        skew = round(pos * E_SKEW)
        bid_price = min(bid_price - skew, FAIR - 1)
        ask_price = max(ask_price - skew, FAIR + 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * E_L1_PCT))
            orders.append(Order(P, bid_price, l1))
            if buy_b - l1 > 0:
                orders.append(Order(P, bid_price - E_L2_OFFSET, buy_b - l1))
        if sell_b > 0:
            l1 = max(1, int(sell_b * E_L1_PCT))
            orders.append(Order(P, ask_price, -l1))
            if sell_b - l1 > 0:
                orders.append(Order(P, ask_price + E_L2_OFFSET, -(sell_b - l1)))

        return orders

    def trade_tomatoes(self, od, pos, td):
        """
        Hybrid: market-make normally + detect trend + ride it.

        Early ticks (0-200): pure market making, collect data
        After 200 ticks: if trend detected, bias quotes heavily in trend direction
        Last 300 ticks: try to accumulate max position in trend direction for mark-to-market
        """
        P = "TOMATOES"
        orders = []

        mid = mid_price(od)
        if mid is None:
            return orders

        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 200:
            hist = hist[-200:]
        td["h"] = hist

        tick = len(hist)

        # Fair value from linreg
        lb = min(T_LR_LOOKBACK, len(hist))
        fair = round(linreg_fair(hist[-lb:])) if lb >= 3 else round(mid)

        # Detect trend direction
        trend = 0  # -1 = down, 0 = none, +1 = up
        if len(hist) >= T_TREND_WINDOW:
            price_change = hist[-1] - hist[-T_TREND_WINDOW]
            if price_change > T_TREND_THRESHOLD:
                trend = 1
            elif price_change < -T_TREND_THRESHOLD:
                trend = -1

        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # ── PHASE 1: TAKE ──
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

        # ── PHASE 2: CLEAR (only when NOT riding a trend) ──
        if trend == 0 or (trend == 1 and pos > 0) or (trend == -1 and pos < 0):
            # Clear only if we're not positioned WITH the trend
            pass  # keep position when aligned with trend
        else:
            # Clear when no trend or positioned against trend
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

        # ── PHASE 3: MAKE — trend-biased ──
        skew = round(pos * T_SKEW)

        # Trend bias: shift quotes to accumulate in trend direction
        trend_shift = 0
        if trend == 1:
            trend_shift = 2   # shift up → buy more aggressively, sell less
        elif trend == -1:
            trend_shift = -2  # shift down → sell more aggressively, buy less

        bid_price = fair - T_SPREAD - skew + trend_shift
        ask_price = fair + T_SPREAD - skew + trend_shift

        # Hard brake only AGAINST trend
        if trend >= 0 and pos >= 70:
            buy_b = 0
        if trend <= 0 and pos <= -70:
            sell_b = 0
        # Less aggressive brake when WITH trend
        if trend == 1 and pos >= LIMITS[P]:
            buy_b = 0
        if trend == -1 and pos <= -LIMITS[P]:
            sell_b = 0

        # Two-layer quoting
        if buy_b > 0:
            l1 = max(1, int(buy_b * T_L1_PCT))
            l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0:
                orders.append(Order(P, bid_price - T_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * T_L1_PCT))
            l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_price + T_L2_OFFSET, -(sell_b - l1)))

        return orders
