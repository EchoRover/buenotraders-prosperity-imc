"""
e1_v14 — v10 base + taker event exploitation.

KEY INSIGHT from PnL decomposition:
  - v10's ENTIRE profit is directional (spread capture is NEGATIVE)
  - 79.5% of fills are followed by favorable price moves
  - After taker events (tight spread), reversion is 6.27 per event over 5 ticks
  - Wide-spread ticks generate 84% of profit by volume

STRATEGY:
  - Keep v10's exact approach on normal ticks (84% of profit, don't break it)
  - After detecting a taker event (spread < 13), go AGGRESSIVE for 5 ticks:
    - Tighten spread from 6 to 4 (capture more of the reversion)
    - Increase take edge (take more aggressively)
  - Track taker events via traderData

EMERALDS: v10 exact (867, don't touch — products interfere)
TOMATOES: v10 base + taker event aggression
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# EMERALDS: v10 exact
# TOMATOES params
T_ADVERSE_VOL = 15
T_REVERSION_BETA = -0.229
T_TAKE_EDGE = 1
T_CLEAR_EDGE = 0
T_SPREAD_NORMAL = 6     # normal ticks
T_SPREAD_TAKER = 4      # tighter after taker event (capture reversion)
T_SKEW = 0.15
T_HARD_LIM = 40
T_L1_PCT = 0.65
T_L2_OFFSET = 2
T_TAKER_WINDOW = 5      # how many ticks to stay aggressive after taker event


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
        """v10 exact — proven 867, don't touch."""
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
        """v10 base + taker event exploitation."""
        P = "TOMATOES"; orders = []

        # Detect current spread
        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if best_bid is None or best_ask is None:
            return orders
        current_spread = best_ask - best_bid

        # Track taker events: when spread < 13, a taker just hit
        taker_countdown = td.get("tc", 0)
        if current_spread < 13:
            taker_countdown = T_TAKER_WINDOW  # reset: stay aggressive for 5 ticks
        elif taker_countdown > 0:
            taker_countdown -= 1
        td["tc"] = taker_countdown

        is_taker_mode = taker_countdown > 0

        # Filtered mid (vol >= 15) — v10 exact
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p; break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p; break
        if filtered_bid is None:
            filtered_bid = best_bid
        if filtered_ask is None:
            filtered_ask = best_ask

        filtered_mid = (filtered_bid + filtered_ask) / 2

        # Reversion — v10 exact
        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_BETA
            fair = round(filtered_mid * (1 + pred_return))
        else:
            fair = round(filtered_mid)

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE — same as v10
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

        # CLEAR — same as v10
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

        # MAKE — spread depends on whether taker just hit
        spread = T_SPREAD_TAKER if is_taker_mode else T_SPREAD_NORMAL

        skew = round(pos * T_SKEW)
        bid_price = fair - spread - skew
        ask_price = fair + spread - skew

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
