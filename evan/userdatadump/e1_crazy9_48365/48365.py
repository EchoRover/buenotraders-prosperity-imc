"""
e1_crazy9 — claude2 agent
=========================
2,661 baseline (crazy8). Need +339 for 3,000.

THE CRAZY BET: TAKE_EDGE = 0

We're directional traders (79.5% favorable fills). Every fill is a bet.
Currently TAKE_EDGE=1 means we only bet when price is ≥1 tick mispriced.
What if we bet at FAIR? We lose the 1-tick edge per take, but we make
WAY more bets. 79.5% of those bets pay off directionally.

Math: if take volume doubles and each bet has +EV from direction,
the extra directional profit should dwarf the lost 1-tick edge.

Also: push LIMITS to 80 (from 70). More capacity = more bets.
Also: soft limit to 25 (from 20). Even more room to ride.

EMERALDS: crazy1 exact (1,050, aggressive CLEAR didn't help)

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# TOMATOES — v10 submitted base with crazy changes
T_ADVERSE_VOL = 15
T_REVERSION_BETA = -0.229
T_TAKE_EDGE = 0           # THE BIG BET: take at fair, not fair-1
T_DISREGARD = 1
T_DEFAULT_EDGE = 2
T_SOFT_LIMIT = 25         # from 20, let positions ride even more

# EMERALDS — crazy1 exact (aggressive CLEAR didn't help, go back to 30/15)
E_FAIR = 10_000; E_TAKE_EDGE = 1; E_CLEAR_EDGE = 0
E_DEFAULT_EDGE = 4; E_DISREGARD = 1; E_SKEW = 0.00
E_SOFT_LIMIT = 25; E_L1_PCT = 0.65; E_L2_OFFSET = 1
E_IMB_THRESH = 0.12; E_AGGRO_POS = 30; E_AGGRO_TARG = 15


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
    # EMERALDS — crazy1 exact (proven 1,050)
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
    # TOMATOES — v10 penny-jump + TAKE_EDGE=0 + higher limits
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos, td):
        P = "TOMATOES"; orders = []

        # FILTERED MID (v10 submitted exact)
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p; break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p; break
        if filtered_bid is None:
            filtered_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        if filtered_ask is None:
            filtered_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if filtered_bid is None or filtered_ask is None:
            return orders

        filtered_mid = (filtered_bid + filtered_ask) / 2

        # REVERSION (v10 submitted exact)
        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid

        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_BETA
            fair = round(filtered_mid * (1 + pred_return))
        else:
            fair = round(filtered_mid)

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE — EDGE=0: take at fair, not just below fair
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - T_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q)); buy_b -= q; pos += q
            else: break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + T_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
            else: break

        # CLEAR (v10 submitted exact)
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

        # MAKE — penny-jump (v10 submitted exact)
        best_ask_above = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair + T_DISREGARD:
                best_ask_above = p; break
        best_bid_below = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - T_DISREGARD:
                best_bid_below = p; break

        if best_bid_below is not None:
            bid_price = best_bid_below + 1
        else:
            bid_price = fair - T_DEFAULT_EDGE
        bid_price = min(bid_price, fair - 1)

        if best_ask_above is not None:
            ask_price = best_ask_above - 1
        else:
            ask_price = fair + T_DEFAULT_EDGE
        ask_price = max(ask_price, fair + 1)

        # Soft position limit — raised to 25
        if pos > T_SOFT_LIMIT:
            ask_price = max(ask_price - 1, fair + 1)
        elif pos < -T_SOFT_LIMIT:
            bid_price = min(bid_price + 1, fair - 1)

        # Hard limit — raised to 80
        if pos >= 80: buy_b = 0
        if pos <= -80: sell_b = 0

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