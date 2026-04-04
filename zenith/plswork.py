"""
ADAPTIVE MM — No directional prediction, just smarter market making
====================================================================
Key insight from P3 2nd-place: "future price is essentially unpredictable"
So we DON'T predict direction. Instead we adapt the MM parameters:

1. Use wall-mid for fair (proven best FV estimator)
2. ADAPT spread based on recent volatility
   - High vol → wider spread (protect from adverse selection)
   - Low vol → tighter spread (capture more fills)
3. ADAPT inventory clearing based on how far from neutral we are
   - Large position → more aggressive clearing
4. Use OBI to SKEW quotes (not predict, just lean)
   - High buy pressure → widen asks slightly (let buyers pay more)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json, math
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 70}
T_ADVOL = 16
T_BETA = -0.229

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
                result[product] = self._emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self._tomatoes(od, pos, td)
        return result, 0, json.dumps(td, separators=(',', ':'))

    def _emeralds(self, od, pos):
        FAIR=10000;P="EMERALDS";o=[];bb=LIMITS[P]-pos;sb=LIMITS[P]+pos
        for p in sorted(od.sell_orders.keys()):
            if p<=FAIR-1 and bb>0:q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else:break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=FAIR+1 and sb>0:q=min(od.buy_orders[p],sb);o.append(Order(P,p,-q));sb-=q;pos-=q
            else:break
        if pos>0 and sb>0:
            for p in sorted(od.buy_orders.keys(),reverse=True):
                if p>=FAIR and sb>0 and pos>0:q=min(od.buy_orders[p],sb,pos);o.append(Order(P,p,-q)) if q>0 else None;sb-=q;pos-=q
                else:break
        if pos<0 and bb>0:
            for p in sorted(od.sell_orders.keys()):
                if p<=FAIR and bb>0 and pos<0:q=min(-od.sell_orders[p],bb,-pos);o.append(Order(P,p,q)) if q>0 else None;bb-=q;pos+=q
                else:break
        if pos>20 and sb>0:
            for p in sorted(od.buy_orders.keys(),reverse=True):
                if p>=FAIR-1 and sb>0 and pos>5:q=min(od.buy_orders[p],sb,pos-5);o.append(Order(P,p,-q)) if q>0 else None;sb-=q;pos-=q
                else:break
        if pos<-20 and bb>0:
            for p in sorted(od.sell_orders.keys()):
                if p<=FAIR+1 and bb>0 and pos<-5:q=min(-od.sell_orders[p],bb,-pos-5);o.append(Order(P,p,q)) if q>0 else None;bb-=q;pos+=q
                else:break
        bp=FAIR-4
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p<FAIR-1:bp=p+1;break
        bp=min(bp,FAIR-1);ap=FAIR+4
        for p in sorted(od.sell_orders.keys()):
            if p>FAIR+1:ap=p-1;break
        ap=max(ap,FAIR+1)
        if pos>25:bp-=1;ap=max(ap-1,FAIR+1)
        elif pos<-25:ap+=1;bp=min(bp+1,FAIR-1)
        bp=min(bp,FAIR-1);ap=max(ap,FAIR+1)
        if bb>0:l1=max(1,int(bb*0.65));o.append(Order(P,bp,l1));r=bb-l1;(o.append(Order(P,bp-1,r)) if r>0 else None)
        if sb>0:l1=max(1,int(sb*0.65));o.append(Order(P,ap,-l1));r=sb-l1;(o.append(Order(P,ap+1,-r)) if r>0 else None)
        return o

    def _tomatoes(self, od, pos, td):
        P = "TOMATOES"; LIM = LIMITS[P]; o = []
        if not od.buy_orders or not od.sell_orders:
            return o

        # ── Fair value: wall-mid + beta (proven) ──
        fb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVOL: fb = p; break
        fa = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVOL: fa = p; break
        if fb is None: fb = max(od.buy_orders.keys())
        if fa is None: fa = min(od.sell_orders.keys())
        fm = (fb + fa) / 2.0
        pm = td.get("pm", fm); td["pm"] = fm
        if pm != 0:
            lr = (fm - pm) / pm
            fair = round(fm * (1 + lr * T_BETA))
        else:
            fair = round(fm)

        # ── Volatility tracking ──
        hist = td.get("vh", [])
        hist.append(fm)
        if len(hist) > 30: hist = hist[-30:]
        td["vh"] = hist

        vol = 1.0
        if len(hist) >= 8:
            returns = [hist[i] - hist[i-1] for i in range(-min(8, len(hist)-1), 0)]
            if returns:
                mean_r = sum(returns) / len(returns)
                var_r = sum((r - mean_r)**2 for r in returns) / len(returns)
                vol = math.sqrt(var_r) if var_r > 0 else 0.5

        # ── OBI for quote skew ──
        bid_vol = sum(od.buy_orders.values())
        ask_vol = sum(abs(v) for v in od.sell_orders.values())
        total_vol = bid_vol + ask_vol
        obi = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0.0

        bb = LIM - pos; sb = LIM + pos

        # ── TAKE (same as e1_fake1) ──
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

        # ── CLEAR (same as e1_fake1) ──
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

        # ── ADAPTIVE MAKE ──
        # Dynamic spread: penny-ahead (e1 style) but adjusted by vol
        bbb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - 1: bbb = p; break
        baa = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair + 1: baa = p; break

        bidp = bbb + 1 if bbb is not None else fair - 2
        bidp = min(bidp, fair - 1)
        askp = baa - 1 if baa is not None else fair + 2
        askp = max(askp, fair + 1)

        # Vol adjustment: widen in high vol
        if vol > 2.0:
            bidp -= 1
            askp += 1

        # OBI skew: lean INTO the pressure (let the aggressive side pay more)
        if obi > 0.15:   # strong buy pressure
            askp += 1     # widen ask (make buyers pay more)
        elif obi < -0.15: # strong sell pressure
            bidp -= 1     # widen bid (make sellers accept less)

        # Position skew: lean AGAINST position to reduce inventory
        if pos > 30:
            askp = max(askp - 1, fair + 1)  # tighten ask to sell more
            bidp -= 1                        # widen bid to buy less
        elif pos < -30:
            bidp = min(bidp + 1, fair - 1)  # tighten bid to buy more
            askp += 1                        # widen ask to sell less

        bidp = min(bidp, fair - 1)
        askp = max(askp, fair + 1)

        if pos >= LIM: bb = 0
        if pos <= -LIM: sb = 0

        if bb > 0: o.append(Order(P, bidp, bb))
        if sb > 0: o.append(Order(P, askp, -sb))
        return o