"""
e1_v13 — v10 exact code + EMERALDS zero skew (from crazy1).

ONLY CHANGE from v10: E_SKEW 0.12 → 0.00
Everything else byte-for-byte identical to v10 which scored 2,344.
crazy1's zero skew got EMERALDS from 867→1050.
If this works: 1,050 + 1,477 = 2,527.
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# Linear Utility's exact params for trending product
T_ADVERSE_VOL = 15      # filter: only use levels with 15+ volume
T_REVERSION_BETA = -0.229  # fade 22.9% of last move
T_TAKE_EDGE = 1
T_CLEAR_EDGE = 0
T_DISREGARD = 1         # ignore within 1 of fair for penny-jump
T_JOIN_EDGE = 0          # never join, always penny (LU's starfruit setting)
T_DEFAULT_EDGE = 2       # LU's min_edge for starfruit
T_SOFT_LIMIT = 10        # shift quotes when pos > this


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
        skew = round(pos * 0.00)  # zero skew — crazy1's EMERALD breakthrough
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
        P = "TOMATOES"; orders = []

        # FILTERED MID: only use levels with 15+ volume
        # This finds the market maker's quotes, filtering noise
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p; break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p; break

        # Fallback to best bid/ask if no large levels
        if filtered_bid is None:
            filtered_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        if filtered_ask is None:
            filtered_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if filtered_bid is None or filtered_ask is None:
            return orders

        filtered_mid = (filtered_bid + filtered_ask) / 2

        # Track for reversion
        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid

        # REVERSION FAIR VALUE — Linear Utility's formula
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_BETA
            fair = round(filtered_mid * (1 + pred_return))
        else:
            fair = round(filtered_mid)

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

        # MAKE — static spread (NOT penny-jump — Lakshan proved it fails on TOMATOES)
        skew = round(pos * 0.15)
        bid_price = fair - 6 - skew
        ask_price = fair + 6 - skew

        if pos >= 40: buy_b = 0
        if pos <= -40: sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.65)); l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0: orders.append(Order(P, bid_price - 2, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.65)); l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0: orders.append(Order(P, ask_price + 2, -l2))

        return orders
