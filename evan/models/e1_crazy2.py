"""
e1_crazy2 — claude2 agent
=========================
The Frankenstein: best EMERALDS approach + best TOMATOES approach.

EMERALDS from crazy1 (scored 1,050 — best ever, +21% over all others at 867):
  - Limit=80, zero skew, aggressive CLEAR cycling
  - Penny-jump + OBI adjustment
  - This works because aggressive CLEAR frees capacity for more fills:
    29 fills at +36 avg vs 16 fills before

TOMATOES from v10 (scored 1,477 — best ever, +20% over LADDOO's 1,235):
  - Filtered mid (vol >= 15 = bot quotes, ignore noise)
  - Reversion beta -0.229 (fade 22.9% of last move)
  - Simple spread=6, skew=0.10 (reduced from v10's 0.15 for limit=80)
  PLUS limit=80 + aggressive CLEAR (the trick that boosted EMERALDS)
  - If CLEAR cycling works on TOMATOES like it did on EMERALDS, expect 1,600+

Combined target: 1,050 + 1,600 = 2,650+ (vs current best 2,344)

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# ═══════════════════════════════════════════
# EMERALDS — crazy1 exact (proven 1,050)
# ═══════════════════════════════════════════
E_FAIR         = 10_000
E_TAKE_EDGE    = 1
E_CLEAR_EDGE   = 0
E_DEFAULT_EDGE = 4
E_DISREGARD    = 1
E_SKEW         = 0.00
E_SOFT_LIMIT   = 25
E_L1_PCT       = 0.65
E_L2_OFFSET    = 1
E_IMB_THRESH   = 0.12
E_AGGRO_POS    = 30
E_AGGRO_TARG   = 15

# ═══════════════════════════════════════════
# TOMATOES — v10 core + limit=80 + CLEAR
# ═══════════════════════════════════════════
T_ADVERSE_VOL  = 15
T_REVERSION    = -0.229
T_TAKE_EDGE    = 1
T_CLEAR_EDGE   = 0
T_SPREAD       = 6
T_SKEW         = 0.10
T_HARD_LIMIT   = 60
T_L1_PCT       = 0.65
T_L2_OFFSET    = 2
T_AGGRO_POS    = 40
T_AGGRO_TARG   = 20


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
                result[product] = self._emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self._tomatoes(od, pos, td)

        return result, 0, json.dumps(td, separators=(',', ':'))

    # ══════════════════════════════════════════════════════════════
    # EMERALDS — crazy1 exact (proven 1,050)
    # ══════════════════════════════════════════════════════════════

    def _emeralds(self, od, pos):
        P = "EMERALDS"
        FAIR = E_FAIR
        LIM = LIMITS[P]
        orders = []
        buy_b = LIM - pos
        sell_b = LIM + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - E_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q; pos += q
            else:
                break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + E_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q; pos -= q
            else:
                break

        # CLEAR at fair
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR - E_CLEAR_EDGE and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR + E_CLEAR_EDGE and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # AGGRESSIVE CLEAR at fair±1 when extreme
        if pos > E_AGGRO_POS and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR - 1 and sell_b > 0 and pos > E_AGGRO_TARG:
                    q = min(od.buy_orders[price], sell_b, pos - E_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < -E_AGGRO_POS and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR + 1 and buy_b > 0 and pos < -E_AGGRO_TARG:
                    q = min(-od.sell_orders[price], buy_b, -pos - E_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # MAKE: penny-jump + OBI
        bid_p = FAIR - E_DEFAULT_EDGE
        if od.buy_orders:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p < FAIR - E_DISREGARD:
                    bid_p = p + 1
                    break
        bid_p = min(bid_p, FAIR - 1)

        ask_p = FAIR + E_DEFAULT_EDGE
        if od.sell_orders:
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + E_DISREGARD:
                    ask_p = p - 1
                    break
        ask_p = max(ask_p, FAIR + 1)

        if pos > E_SOFT_LIMIT:
            bid_p -= 1
            ask_p = max(ask_p - 1, FAIR + 1)
        if pos < -E_SOFT_LIMIT:
            ask_p += 1
            bid_p = min(bid_p + 1, FAIR - 1)

        imb = self._obi(od)
        if imb > E_IMB_THRESH:
            ask_p = max(ask_p - 1, FAIR + 1)
        elif imb < -E_IMB_THRESH:
            bid_p = min(bid_p + 1, FAIR - 1)

        skew = round(pos * E_SKEW)
        bid_p -= skew
        ask_p -= skew
        bid_p = min(bid_p, FAIR - 1)
        ask_p = max(ask_p, FAIR + 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * E_L1_PCT))
            l2 = buy_b - l1
            orders.append(Order(P, bid_p, l1))
            if l2 > 0:
                orders.append(Order(P, bid_p - E_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * E_L1_PCT))
            l2 = sell_b - l1
            orders.append(Order(P, ask_p, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_p + E_L2_OFFSET, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — v10 filtered mid + reversion + limit=80 + CLEAR
    # ══════════════════════════════════════════════════════════════

    def _tomatoes(self, od, pos, td):
        P = "TOMATOES"
        LIM = LIMITS[P]
        orders = []

        # FILTERED MID: only levels with 15+ volume (bot maker quotes)
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p
                break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p
                break

        # Fallback to best bid/ask
        if filtered_bid is None:
            filtered_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        if filtered_ask is None:
            filtered_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if filtered_bid is None or filtered_ask is None:
            return orders

        fmid = (filtered_bid + filtered_ask) / 2

        # REVERSION — v10's exact formula (percentage-based, -0.229)
        prev_mid = td.get("pm", fmid)
        td["pm"] = fmid

        if prev_mid != 0:
            last_return = (fmid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION
            fair = round(fmid * (1 + pred_return))
        else:
            fair = round(fmid)

        buy_b = LIM - pos
        sell_b = LIM + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - T_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q; pos += q
            else:
                break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + T_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q; pos -= q
            else:
                break

        # CLEAR at fair
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair - T_CLEAR_EDGE and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair + T_CLEAR_EDGE and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # AGGRESSIVE CLEAR at fair±1 when extreme (from crazy1 EMERALDS success)
        if pos > T_AGGRO_POS and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair - 1 and sell_b > 0 and pos > T_AGGRO_TARG:
                    q = min(od.buy_orders[price], sell_b, pos - T_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < -T_AGGRO_POS and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair + 1 and buy_b > 0 and pos < -T_AGGRO_TARG:
                    q = min(-od.sell_orders[price], buy_b, -pos - T_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # MAKE — v10 static spread + reduced skew for limit=80
        skew = round(pos * T_SKEW)
        bid_p = fair - T_SPREAD - skew
        ask_p = fair + T_SPREAD - skew

        if pos >= T_HARD_LIMIT:
            buy_b = 0
        if pos <= -T_HARD_LIMIT:
            sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * T_L1_PCT))
            l2 = buy_b - l1
            orders.append(Order(P, bid_p, l1))
            if l2 > 0:
                orders.append(Order(P, bid_p - T_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * T_L1_PCT))
            l2 = sell_b - l1
            orders.append(Order(P, ask_p, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_p + T_L2_OFFSET, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # UTILS
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _obi(od) -> float:
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0
