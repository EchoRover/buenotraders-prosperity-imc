"""
e1_crazy4 — claude2 agent
=========================
NOT accepting E=867. Challenging the interference finding.

FACT: crazy1 got E=1,050 AND T=1,015 = 2,065.
FACT: v12/v13 got E=1,050 AND T=549 = 1,599.
CONCLUSION: The interference isn't absolute. crazy1's T SURVIVED. WHY?

Hypothesis: The ADVERSE FILTER in crazy1 protected T from the interference.
When E=1,050 changes bot behavior, some TOMATOES fills become toxic.
The adverse filter (skip takes when best vol >= 15) catches those toxic fills.
v10's T has NO filter → eats the toxic fills → crashes.

PLAN: Combine the BEST of everything:
  - EMERALDS: crazy1 approach (1,050 — proven 3 times)
  - TOMATOES FV: v10's filtered mid + reversion (proven at 1,477 with E=867)
  - TOMATOES PROTECTION: adverse filter from crazy1 (shields against interference)
  - TOMATOES MAKE: PENNY-JUMP (not static spread!)
    Why? Claude1 proved queue priority is everything. Static spread=6 puts us
    at the SAME price as bots = LAST in queue. Penny-jump = unique price = FIRST.
    "Penny-jump fails on TOMATOES" was tested with BAD fair value (not filtered mid).
    With filtered mid + reversion, our FV is accurate → penny-jump should work.

Expected:
  E = 1,050 (crazy1, proven)
  T = 1,200-1,500 (v10 FV + adverse shield + penny-jump queue priority)
  Total = 2,250-2,550 (potential new best!)

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 50}

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
# TOMATOES — v10 FV + adverse shield + penny-jump
# ═══════════════════════════════════════════
T_ADVERSE_VOL   = 15
T_REVERSION     = -0.229
T_TAKE_EDGE     = 1
T_DISREGARD     = 1       # ignore orders within 1 of fair for penny-jump
T_DEFAULT_EDGE  = 4       # fallback if no bot levels to penny
T_SKEW          = 0.15
T_HARD_LIMIT    = 40
T_L1_PCT        = 0.65
T_L2_OFFSET     = 2


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
                result[product] = self._tomatoes(od, pos, td, state)

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
                if p < FAIR - E_DISREGARD:
                    bid_p = p + 1; break
        bid_p = min(bid_p, FAIR - 1)

        ask_p = FAIR + E_DEFAULT_EDGE
        if od.sell_orders:
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + E_DISREGARD:
                    ask_p = p - 1; break
        ask_p = max(ask_p, FAIR + 1)

        if pos > E_SOFT_LIMIT:
            bid_p -= 1; ask_p = max(ask_p - 1, FAIR + 1)
        if pos < -E_SOFT_LIMIT:
            ask_p += 1; bid_p = min(bid_p + 1, FAIR - 1)

        imb = self._obi(od)
        if imb > E_IMB_THRESH:
            ask_p = max(ask_p - 1, FAIR + 1)
        elif imb < -E_IMB_THRESH:
            bid_p = min(bid_p + 1, FAIR - 1)

        skew = round(pos * E_SKEW)
        bid_p -= skew; ask_p -= skew
        bid_p = min(bid_p, FAIR - 1)
        ask_p = max(ask_p, FAIR + 1)

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
    # TOMATOES — v10 FV + adverse shield + penny-jump make
    # ══════════════════════════════════════════════════════════════

    def _tomatoes(self, od, pos, td, state):
        P = "TOMATOES"
        LIM = LIMITS[P]
        orders = []

        # ── FILTERED MID + REVERSION (v10 proven) ──
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p; break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p; break
        if filtered_bid is None:
            filtered_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        if filtered_ask is None:
            filtered_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if filtered_bid is None or filtered_ask is None:
            return orders

        fmid = (filtered_bid + filtered_ask) / 2

        prev_mid = td.get("pm", fmid)
        td["pm"] = fmid

        if prev_mid != 0:
            last_return = (fmid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION
            fair = round(fmid * (1 + pred_return))
        else:
            fair = round(fmid)

        buy_b = LIM - pos; sell_b = LIM + pos

        # ── TAKE with ADVERSE FILTER (interference shield) ──
        # Skip takes when best level has large volume (market maker)
        # This protected crazy1's T when E=1,050
        can_buy = True
        can_sell = True
        if od.sell_orders:
            best_ask = min(od.sell_orders.keys())
            if abs(od.sell_orders[best_ask]) >= T_ADVERSE_VOL:
                can_buy = False
        if od.buy_orders:
            best_bid = max(od.buy_orders.keys())
            if od.buy_orders[best_bid] >= T_ADVERSE_VOL:
                can_sell = False

        if can_buy:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair - T_TAKE_EDGE and buy_b > 0:
                    q = min(-od.sell_orders[price], buy_b)
                    orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        if can_sell:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair + T_TAKE_EDGE and sell_b > 0:
                    q = min(od.buy_orders[price], sell_b)
                    orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break

        # ── CLEAR at fair (v10) ──
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        # ── MAKE: PENNY-JUMP (not static spread!) ──
        # Queue priority insight: static spread puts us at same price as bots = LAST in queue
        # Penny-jump = 1 tick better than bot = unique level = FIRST in queue
        # "Penny-jump fails on TOMATOES" was tested with BAD FV. With filtered mid it should work.

        bid_p = fair - T_DEFAULT_EDGE  # fallback
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - T_DISREGARD:
                bid_p = p + 1
                break
        bid_p = min(bid_p, fair - 1)

        ask_p = fair + T_DEFAULT_EDGE  # fallback
        for p in sorted(od.sell_orders.keys()):
            if p > fair + T_DISREGARD:
                ask_p = p - 1
                break
        ask_p = max(ask_p, fair + 1)

        # Inventory skew on top of penny-jump
        skew = round(pos * T_SKEW)
        bid_p -= skew
        ask_p -= skew

        if pos >= T_HARD_LIMIT: buy_b = 0
        if pos <= -T_HARD_LIMIT: sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * T_L1_PCT)); l2 = buy_b - l1
            orders.append(Order(P, bid_p, l1))
            if l2 > 0: orders.append(Order(P, bid_p - T_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * T_L1_PCT)); l2 = sell_b - l1
            orders.append(Order(P, ask_p, -l1))
            if l2 > 0: orders.append(Order(P, ask_p + T_L2_OFFSET, -l2))

        return orders

    @staticmethod
    def _obi(od) -> float:
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0