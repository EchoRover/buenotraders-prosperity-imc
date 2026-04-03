"""
e1_p2 — PROBE: PnL Scorer / Hidden Fair Value Detector

PURPOSE: Figure out how the competition calculates PnL.
Top teams discovered PnL is scored against a "hidden fair value",
NOT the simple mid-price. This probe tries to detect what that value is.

HOW IT WORKS:
- Phase 1 (first 500 ticks): Buy exactly 1 EMERALD and 1 TOMATO, then hold
- Phase 2 (remaining ticks): Do nothing, just observe PnL changes
- Since we hold a fixed position, PnL changes = changes in the hidden fair value
- By comparing PnL changes to order book mid, we can figure out the scoring model

ALSO TRACKS:
- Full order book state via traderData (best 2 levels each side)
- Market trades (who is trading, at what prices)
- Own trade confirmations

WHAT WE LEARN:
- The hidden fair value function
- Whether PnL is marked to mid, VWAP, or something else
- Bot trading patterns over time
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}


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
        tick = td.get("tick", 0)

        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)

            if product == "EMERALDS":
                result[product] = self.trade_emeralds(od, pos, tick)
            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(od, pos, tick)

        # ── LOG EVERYTHING ──
        td["tick"] = tick + 1
        td["ts"] = state.timestamp

        # Log order book snapshots (sample every 50 ticks to stay under size limit)
        if tick % 50 == 0:
            snapshots = td.get("snaps", [])
            snap = {"t": state.timestamp}
            for product in state.order_depths:
                od = state.order_depths[product]
                bb = max(od.buy_orders.keys()) if od.buy_orders else 0
                ba = min(od.sell_orders.keys()) if od.sell_orders else 0
                bv = od.buy_orders.get(bb, 0)
                av = od.sell_orders.get(ba, 0)
                snap[product[:3]] = {
                    "bb": bb, "ba": ba, "bv": bv, "av": av,
                    "mid": round((bb + ba) / 2, 1) if bb and ba else 0
                }
            snapshots.append(snap)
            # Keep last 40 snapshots
            if len(snapshots) > 40:
                snapshots = snapshots[-40:]
            td["snaps"] = snapshots

        # Log positions
        td["e_pos"] = state.position.get("EMERALDS", 0)
        td["t_pos"] = state.position.get("TOMATOES", 0)

        # Log market trades (sample)
        if tick % 100 == 0:
            mt = td.get("mt", [])
            for product in state.market_trades:
                for trade in state.market_trades[product]:
                    mt.append({
                        "t": trade.timestamp,
                        "p": product[:3],
                        "pr": trade.price,
                        "q": trade.quantity,
                        "b": trade.buyer[:8] if trade.buyer else "",
                        "s": trade.seller[:8] if trade.seller else "",
                    })
            if len(mt) > 50:
                mt = mt[-50:]
            td["mt"] = mt

        return result, 0, json.dumps(td)

    def trade_emeralds(self, od: OrderDepth, pos: int, tick: int) -> List[Order]:
        P = "EMERALDS"
        # Phase 1: buy exactly 1 unit in the first few ticks
        if pos == 0 and tick < 500:
            best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
            if best_ask is not None:
                return [Order(P, best_ask, 1)]
        # Phase 2: hold and observe
        return []

    def trade_tomatoes(self, od: OrderDepth, pos: int, tick: int) -> List[Order]:
        P = "TOMATOES"
        # Phase 1: buy exactly 1 unit in the first few ticks
        if pos == 0 and tick < 500:
            best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
            if best_ask is not None:
                return [Order(P, best_ask, 1)]
        # Phase 2: hold and observe
        return []
