"""
PARAMETER GRID — 6 Variants That Actually Differ
==================================================
IMPORTANT: zenmary + zenmaryv2 both produced IDENTICAL results to e1_fake1 (2787.47).
The circuit breaker NEVER fired (max FV drop=8.0, threshold was >8).
The limit=75 had no effect (position never hit 70).

These variants change parameters that ACTUALLY affect execution.
Test each one separately on the sim.

HOW TO USE:
  1. Pick a variant by uncommenting one VARIANT block below
  2. Submit to the sim
  3. Record the PnL
  4. Repeat for each variant
"""

# ═══════════════════════════════════════════════════════════════
# UNCOMMENT ONE VARIANT AT A TIME
# ═══════════════════════════════════════════════════════════════

# --- VARIANT A: Edge=0 (take AT fair, not fair±1) ---
# More aggressive taking: 41 extra take opportunities vs edge=1
# Risk: some takes at 0 edge, but position gains in trending market
T_LIMIT = 70; T_BETA = -0.229; T_ADVOL = 16; T_EDGE = 0

# --- VARIANT B: Lower beta (less mean reversion) ---
# T_LIMIT = 70; T_BETA = -0.10; T_ADVOL = 16; T_EDGE = 1

# --- VARIANT C: Higher beta (more mean reversion) ---
# T_LIMIT = 70; T_BETA = -0.35; T_ADVOL = 16; T_EDGE = 1

# --- VARIANT D: Lower ADVOL (wider fat-level detection) ---
# T_LIMIT = 70; T_BETA = -0.229; T_ADVOL = 10; T_EDGE = 1

# --- VARIANT E: Limit 80 (max capacity) ---
# T_LIMIT = 80; T_BETA = -0.229; T_ADVOL = 16; T_EDGE = 1

# --- VARIANT F: Aggressive combo ---
# T_LIMIT = 80; T_BETA = -0.15; T_ADVOL = 12; T_EDGE = 0

# ═══════════════════════════════════════════════════════════════

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": T_LIMIT}

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
            if product == "EMERALDS": result[product] = self.te(od, pos)
            elif product == "TOMATOES": result[product] = self.tt(od, pos, td)
        return result, 0, json.dumps(td, separators=(',',':'))

    def te(self, od, pos):
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

    def tt(self, od, pos, td):
        P="TOMATOES";o=[]
        fb=None
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if od.buy_orders[p]>=T_ADVOL: fb=p;break
        fa=None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p])>=T_ADVOL: fa=p;break
        if fb is None: fb=max(od.buy_orders.keys()) if od.buy_orders else None
        if fa is None: fa=min(od.sell_orders.keys()) if od.sell_orders else None
        if fb is None or fa is None: return o
        fm=(fb+fa)/2
        pm=td.get("pm",fm);td["pm"]=fm
        if pm!=0:
            lr=(fm-pm)/pm;pr=lr*T_BETA;fair=round(fm*(1+pr))
        else: fair=round(fm)
        bb=LIMITS[P]-pos;sb=LIMITS[P]+pos
        # TAKE
        for p in sorted(od.sell_orders.keys()):
            if p<=fair-T_EDGE and bb>0:
                q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else: break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=fair+T_EDGE and sb>0:
                q=min(od.buy_orders[p],sb);o.append(Order(P,p,-q));sb-=q;pos-=q
            else: break
        # CLEAR at fair
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
        if pos>=T_LIMIT: bb=0
        if pos<=-T_LIMIT: sb=0
        if bb>0: o.append(Order(P,bidp,bb))
        if sb>0: o.append(Order(P,askp,-sb))
        return o