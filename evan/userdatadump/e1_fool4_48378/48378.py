"""
e1_fool4 — DIRECTIONAL TAKER-EVENT FADING.

NOT market making. This is a directional trading strategy.

THE DATA:
  After UP taker event: price drops 3.10 in 5 ticks (95%+ confidence)
  After DOWN taker event: price rises 3.36 in 5 ticks
  116 events per session × ~3.2 avg move × position size = massive PnL

THE STRATEGY:
  Normal ticks: v10's approach (filtered mid + reversion + penny-jump MAKE)
  Taker tick detected: AGGRESSIVELY fade the move
    - Taker pushed UP → take every available ASK (go long to sell on reversion...
      wait no, taker UP means price will DROP, so we should SELL)
    - Taker pushed DOWN → take every available BID (price will RISE, so BUY)
  Hold for 5 ticks, then revert to normal v10 behavior.

  The key insight: on taker ticks, we KNOW the direction.
  We should use our ENTIRE available capacity on that signal.

EMERALDS: crazy1 approach (1,050)
TOMATOES: v10 base + aggressive taker fading
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

E_LIMIT = 80
T_LIMIT = 50

T_ADVERSE_VOL = 15
T_REVERSION_BETA = -0.229
T_TAKE_EDGE = 1
T_DISREGARD = 1
T_DEFAULT_EDGE = 2
T_SOFT_LIMIT = 10


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
        """crazy1 EMERALDS (proven 1,050): zero skew, limit=80."""
        FAIR = 10000; P = "EMERALDS"; orders = []
        buy_b = E_LIMIT - pos; sell_b = E_LIMIT + pos

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

        # Zero skew (crazy1's breakthrough)
        if pos > 25: bid_price -= 1; ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -25: ask_price += 1; bid_price = min(bid_price + 1, FAIR - 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.65)); orders.append(Order(P, bid_price, l1))
            if buy_b - l1 > 0: orders.append(Order(P, bid_price - 1, buy_b - l1))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.65)); orders.append(Order(P, ask_price, -l1))
            if sell_b - l1 > 0: orders.append(Order(P, ask_price + 1, -(sell_b - l1)))
        return orders

    def trade_tomatoes(self, od, pos, td):
        """v10 base + aggressive taker-event fading."""
        P = "TOMATOES"; orders = []

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if best_bid is None or best_ask is None:
            return orders

        current_spread = best_ask - best_bid
        current_mid = (best_bid + best_ask) / 2

        # Track previous mid and spread for taker detection
        prev_mid = td.get("pm", current_mid)
        prev_spread = td.get("ps", 14)
        td["ps"] = current_spread

        # Filtered mid (v10 approach)
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p; break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p; break
        if filtered_bid is None: filtered_bid = best_bid
        if filtered_ask is None: filtered_ask = best_ask
        filtered_mid = (filtered_bid + filtered_ask) / 2
        td["pm"] = filtered_mid

        # Reversion fair value (v10 approach)
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_BETA
            fair = round(filtered_mid * (1 + pred_return))
        else:
            fair = round(filtered_mid)

        # Detect taker event: spread just narrowed significantly
        taker_event = current_spread < prev_spread - 2
        taker_direction = 0  # +1 = taker pushed price UP, -1 = DOWN
        if taker_event:
            mid_change = current_mid - prev_mid
            if mid_change > 0.5:
                taker_direction = 1   # pushed UP → will revert DOWN
            elif mid_change < -0.5:
                taker_direction = -1  # pushed DOWN → will revert UP

        buy_b = T_LIMIT - pos; sell_b = T_LIMIT + pos

        # === PHASE 1: NORMAL TAKES (v10 approach) ===
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

        # === PHASE 2: AGGRESSIVE TAKER FADING ===
        # On taker events, take MORE in the reversion direction
        if taker_direction == 1 and sell_b > 0:
            # Taker pushed UP → price will DROP → SELL aggressively
            # Take any bid at or above current mid (even at 0 edge)
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= round(current_mid) - 1 and sell_b > 0:
                    q = min(od.buy_orders[price], sell_b, 15)  # cap at 15 per level
                    if q > 0:
                        orders.append(Order(P, price, -q)); sell_b -= q; pos -= q
                else:
                    break
        elif taker_direction == -1 and buy_b > 0:
            # Taker pushed DOWN → price will RISE → BUY aggressively
            for price in sorted(od.sell_orders.keys()):
                if price <= round(current_mid) + 1 and buy_b > 0:
                    q = min(-od.sell_orders[price], buy_b, 15)
                    if q > 0:
                        orders.append(Order(P, price, q)); buy_b -= q; pos += q
                else:
                    break

        # === PHASE 3: CLEAR (v10 approach) ===
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

        # === PHASE 4: MAKE (v10 penny-jump approach) ===
        best_ask_above = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair + T_DISREGARD:
                best_ask_above = p; break
        best_bid_below = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - T_DISREGARD:
                best_bid_below = p; break

        if best_bid_below is not None:
            bid_price = best_bid_below + 1
        else:
            bid_price = fair - T_DEFAULT_EDGE
        bid_price = min(bid_price, fair - 1)

        if best_ask_above is not None:
            ask_price = best_ask_above - 1
        else:
            ask_price = fair + T_DEFAULT_EDGE
        ask_price = max(ask_price, fair + 1)

        if pos > T_SOFT_LIMIT:
            ask_price = max(ask_price - 1, fair + 1)
        elif pos < -T_SOFT_LIMIT:
            bid_price = min(bid_price + 1, fair - 1)

        if pos >= 50: buy_b = 0
        if pos <= -50: sell_b = 0

        if buy_b > 0:
            orders.append(Order(P, bid_price, buy_b))
        if sell_b > 0:
            orders.append(Order(P, ask_price, -sell_b))

        return orders