"""
e1_fake2 — Testing LIVE-ONLY effects the Rust backtester can't model.

KEY FINDING: Rust BT shows limit=70 and limit=80 as identical (2770.5).
But LIVE shows limit=80 crashes T to 743 while limit=70 gives T=1738.
The Rust BT is missing a live mechanic.

HYPOTHESIS: The live portal's matching engine reacts to our ORDER SIZE.
When we post large MAKE orders (70 units at one price), the matching
engine might process them differently than smaller orders.

TEST: Same as fake1 but with SMALLER individual order sizes.
Instead of posting buy_b=65 at one price, post 5 orders of 13 each
at the SAME price. Same total exposure but different order structure.

If this scores differently from fake1 live (but same in Rust),
we've found the live-only mechanic.

Also testing: position limit = 60 (between 50 and 70) on TOMATOES.
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 60}  # T=60 — testing between 50 and 70

class Trader:

    def run(self, state):
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
                result[product] = self.tt(od, pos, td, state)
        return result, 0, json.dumps(td, separators=(',', ':'))

    def te(self, od, pos):
        FAIR = 10000; P = "EMERALDS"; o = []; bb = LIMITS[P]-pos; sb = LIMITS[P]+pos
        for p in sorted(od.sell_orders.keys()):
            if p <= FAIR-1 and bb > 0:
                q = min(-od.sell_orders[p], bb); o.append(Order(P, p, q)); bb -= q; pos += q
            else: break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= FAIR+1 and sb > 0:
                q = min(od.buy_orders[p], sb); o.append(Order(P, p, -q)); sb -= q; pos -= q
            else: break
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
        if pos > 20 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR-1 and sb > 0 and pos > 5:
                    q = min(od.buy_orders[p], sb, pos-5)
                    if q > 0: o.append(Order(P, p, -q)); sb -= q; pos -= q
                else: break
        if pos < -20 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR+1 and bb > 0 and pos < -5:
                    q = min(-od.sell_orders[p], bb, -pos-5)
                    if q > 0: o.append(Order(P, p, q)); bb -= q; pos += q
                else: break
        bp = FAIR-4
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR-1: bp = p+1; break
        bp = min(bp, FAIR-1)
        ap = FAIR+4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR+1: ap = p-1; break
        ap = max(ap, FAIR+1)
        if pos > 25: bp -= 1; ap = max(ap-1, FAIR+1)
        elif pos < -25: ap += 1; bp = min(bp+1, FAIR-1)
        bp = min(bp, FAIR-1); ap = max(ap, FAIR+1)
        if bb > 0:
            l1 = max(1, int(bb*0.65)); o.append(Order(P, bp, l1))
            if bb-l1 > 0: o.append(Order(P, bp-1, bb-l1))
        if sb > 0:
            l1 = max(1, int(sb*0.65)); o.append(Order(P, ap, -l1))
            if sb-l1 > 0: o.append(Order(P, ap+1, -(sb-l1)))
        return o

    def tt(self, od, pos, td, state):
        P = "TOMATOES"; o = []
        fb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= 16: fb = p; break
        fa = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= 16: fa = p; break
        if fb is None: fb = max(od.buy_orders.keys()) if od.buy_orders else None
        if fa is None: fa = min(od.sell_orders.keys()) if od.sell_orders else None
        if fb is None or fa is None: return o
        fm = (fb + fa) / 2

        # Multi-timeframe history
        hist = td.get("mh", [])
        hist.append(fm)
        if len(hist) > 10: hist = hist[-10:]
        td["mh"] = hist

        pm = td.get("pm", fm); td["pm"] = fm

        # Reversion
        rev1 = 0
        if pm != 0: rev1 = ((fm - pm) / pm) * -0.229
        rev5 = 0
        if len(hist) >= 6:
            pm5 = hist[-6]
            if pm5 != 0: rev5 = ((fm - pm5) / pm5) * -0.229 * 0.5

        # Market trades flow
        mt = state.market_trades.get("TOMATOES", [])
        fl = 0
        if mt:
            bv = sum(t.quantity for t in mt if t.price >= fm)
            sv = sum(t.quantity for t in mt if t.price < fm)
            if bv + sv > 0: fl = (bv - sv) / (bv + sv) * 2

        fair = round(fm * (1 + rev1 + rev5) + fl)

        bb = LIMITS[P] - pos; sb = LIMITS[P] + pos

        # TAKE
        for p in sorted(od.sell_orders.keys()):
            if p <= fair-1 and bb > 0:
                q = min(-od.sell_orders[p], bb); o.append(Order(P, p, q)); bb -= q; pos += q
            else: break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= fair+1 and sb > 0:
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

        # MAKE — penny-jump
        baa = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair+1: baa = p; break
        bbb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair-1: bbb = p; break
        if bbb is not None: bidp = bbb+1
        else: bidp = fair-2
        bidp = min(bidp, fair-1)
        if baa is not None: askp = baa-1
        else: askp = fair+2
        askp = max(askp, fair+1)

        if pos >= 60: bb = 0
        if pos <= -60: sb = 0

        if bb > 0: o.append(Order(P, bidp, bb))
        if sb > 0: o.append(Order(P, askp, -sb))

        return o
