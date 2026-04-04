"""e1_fake2_test — structural change: multi-timeframe reversion + market_trades flow"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order
import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 75}
T_ADVOL = 16
T_REVERSION_BETA = -0.229

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
            elif product == "TOMATOES": result[product] = self.tt(od, pos, td, state)
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

    def tt(self, od, pos, td, state):
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

        # Multi-timeframe: track 1-tick and 5-tick history
        hist = td.get("mh", [])
        hist.append(fm)
        if len(hist) > 10:
            hist = hist[-10:]
        td["mh"] = hist

        pm=td.get("pm",fm);td["pm"]=fm

        # Reversion on 1-tick
        rev1 = 0
        if pm != 0:
            lr=(fm-pm)/pm
            rev1 = lr * T_REVERSION_BETA

        # Reversion on 5-tick (if enough history)
        rev5 = 0
        if len(hist) >= 6:
            pm5 = hist[-6]
            if pm5 != 0:
                lr5 = (fm - pm5) / pm5
                rev5 = lr5 * T_REVERSION_BETA * 0.5  # half weight for longer term

        # Market trades flow signal
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
                flow_adj = flow * 2.0  # shift fair by up to ±2

        fair = round(fm * (1 + rev1 + rev5) + flow_adj)

        bb=LIMITS[P]-pos;sb=LIMITS[P]+pos
        for p in sorted(od.sell_orders.keys()):
            if p<=fair-1 and bb>0:
                q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else: break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=fair+1 and sb>0:
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
        if pos>=75: bb=0
        if pos<=-75: sb=0
        if bb>0: o.append(Order(P,bidp,bb))
        if sb>0: o.append(Order(P,askp,-sb))
        return o