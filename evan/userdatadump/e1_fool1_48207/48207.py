"""
e1_fool1 — The Fool Series. Start from zero. No assumptions.

PHILOSOPHY: "Simple market making + unwinding" gets 3,119.
Everything complex we've tried (v11-v15) scored WORSE than v10.
What if the answer is LESS code, not more?

EMERALDS:
  Fair = 10000. Take below, sell above. Unwind at fair.
  Post at mid-1/mid+1. That's it. No penny-jump, no skew, no layers.

TOMATOES:
  Fair = simple mid. Take below, sell above. Unwind at fair.
  Post at mid-3/mid+3. No filtering, no reversion, no ensemble.

Position management: just the hard limit. No skew.
The market handles the rest.

50 lines of actual logic. If this scores > 0, we build up.
If it scores > v10, complexity was the enemy all along.
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}


class Trader:

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)
            if product == "EMERALDS":
                result[product] = self.emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self.tomatoes(od, pos)
        return result, 0, ""

    def emeralds(self, od, pos):
        FAIR = 10000
        P = "EMERALDS"
        orders = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # Take anything mispriced
        for p in sorted(od.sell_orders.keys()):
            if p < FAIR and buy_b > 0:
                q = min(-od.sell_orders[p], buy_b)
                orders.append(Order(P, p, q))
                buy_b -= q; pos += q
            else:
                break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p > FAIR and sell_b > 0:
                q = min(od.buy_orders[p], sell_b)
                orders.append(Order(P, p, -q))
                sell_b -= q; pos -= q
            else:
                break

        # Unwind at fair
        if pos > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[p], sell_b, pos)
                    orders.append(Order(P, p, -q))
                    sell_b -= q; pos -= q
                else:
                    break
        elif pos < 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[p], buy_b, -pos)
                    orders.append(Order(P, p, q))
                    buy_b -= q; pos += q
                else:
                    break

        # Make: simple quotes
        if buy_b > 0:
            orders.append(Order(P, FAIR - 1, buy_b))
        if sell_b > 0:
            orders.append(Order(P, FAIR + 1, -sell_b))

        return orders

    def tomatoes(self, od, pos):
        P = "TOMATOES"
        orders = []

        if not od.buy_orders or not od.sell_orders:
            return orders

        mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2
        fair = round(mid)

        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # Take anything mispriced
        for p in sorted(od.sell_orders.keys()):
            if p < fair and buy_b > 0:
                q = min(-od.sell_orders[p], buy_b)
                orders.append(Order(P, p, q))
                buy_b -= q; pos += q
            else:
                break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p > fair and sell_b > 0:
                q = min(od.buy_orders[p], sell_b)
                orders.append(Order(P, p, -q))
                sell_b -= q; pos -= q
            else:
                break

        # Unwind at fair
        if pos > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= fair and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[p], sell_b, pos)
                    orders.append(Order(P, p, -q))
                    sell_b -= q; pos -= q
                else:
                    break
        elif pos < 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= fair and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[p], buy_b, -pos)
                    orders.append(Order(P, p, q))
                    buy_b -= q; pos += q
                else:
                    break

        # Make: simple quotes around mid
        if pos >= 40:
            buy_b = 0
        if pos <= -40:
            sell_b = 0

        if buy_b > 0:
            orders.append(Order(P, fair - 3, buy_b))
        if sell_b > 0:
            orders.append(Order(P, fair + 3, -sell_b))

        return orders