"""
e1_crazy10 — claude2 agent
==========================
Research-backed overhaul. Every change sourced from winning teams.

EMERALDS (1,050 → 1,200+ target):
  E_TAKE_EDGE = 0 — TAKE at fair price (10,000).
  Data shows 327 anomalous ticks/day with asks/bids at 10,000.
  Current TAKE_EDGE=1 misses them all. Taking at fair on EMERALDS
  is safe because price ALWAYS reverts (it's pegged at 10,000).
  Each captured anomalous tick = position that CLEARs at 10,001+ later.

TOMATOES (1,611 → 1,900+ target):
  Three techniques from 2nd-place winners:

  1. T_TAKE_EDGE = 2 (Frankfurt Hedgehogs, 2nd P3)
     Our spread capture is NEGATIVE (-24). The 20.5% unfavorable fills
     are the marginal takes at edge=1. Cut them. Fewer but better takes.
     Frankfurt reported +20% MM PnL from this alone.

  2. DUAL FAIR VALUE (Linear Utility / pe049395)
     Currently we use reversion-adjusted fair for EVERYTHING.
     This biases our MAKE quotes off-center → negative spread capture.
     Fix: use reversion fair for TAKE (directional bets),
          use raw filtered_mid for MAKE penny-jump (centered spread).
     Earn from BOTH direction AND spread capture.

  3. PASSIVE CLEAR AT FAIR (Linear Utility, 2nd P2)
     When we have inventory, post an order at exactly fair.
     0 EV but frees capacity for future +EV trades. Linear Utility
     reported +3% PnL from this.

  Position: soft=20, hard=70, limit=70 (crazy8 proven)

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 70}

# TOMATOES constants
T_ADVERSE_VOL = 15
T_REVERSION_BETA = -0.229
T_TAKE_EDGE = 2            # CHANGE: was 1. Frankfurt: eliminate marginal bad takes.
T_DISREGARD = 1
T_DEFAULT_EDGE = 2
T_SOFT_LIMIT = 20

# EMERALDS constants
E_FAIR = 10_000
E_TAKE_EDGE = 0             # CHANGE: was 1. Capture anomalous ticks at 10,000.
E_CLEAR_EDGE = 0
E_DEFAULT_EDGE = 4; E_DISREGARD = 1; E_SKEW = 0.00
E_SOFT_LIMIT = 25; E_L1_PCT = 0.65; E_L2_OFFSET = 1
E_IMB_THRESH = 0.12; E_AGGRO_POS = 30; E_AGGRO_TARG = 15


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
    # EMERALDS — crazy1 + TAKE_EDGE=0 (capture anomalous ticks)
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od, pos):
        P = "EMERALDS"; FAIR = E_FAIR; LIM = LIMITS[P]
        orders = []; buy_b = LIM - pos; sell_b = LIM + pos

        # TAKE at FAIR (edge=0) — captures 327 anomalous ticks/day
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

        # AGGRESSIVE CLEAR at fair±1
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

        # MAKE: penny-jump + OBI
        bid_p = FAIR - E_DEFAULT_EDGE
        if od.buy_orders:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p < FAIR - E_DISREGARD: bid_p = p + 1; break
        bid_p = min(bid_p, FAIR - 1)
        ask_p = FAIR + E_DEFAULT_EDGE
        if od.sell_orders:
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + E_DISREGARD: ask_p = p - 1; break
        ask_p = max(ask_p, FAIR + 1)

        if pos > E_SOFT_LIMIT: bid_p -= 1; ask_p = max(ask_p - 1, FAIR + 1)
        if pos < -E_SOFT_LIMIT: ask_p += 1; bid_p = min(bid_p + 1, FAIR - 1)

        imb = self._obi(od)
        if imb > E_IMB_THRESH: ask_p = max(ask_p - 1, FAIR + 1)
        elif imb < -E_IMB_THRESH: bid_p = min(bid_p + 1, FAIR - 1)

        bid_p = min(bid_p, FAIR - 1); ask_p = max(ask_p, FAIR + 1)

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
    # TOMATOES — dual FV + TAKE_EDGE=2 + passive CLEAR
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos, td):
        P = "TOMATOES"; orders = []

        # FILTERED MID (v10 submitted)
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

        # DUAL FAIR VALUE — reversion for TAKE, raw for MAKE
        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid

        # take_fair: with reversion (directional signal for aggressive orders)
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_BETA
            take_fair = round(filtered_mid * (1 + pred_return))
        else:
            take_fair = round(filtered_mid)

        # make_fair: raw filtered mid (unbiased center for passive quotes)
        make_fair = round(filtered_mid)

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE — using take_fair with EDGE=2 (only high-quality takes)
        for price in sorted(od.sell_orders.keys()):
            if price <= take_fair - T_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q)); buy_b -= q; pos += q
            else: break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= take_fair + T_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
            else: break

        # PASSIVE CLEAR — post at fair when we have inventory (0-EV capacity freeing)
        if pos > 0 and sell_b > 0:
            clear_qty = min(pos, sell_b, 10)  # cap at 10 to leave room for MAKE
            if clear_qty > 0:
                orders.append(Order(P, make_fair, -clear_qty))
                sell_b -= clear_qty; pos -= clear_qty
        if pos < 0 and buy_b > 0:
            clear_qty = min(-pos, buy_b, 10)
            if clear_qty > 0:
                orders.append(Order(P, make_fair, clear_qty))
                buy_b -= clear_qty; pos += clear_qty

        # MAKE — penny-jump using make_fair (unbiased, centered spread)
        best_ask_above = None
        for p in sorted(od.sell_orders.keys()):
            if p > make_fair + T_DISREGARD:
                best_ask_above = p; break
        best_bid_below = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < make_fair - T_DISREGARD:
                best_bid_below = p; break

        if best_bid_below is not None:
            bid_price = best_bid_below + 1
        else:
            bid_price = make_fair - T_DEFAULT_EDGE
        bid_price = min(bid_price, make_fair - 1)

        if best_ask_above is not None:
            ask_price = best_ask_above - 1
        else:
            ask_price = make_fair + T_DEFAULT_EDGE
        ask_price = max(ask_price, make_fair + 1)

        # Soft position limit
        if pos > T_SOFT_LIMIT:
            ask_price = max(ask_price - 1, make_fair + 1)
        elif pos < -T_SOFT_LIMIT:
            bid_price = min(bid_price + 1, make_fair - 1)

        # Hard limit
        if pos >= 70: buy_b = 0
        if pos <= -70: sell_b = 0

        if buy_b > 0:
            orders.append(Order(P, bid_price, buy_b))
        if sell_b > 0:
            orders.append(Order(P, ask_price, -sell_b))

        return orders

    @staticmethod
    def _obi(od) -> float:
        if not od.buy_orders or not od.sell_orders: return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0
