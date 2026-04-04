"""
e1_crazy14 — claude2 agent
===========================
LESSON LEARNED from crazy12: data-fitted AR ≠ optimal trading params.
LIMITS=80 on TOMATOES is POISON. Stronger reversion fights trends too hard.

This bot: fake1 EXACT TOMATOES + crazy8 EMERALDS.
ONE change: LIMITS["TOMATOES"] = 70 (not 80).
Everything else is byte-for-byte fake1 T code.

This is the clean baseline combination:
  - E: crazy8 (proven 1,050)
  - T: fake1 (proven 1,738 live)
  - Should score: 2,787 (matching fake1)

If this matches fake1's score, we CONFIRM the code is correct.
Then we can try single targeted changes from this baseline.

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 70}  # T=70, NOT 80!
T_ADVOL = 16
T_REVERSION_BETA = -0.229  # proven value, NOT data-fitted

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
                result[product] = self.trade_tomatoes(od, pos, td, state)

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
    # TOMATOES — fake1 EXACT (proven 1,738 live)
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos, td, state):
        P = "TOMATOES"; o = []

        # FILTERED MID (fake1 exact)
        fb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVOL:
                fb = p; break
        fa = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVOL:
                fa = p; break
        if fb is None:
            fb = max(od.buy_orders.keys()) if od.buy_orders else None
        if fa is None:
            fa = min(od.sell_orders.keys()) if od.sell_orders else None
        if fb is None or fa is None:
            return o
        fm = (fb + fa) / 2

        # Multi-timeframe history (fake1 exact)
        hist = td.get("mh", [])
        hist.append(fm)
        if len(hist) > 10:
            hist = hist[-10:]
        td["mh"] = hist

        pm = td.get("pm", fm)
        td["pm"] = fm

        # 1-tick reversion (fake1 exact)
        rev1 = 0
        if pm != 0:
            lr = (fm - pm) / pm
            rev1 = lr * T_REVERSION_BETA

        # 5-tick reversion at half weight (fake1 exact)
        rev5 = 0
        if len(hist) >= 6:
            pm5 = hist[-6]
            if pm5 != 0:
                lr5 = (fm - pm5) / pm5
                rev5 = lr5 * T_REVERSION_BETA * 0.5

        # Market trades flow signal (fake1 exact)
        flow_adj = 0
        mt = state.market_trades.get("TOMATOES", [])
        if mt:
            buy_vol = 0; sell_vol = 0
            mid = (fb + fa) / 2
            for t in mt:
                if t.price >= mid:
                    buy_vol += t.quantity
                else:
                    sell_vol += t.quantity
            total = buy_vol + sell_vol
            if total > 0:
                flow = (buy_vol - sell_vol) / total
                flow_adj = flow * 2.0

        fair = round(fm * (1 + rev1 + rev5) + flow_adj)

        bb = LIMITS[P] - pos; sb = LIMITS[P] + pos

        # TAKE (fake1 exact)
        for p in sorted(od.sell_orders.keys()):
            if p <= fair - 1 and bb > 0:
                q = min(-od.sell_orders[p], bb)
                o.append(Order(P, p, q)); bb -= q; pos += q
            else: break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= fair + 1 and sb > 0:
                q = min(od.buy_orders[p], sb)
                o.append(Order(P, p, -q)); sb -= q; pos -= q
            else: break

        # CLEAR (fake1 exact)
        if pos > 0 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= fair and sb > 0 and pos > 0:
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0: o.append(Order(P, p, -q)); sb -= q; pos -= q
                else: break
        if pos < 0 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= fair and bb > 0 and pos < 0:
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0: o.append(Order(P, p, q)); bb -= q; pos += q
                else: break

        # MAKE — penny-jump (fake1 exact)
        baa = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair + 1: baa = p; break
        bbb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - 1: bbb = p; break
        if bbb is not None:
            bidp = bbb + 1
        else:
            bidp = fair - 2
        bidp = min(bidp, fair - 1)
        if baa is not None:
            askp = baa - 1
        else:
            askp = fair + 2
        askp = max(askp, fair + 1)

        # Hard limit (fake1 exact: 70, not 80)
        if pos >= 70: bb = 0
        if pos <= -70: sb = 0

        if bb > 0:
            o.append(Order(P, bidp, bb))
        if sb > 0:
            o.append(Order(P, askp, -sb))

        return o

    @staticmethod
    def _obi(od) -> float:
        if not od.buy_orders or not od.sell_orders: return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0
