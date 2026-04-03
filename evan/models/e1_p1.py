"""
e1_p1 — PROBE: Fill Rate Mapper + Position Limit Tester

PURPOSE: Two experiments in one:
1. Map fill rates at different price levels (which prices get filled, how often)
2. Test if position limit is 50 or 80 (CRITICAL — we don't know the real limit)

HOW IT WORKS:
- Phase 1 (ticks 0-999): Fill rate mapping
  Posts small orders at 7 price levels per side to see where fills happen.
- Phase 2 (ticks 1000-1500): Position limit test
  Tries to accumulate EMERALDS position beyond 50 to see if orders get cancelled.
  If we successfully hold 51+, limit is >50. If orders cancel at 50, limit is 50.
- Phase 3 (ticks 1500+): Back to fill rate mapping with wider range

Logs everything via traderData for analysis.
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List


def mid_price(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


class Trader:

    def run(self, state: TradingState):
        td = {}
        if state.traderData:
            try:
                td = json.loads(state.traderData)
            except (json.JSONDecodeError, TypeError):
                td = {}

        tick = td.get("tick", 0)
        result: Dict[str, List[Order]] = {}

        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)

            if product == "EMERALDS":
                if 1000 <= tick < 1500:
                    result[product] = self.test_limit_emeralds(od, pos, td)
                else:
                    result[product] = self.probe_fills(od, pos, product, 10000)
            elif product == "TOMATOES":
                mid = mid_price(od)
                fair = round(mid) if mid else 5000
                result[product] = self.probe_fills(od, pos, product, fair)

        # ── LOG STATE ──
        td["tick"] = tick + 1
        td["ts"] = state.timestamp
        td["e_pos"] = state.position.get("EMERALDS", 0)
        td["t_pos"] = state.position.get("TOMATOES", 0)

        # Track max positions seen (for limit testing)
        td["e_max"] = max(td.get("e_max", 0), abs(state.position.get("EMERALDS", 0)))
        td["t_max"] = max(td.get("t_max", 0), abs(state.position.get("TOMATOES", 0)))

        # Accumulate fill counts per price per product
        for product in ["EMERALDS", "TOMATOES"]:
            trades = state.own_trades.get(product, [])
            key = f"{product[0].lower()}_fills"
            fills = td.get(key, {})
            for trade in trades:
                p = str(trade.price)
                fills[p] = fills.get(p, 0) + abs(trade.quantity)
            td[key] = fills

        # Track total fill volume per product
        for product in ["EMERALDS", "TOMATOES"]:
            trades = state.own_trades.get(product, [])
            key = f"{product[0].lower()}_vol"
            td[key] = td.get(key, 0) + sum(abs(t.quantity) for t in trades)

        return result, 0, json.dumps(td)

    def probe_fills(self, od, pos: int, product: str, fair: int) -> list:
        """Post small orders at 7 price levels per side."""
        orders = []
        QTY = 3

        # Use 50 as conservative limit (we're testing if it's actually 80)
        buy_budget = 50 - pos
        sell_budget = 50 + pos

        for offset in range(1, 8):
            price = fair - offset
            qty = min(QTY, buy_budget)
            if qty > 0:
                orders.append(Order(product, price, qty))
                buy_budget -= qty

        for offset in range(1, 8):
            price = fair + offset
            qty = min(QTY, sell_budget)
            if qty > 0:
                orders.append(Order(product, price, -qty))
                sell_budget -= qty

        return orders

    def test_limit_emeralds(self, od, pos: int, td: dict) -> list:
        """
        Try to accumulate beyond 50 EMERALDS to test position limit.
        Buy aggressively at best ask to build position.
        """
        orders = []

        # Log what we're attempting
        td["limit_test"] = td.get("limit_test", [])

        if pos < 80:
            # Try to buy up to 80 — if limit is 50 this will get cancelled at 50
            best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
            if best_ask is not None:
                # Try to buy enough to push past 50
                want = min(10, 80 - pos)
                if want > 0:
                    orders.append(Order("EMERALDS", best_ask, want))

        # Log attempt
        if len(td["limit_test"]) < 20:
            td["limit_test"].append({"tick": td.get("tick", 0), "pos": pos, "orders": len(orders)})

        return orders
