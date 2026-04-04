"""
e1_crazy15 — claude2 agent
===========================
STRIPPED DOWN. Less is more.

Mr Nobody gets 3,119 with "simple MM + unwinding." That's MORE than
any fancy model we've built. What if the answer is SIMPLER?

All our T profit is directional (79.5% favorable fills). The reversion,
flow, multi-timeframe signals might be ADDING NOISE to our fair value,
causing worse MAKE placement. Every time fair shifts by 1 tick, our
penny-jump moves too — potentially to a WORSE position.

THE THESIS: Pure filtered mid = the CLEANEST fair value. No reversion
shifting it around. No flow adjusting it. The book structure already
contains all the information. Our penny-jump just needs to be in the
RIGHT place, and it's in the right place when fair = filtered_mid.

What changes vs fake1:
  - REMOVE reversion (both 1-tick and 5-tick)
  - REMOVE market_trades flow signal
  - REMOVE multi-timeframe history
  - KEEP filtered mid (vol >= 16) — this IS the signal
  - KEEP penny-jump MAKE — this IS the edge
  - KEEP all take/clear mechanics

Why this could work LIVE even though Rust shows same score:
  - Cleaner FV = more stable penny-jump placement
  - Less whipsaw on MAKE quotes = better queue position
  - Simpler = fewer edge cases where signals fight each other

Why this could fail:
  - Reversion genuinely helps live (fake1 vs v10: +261)
  - But v10 had LIMITS=50 and soft_limit=10 — was the improvement
    from reversion or from limits? We don't know.

EMERALDS: crazy8 exact (1,050)
TOMATOES: filtered_mid ONLY + penny-jump + LIMITS=70

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 70}
T_ADVOL = 16

# EMERALDS — crazy8 exact
E_FAIR = 10_000; E_TAKE_EDGE = 1; E_CLEAR_EDGE = 0
E_DEFAULT_EDGE = 4; E_DISREGARD = 1
E_SOFT_LIMIT = 25; E_L1_PCT = 0.65; E_L2_OFFSET = 1
E_IMB_THRESH = 0.12; E_AGGRO_POS = 20; E_AGGRO_TARG = 5


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
                result[product] = self.trade_tomatoes(od, pos)

        return result, 0, json.dumps(td, separators=(',', ':'))

    # ══════════════════════════════════════════════════════════════
    # EMERALDS — crazy8 exact (1,050)
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od, pos):
        P = "EMERALDS"; FAIR = E_FAIR; LIM = LIMITS[P]
        orders = []; buy_b = LIM - pos; sell_b = LIM + pos

        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - E_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q)); buy_b -= q; pos += q
            else: break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + E_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
            else: break

        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR - E_CLEAR_EDGE and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR + E_CLEAR_EDGE and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        if pos > E_AGGRO_POS and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR - 1 and sell_b > 0 and pos > E_AGGRO_TARG:
                    q = min(od.buy_orders[price], sell_b, pos - E_AGGRO_TARG)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < -E_AGGRO_POS and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR + 1 and buy_b > 0 and pos < -E_AGGRO_TARG:
                    q = min(-od.sell_orders[price], buy_b, -pos - E_AGGRO_TARG)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        bid_p = FAIR - E_DEFAULT_EDGE
        if od.buy_orders:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p < FAIR - E_DISREGARD: bid_p = p + 1; break
        bid_p = min(bid_p, FAIR - 1)
        ask_p = FAIR + E_DEFAULT_EDGE
        if od.sell_orders:
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + E_DISREGARD: ask_p = p - 1; break
        ask_p = max(ask_p, FAIR + 1)

        if pos > E_SOFT_LIMIT: bid_p -= 1; ask_p = max(ask_p - 1, FAIR + 1)
        if pos < -E_SOFT_LIMIT: ask_p += 1; bid_p = min(bid_p + 1, FAIR - 1)

        imb = self._obi(od)
        if imb > E_IMB_THRESH: ask_p = max(ask_p - 1, FAIR + 1)
        elif imb < -E_IMB_THRESH: bid_p = min(bid_p + 1, FAIR - 1)

        bid_p = min(bid_p, FAIR - 1); ask_p = max(ask_p, FAIR + 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * E_L1_PCT)); l2 = buy_b - l1
            orders.append(Order(P, bid_p, l1))
            if l2 > 0: orders.append(Order(P, bid_p - E_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * E_L1_PCT)); l2 = sell_b - l1
            orders.append(Order(P, ask_p, -l1))
            if l2 > 0: orders.append(Order(P, ask_p + E_L2_OFFSET, -l2))
        return orders

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — STRIPPED DOWN. Pure filtered mid. No signals.
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos):
        P = "TOMATOES"; orders = []

        # ── FILTERED MID — the ONLY signal ──
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVOL:
                filtered_bid = p; break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVOL:
                filtered_ask = p; break
        if filtered_bid is None:
            filtered_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        if filtered_ask is None:
            filtered_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if filtered_bid is None or filtered_ask is None:
            return orders

        fair = round((filtered_bid + filtered_ask) / 2)

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # ── TAKE ──
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - 1 and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q)); buy_b -= q; pos += q
            else: break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + 1 and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
            else: break

        # ── CLEAR ──
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        # ── MAKE — penny-jump (same mechanics, cleaner FV) ──
        best_ask_above = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair + 1:
                best_ask_above = p; break
        best_bid_below = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - 1:
                best_bid_below = p; break

        if best_bid_below is not None:
            bid_price = best_bid_below + 1
        else:
            bid_price = fair - 2
        bid_price = min(bid_price, fair - 1)

        if best_ask_above is not None:
            ask_price = best_ask_above - 1
        else:
            ask_price = fair + 2
        ask_price = max(ask_price, fair + 1)

        if pos >= 70: buy_b = 0
        if pos <= -70: sell_b = 0

        if buy_b > 0:
            orders.append(Order(P, bid_price, buy_b))
        if sell_b > 0:
            orders.append(Order(P, ask_price, -sell_b))

        return orders

    @staticmethod
    def _obi(od) -> float:
        if not od.buy_orders or not od.sell_orders: return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0
