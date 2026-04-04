"""
e1_v15 — Dual fair value: separate TAKE signal from MAKE center.

THEORY INSIGHT (from market microstructure books):
  v10's spread capture is NEGATIVE (-24). Our reversion signal biases
  the fair value, making MAKE quotes off-center. We lose on every fill
  at execution, then make it back on favorable post-fill moves.

  Professional MMs separate "theoretical value" (for quoting) from
  "alpha signal" (for directional bets).

FIX: Two fair values.
  MAKE_FAIR = filtered mid (no reversion) → centered quotes → positive spread capture
  TAKE_FAIR = filtered mid + reversion → directional accuracy → capture reversions

This should earn BOTH spread AND direction. v10 only earns direction.

EMERALDS: v10 exact (867)
TOMATOES: v10 base but with dual fair value
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

T_ADVERSE_VOL = 15
T_REVERSION_BETA = -0.229
T_TAKE_EDGE = 1
T_CLEAR_EDGE = 0
T_SPREAD = 6
T_SKEW = 0.15
T_HARD_LIM = 40
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

    def trade_emeralds(self, od, pos):
        """v10 exact."""
        FAIR = 10000; P = "EMERALDS"; orders = []
        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - 1 and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q)); buy_b -= q; pos += q
            else: break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + 1 and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
            else: break

        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        bid_price = FAIR - 4
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - 1:
                bid_price = p + 1 if od.buy_orders[p] > 1 else p; break
        bid_price = min(bid_price, FAIR - 1)
        ask_price = FAIR + 4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + 1:
                ask_price = p - 1 if abs(od.sell_orders[p]) > 1 else p; break
        ask_price = max(ask_price, FAIR + 1)

        if pos > 25: bid_price -= 1; ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -25: ask_price += 1; bid_price = min(bid_price + 1, FAIR - 1)
        skew = round(pos * 0.12)
        bid_price = min(bid_price - skew, FAIR - 1)
        ask_price = max(ask_price - skew, FAIR + 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.65)); orders.append(Order(P, bid_price, l1))
            if buy_b - l1 > 0: orders.append(Order(P, bid_price - 2, buy_b - l1))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.65)); orders.append(Order(P, ask_price, -l1))
            if sell_b - l1 > 0: orders.append(Order(P, ask_price + 2, -(sell_b - l1)))
        return orders

    def trade_tomatoes(self, od, pos, td):
        """Dual fair value: MAKE centered on mid, TAKE guided by reversion."""
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

        # MAKE FAIR VALUE: just the filtered mid, no reversion bias
        make_fair = round(filtered_mid)

        # TAKE FAIR VALUE: filtered mid + reversion (directional signal)
        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid
        take_fair = make_fair  # default
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_BETA
            take_fair = round(filtered_mid * (1 + pred_return))

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE: use directional fair value
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

        # CLEAR: use make fair value (centered)
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= make_fair and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0: orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else: break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= make_fair and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0: orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else: break

        # MAKE: use centered fair value (no reversion bias)
        skew = round(pos * T_SKEW)
        bid_price = make_fair - T_SPREAD - skew
        ask_price = make_fair + T_SPREAD - skew

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