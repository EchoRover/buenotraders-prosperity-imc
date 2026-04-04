"""
e1_v6 — Target: 3,000+

Built from deep data analysis of 12 submissions.

KEY FIXES from analysis:
1. EMERALDS: asymmetric pricing to prevent position spiral
   - Bid at penny-jump (9993, profit 7)
   - Ask at tight (10001, profit 1) — keeps position balanced
   - Position was stuck at -31 in v5, missing 39/59 taker events
2. TOMATOES: fix position spiral (v5 ended at -90!)
   - Use 83% accurate volume imbalance signal for fair value
   - Fade lag-1 autocorrelation (-0.44)
   - Hard brake at ±50 (LADDOO ranges [-54, +16])
   - Skew=0.01 to ride trends (LADDOO's approach)
3. Both: limit=80 confirmed
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}


def mid_price(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def book_imbalance(od):
    """83.3% predictive of next tick direction on TOMATOES."""
    if not od.buy_orders or not od.sell_orders:
        return 0.0
    bv = sum(od.buy_orders.values())
    av = sum(abs(v) for v in od.sell_orders.values())
    return (bv - av) / (bv + av) if bv + av > 0 else 0.0


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

    def trade_emeralds(self, od: OrderDepth, pos: int) -> List[Order]:
        """
        Asymmetric penny-jump: different strategy per side based on position.

        When pos >= 0 (long or flat):
          Bid: penny-jump at 9993 (profit 7) — normal
          Ask: tight at 10001 (profit 1) — get fills on every taker buy, prevents long spiral
        When pos < 0 (short):
          Bid: tight at 9999 (profit 1) — get fills on every taker sell, prevents short spiral
          Ask: penny-jump at 10007 (profit 7) — normal

        This keeps position oscillating near zero instead of spiraling.
        """
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # ── TAKE ──
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

        # ── CLEAR at fair ──
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

        # ── MAKE: asymmetric based on position ──
        if pos >= 0:
            # Long/flat: penny-jump bid, tight ask
            bid_price = FAIR - 4  # default
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p < FAIR - 1:
                    bid_price = p + 1 if od.buy_orders[p] > 1 else p
                    break
            bid_price = min(bid_price, FAIR - 1)
            ask_price = FAIR + 1  # tight — gets filled on taker buys, prevents long buildup

            # When getting too long, make ask even more aggressive
            if pos > 30:
                ask_price = FAIR + 1
                bid_price = min(bid_price - 1, FAIR - 2)
        else:
            # Short: tight bid, penny-jump ask
            bid_price = FAIR - 1  # tight — gets filled on taker sells, prevents short buildup
            ask_price = FAIR + 4  # default
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + 1:
                    ask_price = p - 1 if abs(od.sell_orders[p]) > 1 else p
                    break
            ask_price = max(ask_price, FAIR + 1)

            # When getting too short, make bid even more aggressive
            if pos < -30:
                bid_price = FAIR - 1
                ask_price = max(ask_price + 1, FAIR + 2)

        # Two-layer
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

    def trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        """
        Data-driven TOMATOES:
        - Linreg(10) base fair value
        - Volume imbalance adjustment (83.3% predictive)
        - Fade lag-1 autocorrelation (-0.44)
        - Ultra-low skew (0.01) to ride trends
        - Hard brake at ±50
        - CLEAR phase at fair
        """
        P = "TOMATOES"
        orders: List[Order] = []

        mid = mid_price(od)
        if mid is None:
            return orders

        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 25:
            hist = hist[-25:]
        td["h"] = hist

        # Base fair from linreg
        if len(hist) >= 10:
            fair_base = linreg_fair(hist[-10:])
        else:
            fair_base = mid

        # Signal 1: Volume imbalance (83.3% predictive)
        imb = book_imbalance(od)
        imb_adj = imb * 4.0  # aggressive: shift fair by up to ±4 ticks

        # Signal 2: Fade lag-1 autocorrelation (-0.44)
        fade_adj = 0.0
        if len(hist) >= 2:
            last_return = hist[-1] - hist[-2]
            fade_adj = -last_return * 0.4  # fade 40% of last move

        fair = round(fair_base + imb_adj + fade_adj)

        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # ── TAKE ──
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

        # ── CLEAR at fair ──
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

        # ── MAKE ──
        skew = round(pos * 0.01)  # ultra-low skew like LADDOO
        bid_price = fair - 6 - skew
        ask_price = fair + 6 - skew

        # Hard brake at ±50
        if pos >= 50:
            buy_b = 0
        if pos <= -50:
            sell_b = 0

        # Two-layer
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
