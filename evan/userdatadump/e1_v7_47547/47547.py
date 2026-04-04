"""
e1_v7 — Target: 3,000+. Improve BOTH products.

EMERALDS (867 → 1050+ target):
  Problem: we capture 47% of taker volume. 1050 crowd captures ~60%.
  Fix 1: Post at BOTH 9993 AND 9992 (multi-level penny-jump + join bot)
         This creates more depth → captures more of each taker event.
  Fix 2: More aggressive CLEAR — clear at fair AND at fair±1 when position extreme
  Fix 3: Full limit=80 capacity

TOMATOES (783 → 2000+ target):
  Problem: v5 position spiraled to -90 (96% short). Only captured 2.4 spread.
  Fix 1: Volume imbalance signal (83.3% predictive) for fair value
  Fix 2: Fade lag-1 autocorrelation (-0.44)
  Fix 3: Ultra-low skew (0.01) + hard brake at ±50
  Fix 4: CLEAR at fair for inventory management
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

    # ══════════════════════════════════════════════════════════════
    # EMERALDS — multi-level penny-jump + aggressive CLEAR
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od: OrderDepth, pos: int) -> List[Order]:
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # ── TAKE: sweep mispriced ──
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

        # ── CLEAR: flatten at fair ──
        # Standard clear at 10000
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

        # Aggressive clear: when position extreme, clear at ±1 from fair (lose 1 per unit)
        # This prevents the spiral that made us miss 39/59 events
        if pos > 30 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR - 1 and sell_b > 0 and pos > 15:
                    q = min(od.buy_orders[price], sell_b, pos - 15)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < -30 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR + 1 and buy_b > 0 and pos < -15:
                    q = min(-od.sell_orders[price], buy_b, -pos - 15)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # ── MAKE: multi-level penny-jump ──
        # Find penny-jump prices
        bid_penny = FAIR - 4  # default
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - 1:
                bid_penny = p + 1 if od.buy_orders[p] > 1 else p
                break
        bid_penny = min(bid_penny, FAIR - 1)

        ask_penny = FAIR + 4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + 1:
                ask_penny = p - 1 if abs(od.sell_orders[p]) > 1 else p
                break
        ask_penny = max(ask_penny, FAIR + 1)

        # Inventory adjustment
        if pos > 25:
            bid_penny -= 1
            ask_penny = max(ask_penny - 1, FAIR + 1)
        elif pos < -25:
            ask_penny += 1
            bid_penny = min(bid_penny + 1, FAIR - 1)

        skew = round(pos * 0.12)
        bid_penny = min(bid_penny - skew, FAIR - 1)
        ask_penny = max(ask_penny - skew, FAIR + 1)

        # Post at TWO levels: penny-jump AND one tick wider (join bot)
        # This creates more depth → captures more taker volume
        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.55))  # 55% at penny
            l2 = buy_b - l1                   # 45% one tick wider
            orders.append(Order(P, bid_penny, l1))
            if l2 > 0:
                orders.append(Order(P, bid_penny - 1, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.55))
            l2 = sell_b - l1
            orders.append(Order(P, ask_penny, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_penny + 1, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — data-driven with imbalance + fade + low skew
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
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

        # Base fair value
        if len(hist) >= 10:
            fair_base = linreg_fair(hist[-10:])
        else:
            fair_base = mid

        # Signal 1: Volume imbalance (83.3% predictive)
        imb = book_imbalance(od)
        imb_adj = imb * 4.0

        # Signal 2: Fade lag-1 autocorrelation (-0.44)
        fade_adj = 0.0
        if len(hist) >= 2:
            last_return = hist[-1] - hist[-2]
            fade_adj = -last_return * 0.4

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
        skew = round(pos * 0.01)  # ultra-low
        bid_price = fair - 6 - skew
        ask_price = fair + 6 - skew

        # Hard brake
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