"""
e1_v13 — v12 base + wider TOMATO spread=7 + hard_lim=60 — Best of both: crazy1 EMERALDS (1050) + v10 TOMATOES (1477).

EMERALDS from crazy1 (scored 1,050 — EMERALD record):
  - Penny-jump + CLEAR
  - LIMIT=80, ZERO SKEW, L2_offset=1
  - Aggressive CLEAR at fair±1 when pos > 30

TOMATOES from v10 (scored 1,477 — TOMATOES record):
  - Filtered mid (vol>=15) + reversion(-0.229)
  - Static spread=6, skew=0.15, hard_limit=40
  - CLEAR at fair, 2-layer 65/35

Combined target: 2,527+
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 50}

# EMERALDS: crazy1 exact params (scored 1,050)
E_FAIR = 10000
E_TAKE_EDGE = 1
E_CLEAR_EDGE = 0
E_DISREGARD = 1
E_DEFAULT_EDGE = 4
E_SKEW = 0.00           # ZERO — crazy1's key finding
E_SOFT_LIMIT = 25
E_L1_PCT = 0.65
E_L2_OFFSET = 1         # tight backup (crazy1 used 1, not 2)
E_AGGRO_POS = 30
E_AGGRO_TARG = 15

# TOMATOES: v10 exact params (scored 1,477)
T_ADVERSE_VOL = 15
T_REVERSION = -0.229
T_TAKE_EDGE = 1
T_CLEAR_EDGE = 0
T_SPREAD = 7
T_SKEW = 0.15
T_HARD_LIM = 60
T_L1_PCT = 0.65
T_L2_OFFSET = 2


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
                result[product] = self.trade_emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(od, pos, td)

        return result, 0, json.dumps(td, separators=(',', ':'))

    # ══════════════════════════════════════════════════════════════
    # EMERALDS — crazy1 code (proven 1,050)
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od, pos):
        FAIR = E_FAIR; P = "EMERALDS"; orders = []
        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE
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

        # CLEAR at fair
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

        # AGGRESSIVE CLEAR at fair±1 when position extreme
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

        # MAKE — penny-jump with ZERO skew
        bid_price = FAIR - E_DEFAULT_EDGE
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - E_DISREGARD:
                bid_price = p + 1 if od.buy_orders[p] > 1 else p; break
        bid_price = min(bid_price, FAIR - 1)

        ask_price = FAIR + E_DEFAULT_EDGE
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + E_DISREGARD:
                ask_price = p - 1 if abs(od.sell_orders[p]) > 1 else p; break
        ask_price = max(ask_price, FAIR + 1)

        # Soft limit shifts (no skew — crazy1's approach)
        if pos > E_SOFT_LIMIT:
            bid_price -= 1; ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -E_SOFT_LIMIT:
            ask_price += 1; bid_price = min(bid_price + 1, FAIR - 1)

        # Two-layer with tight offset
        if buy_b > 0:
            l1 = max(1, int(buy_b * E_L1_PCT)); l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0: orders.append(Order(P, bid_price - E_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * E_L1_PCT)); l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0: orders.append(Order(P, ask_price + E_L2_OFFSET, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — v10 code (proven 1,477)
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos, td):
        P = "TOMATOES"; orders = []

        # Filtered mid (vol >= 15)
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

        filtered_mid = (filtered_bid + filtered_ask) / 2

        # Reversion
        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid
        reversion_adj = 0
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            reversion_adj = last_return * T_REVERSION
        fair = round(filtered_mid * (1 + reversion_adj))

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - T_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q)); buy_b -= q; pos += q
            else: break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + T_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
            else: break

        # CLEAR
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair - T_CLEAR_EDGE and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair + T_CLEAR_EDGE and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        # MAKE
        skew = round(pos * T_SKEW)
        bid_price = fair - T_SPREAD - skew
        ask_price = fair + T_SPREAD - skew

        if pos >= T_HARD_LIM: buy_b = 0
        if pos <= -T_HARD_LIM: sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * T_L1_PCT)); l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0: orders.append(Order(P, bid_price - T_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * T_L1_PCT)); l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0: orders.append(Order(P, ask_price + T_L2_OFFSET, -l2))

        return orders
