"""
e1_fool3 — From ACTUAL v10 (47816.py). Two changes targeting the TAKE decision.

KEY INSIGHT: v10 TOMATOES is 100% TAKE fills. MAKE never fills (queue priority).
The ONLY thing that matters is the fair value used for TAKE decisions.
Everything else (spread, skew, layers, CLEAR) is irrelevant noise.

CHANGE 1: Stronger reversion beta (-0.35 instead of -0.229)
  - Our data says optimal prediction is -0.44
  - v8 tried -0.4 but with static spread (wrong MAKE code) and scored badly
  - With penny-jump MAKE (takes only), stronger reversion = more/better takes
  - -0.35 is a compromise between LU's -0.229 and data-optimal -0.44

CHANGE 2: Use market_trades to log bot activity (print to stdout for analysis)
  - state.market_trades has bot-to-bot trades we've NEVER analyzed
  - This version LOGS them so we can study what's available
  - Future versions can USE them for directional prediction
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# Linear Utility's params — ONLY changed reversion beta
T_ADVERSE_VOL = 15
T_REVERSION_BETA = -0.35   # CHANGED from -0.229 (stronger reversion)
T_TAKE_EDGE = 1
T_CLEAR_EDGE = 0
T_DISREGARD = 1
T_JOIN_EDGE = 0
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

        # Log market trades for analysis (won't affect PnL)
        mt_count = 0
        for product in state.market_trades:
            mt_count += len(state.market_trades[product])
        if mt_count > 0:
            td["mt"] = mt_count  # just track count for now

        return result, 0, json.dumps(td, separators=(',', ':'))

    def trade_emeralds(self, od, pos):
        """v10 exact EMERALDS (penny-jump + CLEAR, proven 867)."""
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
        """v10 TOMATOES with stronger reversion (-0.35)."""
        P = "TOMATOES"; orders = []

        # FILTERED MID
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

        prev_mid = td.get("pm", filtered_mid)
        td["pm"] = filtered_mid

        # REVERSION — stronger beta
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

        # MAKE — penny-jump (THE critical code from v10)
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
