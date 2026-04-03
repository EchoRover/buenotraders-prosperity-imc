"""
e1_p1 — PROBE: Fill Rate Mapper

PURPOSE: Map out exactly where fills happen at different price levels.
This algo sacrifices PnL to gather INFORMATION about the matching engine.

HOW IT WORKS:
- Posts small orders (qty=3) at many price levels simultaneously
- EMERALDS: bids from 9993-9999, asks from 10001-10007
- TOMATOES: bids from fair-7 to fair-1, asks from fair+1 to fair+7
- Logs fill information via traderData for analysis
- After each tick, records which prices got filled and how much

WHAT WE LEARN:
- Fill rate as a function of distance from fair value
- Whether closer-to-fair orders get filled more often
- How many units get filled per tick at each level
- The effective "supply/demand curve" of the bots
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}
QTY_PER_LEVEL = 3  # small qty per price level to spread across many prices


def mid_price(od: OrderDepth):
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

        result: Dict[str, List[Order]] = {}

        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)

            if product == "EMERALDS":
                result[product] = self.probe_emeralds(od, pos, td)
            elif product == "TOMATOES":
                result[product] = self.probe_tomatoes(od, pos, td)

        # Log state for analysis
        td["ts"] = state.timestamp
        td["e_pos"] = state.position.get("EMERALDS", 0)
        td["t_pos"] = state.position.get("TOMATOES", 0)

        # Track fill history (which prices got fills)
        e_trades = state.own_trades.get("EMERALDS", [])
        t_trades = state.own_trades.get("TOMATOES", [])

        # Accumulate fill counts per price
        e_fills = td.get("e_fills", {})
        for trade in e_trades:
            p = str(trade.price)
            e_fills[p] = e_fills.get(p, 0) + abs(trade.quantity)
        td["e_fills"] = e_fills

        t_fills = td.get("t_fills", {})
        for trade in t_trades:
            p = str(trade.price)
            t_fills[p] = t_fills.get(p, 0) + abs(trade.quantity)
        td["t_fills"] = t_fills

        # Track total tick count
        td["ticks"] = td.get("ticks", 0) + 1

        return result, 0, json.dumps(td)

    def probe_emeralds(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        FAIR = 10000
        P = "EMERALDS"
        orders: List[Order] = []

        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

        # Post bids at 7 price levels: 9993, 9994, ..., 9999
        for offset in range(1, 8):
            price = FAIR - offset
            qty = min(QTY_PER_LEVEL, buy_budget)
            if qty > 0:
                orders.append(Order(P, price, qty))
                buy_budget -= qty

        # Post asks at 7 price levels: 10001, 10002, ..., 10007
        for offset in range(1, 8):
            price = FAIR + offset
            qty = min(QTY_PER_LEVEL, sell_budget)
            if qty > 0:
                orders.append(Order(P, price, -qty))
                sell_budget -= qty

        return orders

    def probe_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        orders: List[Order] = []

        mid = mid_price(od)
        if mid is None:
            return orders

        fair = round(mid)
        buy_budget = LIMITS[P] - pos
        sell_budget = LIMITS[P] + pos

        # Post bids at 7 levels: fair-1, fair-2, ..., fair-7
        for offset in range(1, 8):
            price = fair - offset
            qty = min(QTY_PER_LEVEL, buy_budget)
            if qty > 0:
                orders.append(Order(P, price, qty))
                buy_budget -= qty

        # Post asks at 7 levels: fair+1, fair+2, ..., fair+7
        for offset in range(1, 8):
            price = fair + offset
            qty = min(QTY_PER_LEVEL, sell_budget)
            if qty > 0:
                orders.append(Order(P, price, -qty))
                sell_budget -= qty

        return orders