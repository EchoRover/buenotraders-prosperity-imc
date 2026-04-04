"""
BACKTESTER CHAMPION — Swept 100+ combos, best params proven
=============================================================
Backtester score: 33,704 (vs 32,014 baseline = +5.3%)
Projected official sim: ~2,935 (vs 2,787 baseline)

Key findings from sweep:
  - LOWER limit is BETTER (50 > 60 > 70 > 80) — less inventory risk
  - Fixed spread=6 BEATS dynamic spread — more consistent fills
  - Beta=-0.40 marginally best, but beta=0 is nearly tied
  - 2-layer quoting slightly beats 1-layer
  - edge=1 is optimal (edge=0 loses badly, edge=2 slightly worse)

EMERALDS: unchanged (proven 1050 ceiling, identical across all configs)
TOMATOES: limit=50, spread=6 fixed, beta=-0.40, edge=1, 2-layer
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 50}
T_ADVOL = 16
T_BETA = -0.40
T_EDGE = 1
T_SPREAD = 6
T_L1_PCT = 0.65


class Trader:
    def run(self, state: TradingState):
        td = {}
        if state.traderData:
            try: td = json.loads(state.traderData)
            except: td = {}
        result = {}
        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)
            if product == "EMERALDS":
                result[product] = self.te(od, pos)
            elif product == "TOMATOES":
                result[product] = self.tt(od, pos, td)
        return result, 0, json.dumps(td, separators=(',', ':'))

    def te(self, od, pos):
        FAIR = 10000; P = "EMERALDS"; o = []; bb = LIMITS[P] - pos; sb = LIMITS[P] + pos
        # TAKE
        for p in sorted(od.sell_orders.keys()):
            if p <= FAIR - 1 and bb > 0:
                q = min(-od.sell_orders[p], bb); o.append(Order(P, p, q)); bb -= q; pos += q
            else: break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= FAIR + 1 and sb > 0:
                q = min(od.buy_orders[p], sb); o.append(Order(P, p, -q)); sb -= q; pos -= q
            else: break
        # CLEAR
        if pos > 0 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR and sb > 0 and pos > 0:
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0: o.append(Order(P, p, -q)); sb -= q; pos -= q
                else: break
        if pos < 0 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR and bb > 0 and pos < 0:
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0: o.append(Order(P, p, q)); bb -= q; pos += q
                else: break
        # AGGRO CLEAR
        if pos > 20 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR - 1 and sb > 0 and pos > 5:
                    q = min(od.buy_orders[p], sb, pos - 5)
                    if q > 0: o.append(Order(P, p, -q)); sb -= q; pos -= q
                else: break
        if pos < -20 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR + 1 and bb > 0 and pos < -5:
                    q = min(-od.sell_orders[p], bb, -pos - 5)
                    if q > 0: o.append(Order(P, p, q)); bb -= q; pos += q
                else: break
        # MAKE
        bp = FAIR - 4
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - 1: bp = p + 1; break
        bp = min(bp, FAIR - 1)
        ap = FAIR + 4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + 1: ap = p - 1; break
        ap = max(ap, FAIR + 1)
        if pos > 25: bp -= 1; ap = max(ap - 1, FAIR + 1)
        elif pos < -25: ap += 1; bp = min(bp + 1, FAIR - 1)
        bp = min(bp, FAIR - 1); ap = max(ap, FAIR + 1)
        if bb > 0:
            l1 = max(1, int(bb * 0.65)); o.append(Order(P, bp, l1))
            if bb - l1 > 0: o.append(Order(P, bp - 1, bb - l1))
        if sb > 0:
            l1 = max(1, int(sb * 0.65)); o.append(Order(P, ap, -l1))
            if sb - l1 > 0: o.append(Order(P, ap + 1, -(sb - l1)))
        return o

    def tt(self, od, pos, td):
        P = "TOMATOES"; LIM = LIMITS[P]; o = []
        # Fair value: wall-mid + beta reversion
        fb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVOL: fb = p; break
        fa = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVOL: fa = p; break
        if fb is None: fb = max(od.buy_orders.keys()) if od.buy_orders else None
        if fa is None: fa = min(od.sell_orders.keys()) if od.sell_orders else None
        if fb is None or fa is None: return o

        fm = (fb + fa) / 2
        pm = td.get("pm", fm); td["pm"] = fm
        if pm != 0:
            lr = (fm - pm) / pm
            fair = round(fm * (1 + lr * T_BETA))
        else:
            fair = round(fm)

        bb = LIM - pos; sb = LIM + pos
        # TAKE
        for p in sorted(od.sell_orders.keys()):
            if p <= fair - T_EDGE and bb > 0:
                q = min(-od.sell_orders[p], bb); o.append(Order(P, p, q)); bb -= q; pos += q
            else: break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= fair + T_EDGE and sb > 0:
                q = min(od.buy_orders[p], sb); o.append(Order(P, p, -q)); sb -= q; pos -= q
            else: break
        # CLEAR
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
        # MAKE — fixed spread=6, 2-layer (65/35)
        if pos >= LIM: bb = 0
        if pos <= -LIM: sb = 0
        bidp = min(fair - T_SPREAD, fair - 1)
        askp = max(fair + T_SPREAD, fair + 1)
        if bb > 0:
            l1 = max(1, int(bb * T_L1_PCT)); l2 = bb - l1
            o.append(Order(P, bidp, l1))
            if l2 > 0: o.append(Order(P, bidp - 1, l2))
        if sb > 0:
            l1 = max(1, int(sb * T_L1_PCT)); l2 = sb - l1
            o.append(Order(P, askp, -l1))
            if l2 > 0: o.append(Order(P, askp + 1, -l2))
        return o