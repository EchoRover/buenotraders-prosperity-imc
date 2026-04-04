"""
e1_v11 — v10 base + dynamic A-S spread + ensemble with filtered mid.

v10 scored 2,344 (our best). This builds on it with:
1. Filtered mid as input to a smoothed ensemble (not raw to reversion)
2. Avellaneda-Stoikov dynamic spread: wider when volatile, tighter when calm
3. Time-decay position penalty (flatten more aggressively near end)
4. Take edge=2 to reduce overtrading (v10 trades 2x LADDOO's volume)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
import math
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# A-S params for TOMATOES
T_GAMMA = 0.05          # risk aversion
T_TOTAL_TICKS = 2000    # session length
T_MIN_SPREAD = 4        # floor
T_MAX_SPREAD = 10       # ceiling
T_TAKE_EDGE = 2         # reduced from 1 to cut overtrading
T_SKEW = 0.15
T_HARD_LIM = 40
T_ADVERSE_VOL = 15
T_EMA_ALPHA = 0.20
T_REVERSION = -0.229


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
                result[product] = self.trade_tomatoes(od, pos, td, state.timestamp)

        return result, 0, json.dumps(td, separators=(',', ':'))

    def trade_emeralds(self, od, pos):
        """Same penny-jump + CLEAR as v10."""
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

    def trade_tomatoes(self, od, pos, td, timestamp):
        P = "TOMATOES"; orders = []

        # Filtered mid
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

        # EMA on filtered mid
        prev_ema = td.get("te", fmid)
        ema = T_EMA_ALPHA * fmid + (1 - T_EMA_ALPHA) * prev_ema
        td["te"] = ema

        # Track history for volatility estimation
        hist = td.get("h", [])
        hist.append(fmid)
        if len(hist) > 25:
            hist = hist[-25:]
        td["h"] = hist

        # Reversion signal
        prev_mid = td.get("pm", fmid)
        td["pm"] = fmid
        reversion_adj = 0
        if prev_mid != 0:
            last_return = fmid - prev_mid
            reversion_adj = last_return * T_REVERSION

        # Ensemble fair value: blend filtered mid, EMA, and reversion
        if len(hist) >= 8:
            fair = 0.40 * (fmid + reversion_adj) + 0.35 * ema + 0.25 * fmid
        else:
            fair = fmid

        fair = round(fair)

        # Dynamic spread from Avellaneda-Stoikov
        # sigma = recent volatility
        if len(hist) >= 5:
            returns = [hist[i] - hist[i-1] for i in range(max(1, len(hist)-10), len(hist))]
            sigma_sq = sum(r*r for r in returns) / len(returns) if returns else 1.0
        else:
            sigma_sq = 2.0  # default

        # Time remaining fraction
        t_frac = max(0.01, 1.0 - (timestamp / (T_TOTAL_TICKS * 100)))

        # A-S optimal spread
        as_spread = T_GAMMA * sigma_sq * t_frac + 2 / T_GAMMA * 0.1  # simplified
        spread = int(max(T_MIN_SPREAD, min(T_MAX_SPREAD, round(as_spread + 4))))

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # TAKE (with higher edge threshold)
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

        # MAKE with dynamic spread
        # Time-decay skew: flatten more as session progresses
        skew = round(pos * T_SKEW * (1 + (1 - t_frac)))  # skew increases toward end
        bid_price = fair - spread - skew
        ask_price = fair + spread - skew

        if pos >= T_HARD_LIM: buy_b = 0
        if pos <= -T_HARD_LIM: sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * 0.65)); l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0: orders.append(Order(P, bid_price - 2, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * 0.65)); l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0: orders.append(Order(P, ask_price + 2, -l2))

        return orders