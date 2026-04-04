"""
LADDOO BOT_L4 — Sweep-Optimized Ultimate Edition
==================================================
Systematic parameter sweep across 100+ variants found optimal:
  L2 baseline: 32,002  →  L4 optimized: 32,934+ (+932)

Key improvements over L2:
  1. E_SKEW 0.12 → 0.00 (let CLEAR + soft_limit handle inventory)
  2. T_OBI_WEIGHT 1.5 → 1.2 (reduced OBI overcorrection)
  3. L2_OFFSET 2 → 1 (tighter 2nd layer = more fills)
  4. EMERALDS volume imbalance quote tightening (structural)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
import math
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# EMERALDS — sweep-optimized
E_FAIR         = 10_000
E_TAKE_EDGE    = 1
E_CLEAR_EDGE   = 0
E_DEFAULT_EDGE = 4
E_DISREGARD    = 1
E_SKEW         = 0.00
E_SOFT_LIMIT   = 25
E_L2_OFFSET    = 1
E_L1_PCT       = 0.65
E_IMB_THRESH   = 0.12

# TOMATOES — sweep-optimized
T_LR_WINDOW    = 10
T_EMA_ALPHA    = 0.20
T_DECAY        = 0.85
T_OBI_WEIGHT   = 1.2
T_TAKE_EDGE    = 1
T_CLEAR_EDGE   = 0
T_SPREAD       = 6
T_SKEW         = 0.01
T_HARD_LIMIT   = 50
T_L2_OFFSET    = 1
T_L1_PCT       = 0.65


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
                result[product] = self._emeralds(od, pos, td)
            elif product == "TOMATOES":
                result[product] = self._tomatoes(od, pos, td)

        return result, 0, json.dumps(td, separators=(',', ':'))

    def _emeralds(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "EMERALDS"
        FAIR = E_FAIR
        LIM = LIMITS[P]
        orders: List[Order] = []
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

        # CLEAR
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

        # MAKE: penny-jump + volume imbalance + skew
        bid_p = FAIR - E_DEFAULT_EDGE
        if od.buy_orders:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p < FAIR - E_DISREGARD:
                    bid_p = p + 1
                    break
        bid_p = min(bid_p, FAIR - 1)

        if pos > E_SOFT_LIMIT:
            bid_p -= 1
        if pos < -E_SOFT_LIMIT:
            bid_p = min(bid_p + 1, FAIR - 1)

        ask_p = FAIR + E_DEFAULT_EDGE
        if od.sell_orders:
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + E_DISREGARD:
                    ask_p = p - 1
                    break
        ask_p = max(ask_p, FAIR + 1)

        if pos < -E_SOFT_LIMIT:
            ask_p += 1
        if pos > E_SOFT_LIMIT:
            ask_p = max(ask_p - 1, FAIR + 1)

        # Volume imbalance tightening
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

    def _tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        LIM = LIMITS[P]
        orders: List[Order] = []

        micro = self._deep_vwap(od)
        if micro is None:
            return orders

        hist = td.get("th", [])
        hist.append(micro)
        if len(hist) > 25:
            hist = hist[-25:]
        td["th"] = hist

        prev_ema = td.get("te", micro)
        ema = T_EMA_ALPHA * micro + (1.0 - T_EMA_ALPHA) * prev_ema
        td["te"] = ema

        lr_fair = micro
        slope = 0.0
        if len(hist) >= 4:
            win = hist[-min(T_LR_WINDOW, len(hist)):]
            lr_fair, slope = self._wlinreg(win)

        obi = self._obi(od)

        if len(hist) >= 8:
            fair = 0.45 * lr_fair + 0.30 * ema + 0.25 * micro
        elif len(hist) >= 4:
            fair = 0.30 * lr_fair + 0.30 * ema + 0.40 * micro
        else:
            fair = micro
        fair += obi * T_OBI_WEIGHT
        fair = round(fair)

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

        # CLEAR
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

        # MAKE
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

    @staticmethod
    def _deep_vwap(od: OrderDepth):
        if not od.buy_orders or not od.sell_orders:
            return None
        bw = sum(p * v for p, v in od.buy_orders.items())
        bv = sum(od.buy_orders.values())
        aw = sum(p * abs(v) for p, v in od.sell_orders.items())
        av = sum(abs(v) for v in od.sell_orders.values())
        if bv <= 0 or av <= 0:
            if bv > 0: return bw / bv
            if av > 0: return aw / av
            return None
        return (av * (bw / bv) + bv * (aw / av)) / (bv + av)

    @staticmethod
    def _wlinreg(prices):
        n = len(prices)
        if n < 2:
            return prices[-1], 0.0
        w = [T_DECAY ** (n - 1 - i) for i in range(n)]
        ws = sum(w)
        wmx = sum(wi * i for wi, i in zip(w, range(n))) / ws
        wmy = sum(wi * p for wi, p in zip(w, prices)) / ws
        wcov = sum(wi * (i - wmx) * (p - wmy) for wi, i, p in zip(w, range(n), prices))
        wvar = sum(wi * (i - wmx) ** 2 for wi, i in zip(w, range(n)))
        if wvar < 1e-10:
            return prices[-1], 0.0
        b = wcov / wvar
        return (wmy - b * wmx) + b * n, b

    @staticmethod
    def _obi(od: OrderDepth) -> float:
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0
