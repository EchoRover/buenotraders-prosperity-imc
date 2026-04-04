"""
ULTIMATE v2 — Targeting 3100+
================================
Changes from v1 (2787 baseline):

TOMATOES:
  1. TIGHTER QUOTES: fixed fair±3 instead of dynamic ~6
     → More market trade fills (sim matches resting orders vs market trades)
  2. THREE-LAYER QUOTING: spread budget across fair-3, fair-4, fair-5
     → Maximizes fill probability across multiple price levels
  3. ENDGAME FLATTEN: last 15k timestamps → aggressively flatten position
     → Locks in realized PnL, reduces mark-to-market variance
  4. DRIFT BIAS: track cumulative drift direction, lean quotes with it
     → If TOMATOES is trending up, bid tighter (capture more buys)

EMERALDS: unchanged (1050 is the ceiling on this dataset)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 70}

# TOMATOES tuning
T_ADVOL = 16
T_BETA = -0.229
T_EDGE = 1
T_QUOTE_SPREAD = 3       # ← TIGHTER: was ~6 dynamic, now fixed 3
T_LAYERS = 3             # ← NEW: quote across 3 price levels
T_ENDGAME_TS = 185000    # ← NEW: start flattening at this timestamp
T_ENDGAME_AGGRO = True   # ← NEW: flat at any price in endgame


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
            if product == "EMERALDS":
                result[product] = self.te(od, pos)
            elif product == "TOMATOES":
                result[product] = self.tt(od, pos, td, state.timestamp)
        return result, 0, json.dumps(td, separators=(',',':'))

    # ═══════════════════════════════════════════════════════════
    # EMERALDS — exact e1_fake1 (proven 1050)
    # ═══════════════════════════════════════════════════════════
    def te(self, od, pos):
        FAIR=10000;P="EMERALDS";LIM=LIMITS[P];o=[];bb=LIM-pos;sb=LIM+pos
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

    # ═══════════════════════════════════════════════════════════
    # TOMATOES — tighter quotes + multi-layer + endgame flatten
    # ═══════════════════════════════════════════════════════════
    def tt(self, od, pos, td, timestamp):
        P="TOMATOES";LIM=LIMITS[P];o=[]

        # ── Fair value: wall-mid + beta reversion ──
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

        # ── Track drift for bias ──
        dh=td.get("dh",[])
        dh.append(fm)
        if len(dh)>30: dh=dh[-30:]
        td["dh"]=dh
        drift_bias=0
        if len(dh)>=10:
            recent_drift=dh[-1]-dh[-10]
            if recent_drift>3: drift_bias=1    # trending up
            elif recent_drift<-3: drift_bias=-1 # trending down

        bb=LIM-pos;sb=LIM+pos

        # ── ENDGAME: aggressive flatten in last 15k timestamps ──
        endgame = timestamp >= T_ENDGAME_TS
        if endgame and abs(pos) > 5:
            # Flatten at any profitable price (or at fair)
            if pos > 0 and sb > 0:
                for p in sorted(od.buy_orders.keys(),reverse=True):
                    if p >= fair - 2 and sb > 0 and pos > 0:
                        q=min(od.buy_orders[p],sb,pos)
                        if q>0: o.append(Order(P,p,-q));sb-=q;pos-=q
                    else: break
            if pos < 0 and bb > 0:
                for p in sorted(od.sell_orders.keys()):
                    if p <= fair + 2 and bb > 0 and pos < 0:
                        q=min(-od.sell_orders[p],bb,-pos)
                        if q>0: o.append(Order(P,p,q));bb-=q;pos+=q
                    else: break

        # ── TAKE: aggressive fills ──
        for p in sorted(od.sell_orders.keys()):
            if p<=fair-T_EDGE and bb>0:
                q=min(-od.sell_orders[p],bb);o.append(Order(P,p,q));bb-=q;pos+=q
            else: break
        for p in sorted(od.buy_orders.keys(),reverse=True):
            if p>=fair+T_EDGE and sb>0:
                q=min(od.buy_orders[p],sb);o.append(Order(P,p,-q));sb-=q;pos-=q
            else: break

        # ── CLEAR at fair ──
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

        # ── MAKE: tight multi-layer quotes ──
        if pos>=LIM: bb=0
        if pos<=-LIM: sb=0

        # Bid side: 3 layers at fair-3, fair-4, fair-5
        # Drift bias: if trending up, tighten bids (more fills on buy side)
        base_bid = fair - T_QUOTE_SPREAD + drift_bias
        base_bid = min(base_bid, fair - 1)  # never bid at fair or above

        # Ask side: 3 layers at fair+3, fair+4, fair+5
        base_ask = fair + T_QUOTE_SPREAD - drift_bias
        base_ask = max(base_ask, fair + 1)  # never ask at fair or below

        # Position-based skew: lean away from large positions
        if pos > 40:
            base_bid -= 1  # less aggressive buying
            base_ask = max(base_ask - 1, fair + 1)  # more aggressive selling
        elif pos < -40:
            base_ask += 1  # less aggressive selling
            base_bid = min(base_bid + 1, fair - 1)  # more aggressive buying

        # In endgame, tighten even more to capture more fills for flattening
        if endgame:
            if pos > 0:
                base_ask = max(fair + 1, base_ask - 1)  # sell tighter
            elif pos < 0:
                base_bid = min(fair - 1, base_bid + 1)  # buy tighter

        # Distribute budget across 3 layers (50% / 30% / 20%)
        if bb > 0 and T_LAYERS >= 2:
            l1 = max(1, int(bb * 0.50))
            l2 = max(1, int(bb * 0.30))
            l3 = bb - l1 - l2
            o.append(Order(P, base_bid, l1))
            o.append(Order(P, base_bid - 1, l2))
            if l3 > 0:
                o.append(Order(P, base_bid - 2, l3))
        elif bb > 0:
            o.append(Order(P, base_bid, bb))

        if sb > 0 and T_LAYERS >= 2:
            l1 = max(1, int(sb * 0.50))
            l2 = max(1, int(sb * 0.30))
            l3 = sb - l1 - l2
            o.append(Order(P, base_ask, -l1))
            o.append(Order(P, base_ask + 1, -l2))
            if l3 > 0:
                o.append(Order(P, base_ask + 2, -l3))
        elif sb > 0:
            o.append(Order(P, base_ask, -sb))

        return o