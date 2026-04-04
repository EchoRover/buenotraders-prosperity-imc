"""e1_crazy17 — real fake1 (2,787) + two-layer MAKE on TOMATOES
ONE change: split MAKE into 65/35 at two price levels.
This is proven on EMERALDS (1,050). Never tested on T with the real code.
More price levels = more MAKE fill opportunities on live."""
T_SOFT = 100
T_LIM = 70
T_BETA = -0.229
T_EDGE = 1
T_ADVOL = 16

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": T_LIM}

class Trader:
    def run(self, state: TradingState):
        td = {}
        if state.traderData:
            try: td = json.loads(state.traderData)
            except: td = {}
        result: Dict[str, List[Order]] = {}
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
        for p in sorted(od.sell_orders.keys()):
            if p<=fair-T_EDGE and bb>0:
                q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else: break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=fair+T_EDGE and sb>0:
                q=min(od.buy_orders[p],sb);o.append(Order(P,p,-q));sb-=q;pos-=q
            else: break
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
        baa=None
        for p in sorted(od.sell_orders.keys()):
            if p>fair+1: baa=p;break
        bbb=None
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p<fair-1: bbb=p;break
        if bbb is not None: bidp=bbb+1
        else: bidp=fair-2
        bidp=min(bidp,fair-1)
        if baa is not None: askp=baa-1
        else: askp=fair+2
        askp=max(askp,fair+1)
        if pos>T_SOFT: askp=max(askp-1,fair+1)
        elif pos<-T_SOFT: bidp=min(bidp+1,fair-1)
        if pos>=T_LIM: bb=0
        if pos<=-T_LIM: sb=0
        # TWO-LAYER MAKE — the ONE change from fake1
        if bb>0:
            l1=max(1,int(bb*0.65));l2=bb-l1
            o.append(Order(P,bidp,l1))
            if l2>0: o.append(Order(P,bidp-1,l2))
        if sb>0:
            l1=max(1,int(sb*0.65));l2=sb-l1
            o.append(Order(P,askp,-l1))
            if l2>0: o.append(Order(P,askp+1,-l2))
        return o