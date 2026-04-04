"""
VARIANT SWEEP — Test these configs in Rust backtester
=====================================================
All variants use identical EMERALDS logic (proven 1050).
Only TOMATOES parameters change.

Naming: v{limit}_{beta}_{advol}_{dd}
  limit: TOMATOES position limit
  beta: mean reversion coefficient (x1000)
  advol: fat-level volume threshold
  dd: drawdown circuit breaker (0=off, 1=on)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

# ═══════════════════════════════════════════════════════════════
# SWEEP PARAMETERS — edit these per variant
# ═══════════════════════════════════════════════════════════════
VARIANT = "v75_229_16_1"  # identifier for this run

# Position limits
E_LIMIT = 80
T_LIMIT = 75       # SWEEP: [50, 60, 65, 70, 75, 80]

# FV estimation
T_ADVOL = 16       # SWEEP: [10, 12, 14, 16, 18, 20]
T_BETA = -0.229    # SWEEP: [-0.10, -0.15, -0.20, -0.229, -0.25, -0.30, -0.35]
T_EDGE = 1         # SWEEP: [0, 1, 2]

# Quoting
T_L1_PCT = 0.65    # SWEEP: [0.50, 0.60, 0.65, 0.70, 0.80]
T_L2_OFFSET = 1    # SWEEP: [1, 2]
T_SOFT = 60        # SWEEP: [40, 50, 60, 70, 100(off)]

# Circuit breaker
USE_CB = True       # SWEEP: [True, False]
T_DD_WINDOW = 15   # SWEEP: [10, 15, 20, 25]
T_DD_THRESH = 8    # SWEEP: [5, 6, 7, 8, 10, 12]
T_DD_SCALE = 0.60  # SWEEP: [0.40, 0.50, 0.60, 0.70, 0.80]

LIMITS = {"EMERALDS": E_LIMIT, "TOMATOES": T_LIMIT}


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
            if p<=FAIR-1 and bb>0:
                q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else: break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=FAIR+1 and sb>0:
                q=min(od.buy_orders[p],sb);o.append(Order(P,p,-q));sb-=q;pos-=q
            else: break
        if pos>0 and sb>0:
            for p in sorted(od.buy_orders.keys(),reverse=True):
                if p>=FAIR and sb>0 and pos>0:
                    q=min(od.buy_orders[p],sb,pos)
                    if q>0: o.append(Order(P,p,-q));sb-=q;pos-=q
                else: break
        if pos<0 and bb>0:
            for p in sorted(od.sell_orders.keys()):
                if p<=FAIR and bb>0 and pos<0:
                    q=min(-od.sell_orders[p],bb,-pos)
                    if q>0: o.append(Order(P,p,q));bb-=q;pos+=q
                else: break
        if pos>20 and sb>0:
            for p in sorted(od.buy_orders.keys(),reverse=True):
                if p>=FAIR-1 and sb>0 and pos>5:
                    q=min(od.buy_orders[p],sb,pos-5)
                    if q>0: o.append(Order(P,p,-q));sb-=q;pos-=q
                else: break
        if pos<-20 and bb>0:
            for p in sorted(od.sell_orders.keys()):
                if p<=FAIR+1 and bb>0 and pos<-5:
                    q=min(-od.sell_orders[p],bb,-pos-5)
                    if q>0: o.append(Order(P,p,q));bb-=q;pos+=q
                else: break
        bp=FAIR-4
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p<FAIR-1: bp=p+1;break
        bp=min(bp,FAIR-1)
        ap=FAIR+4
        for p in sorted(od.sell_orders.keys()):
            if p>FAIR+1: ap=p-1;break
        ap=max(ap,FAIR+1)
        if pos>25: bp-=1;ap=max(ap-1,FAIR+1)
        elif pos<-25: ap+=1;bp=min(bp+1,FAIR-1)
        bp=min(bp,FAIR-1);ap=max(ap,FAIR+1)
        if bb>0:
            l1=max(1,int(bb*0.65));o.append(Order(P,bp,l1))
            if bb-l1>0: o.append(Order(P,bp-1,bb-l1))
        if sb>0:
            l1=max(1,int(sb*0.65));o.append(Order(P,ap,-l1))
            if sb-l1>0: o.append(Order(P,ap+1,-(sb-l1)))
        return o

    def _tomatoes(self, od, pos, td):
        P="TOMATOES";o=[]

        # FV: fat bid/ask + beta reversion
        fb=None
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if od.buy_orders[p]>=T_ADVOL: fb=p;break
        fa=None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p])>=T_ADVOL: fa=p;break
        if fb is None: fb=max(od.buy_orders.keys()) if od.buy_orders else None
        if fa is None: fa=min(od.sell_orders.keys()) if od.sell_orders else None
        if fb is None or fa is None: return o

        fm=(fb+fa)/2.0
        pm=td.get("pm",fm);td["pm"]=fm
        if pm!=0:
            lr=(fm-pm)/pm;pr=lr*T_BETA;fair=round(fm*(1+pr))
        else: fair=round(fm)

        # Circuit breaker
        LIM = T_LIMIT
        if USE_CB:
            fh=td.get("fh",[]);fh.append(fm)
            if len(fh)>T_DD_WINDOW: fh=fh[-T_DD_WINDOW:]
            td["fh"]=fh
            if len(fh)>=T_DD_WINDOW:
                pk=max(fh[:T_DD_WINDOW//2])
                if pk-fh[-1]>T_DD_THRESH:
                    LIM=int(T_LIMIT*T_DD_SCALE)

        bb=LIM-pos;sb=LIM+pos
        bb=min(bb,LIMITS[P]-pos);sb=min(sb,LIMITS[P]+pos)

        # TAKE
        for p in sorted(od.sell_orders.keys()):
            if p<=fair-T_EDGE and bb>0:
                q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else: break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=fair+T_EDGE and sb>0:
                q=min(od.buy_orders[p],sb);o.append(Order(P,p,-q));sb-=q;pos-=q
            else: break

        # CLEAR
        if pos>0 and sb>0:
            for p in sorted(od.buy_orders.keys(),reverse=True):
                if p>=fair and sb>0 and pos>0:
                    q=min(od.buy_orders[p],sb,pos)
                    if q>0: o.append(Order(P,p,-q));sb-=q;pos-=q
                else: break
        if pos<0 and bb>0:
            for p in sorted(od.sell_orders.keys()):
                if p<=fair and bb>0 and pos<0:
                    q=min(-od.sell_orders[p],bb,-pos)
                    if q>0: o.append(Order(P,p,q));bb-=q;pos+=q
                else: break

        # MAKE — dynamic spread
        bbb=None
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p<fair-1: bbb=p;break
        baa=None
        for p in sorted(od.sell_orders.keys()):
            if p>fair+1: baa=p;break

        bidp=bbb+1 if bbb is not None else fair-2
        bidp=min(bidp,fair-1)
        askp=baa-1 if baa is not None else fair+2
        askp=max(askp,fair+1)

        if pos>T_SOFT: askp=max(askp-1,fair+1)
        elif pos<-T_SOFT: bidp=min(bidp+1,fair-1)

        if pos>=T_LIMIT: bb=0
        if pos<=-T_LIMIT: sb=0

        if bb>0:
            l1=max(1,int(bb*T_L1_PCT));l2=bb-l1
            o.append(Order(P,bidp,l1))
            if l2>0: o.append(Order(P,bidp-T_L2_OFFSET,l2))
        if sb>0:
            l1=max(1,int(sb*T_L1_PCT));l2=sb-l1
            o.append(Order(P,askp,-l1))
            if l2>0: o.append(Order(P,askp+T_L2_OFFSET,-(sb-l1)))
        return o