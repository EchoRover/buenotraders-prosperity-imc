"""
e1_v9 — Match LADDOO's approach exactly, then improve.

Step 1: Match LADDOO (2,102) by using his exact techniques:
  - EMERALDS: penny-jump + CLEAR (proven 867)
  - TOMATOES: ensemble fair value (0.45*wlr + 0.30*ema + 0.25*micro)
    Deep VWAP, weighted LR (decay=0.85), EMA (alpha=0.20), OBI=1.5
    Skew=0.01, spread=6, hard_limit=50, 2-layer 65/35

Step 2: Then beat it by adding limit=80 with matched hard_limit=80
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# TOMATOES params — matching LADDOO exactly
T_LR_WINDOW = 10
T_EMA_ALPHA = 0.20
T_DECAY = 0.85
T_OBI_WEIGHT = 1.5
T_TAKE_EDGE = 1
T_CLEAR_EDGE = 0
T_SPREAD = 6
T_SKEW = 0.01
T_HARD_LIMIT = 50
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
    # EMERALDS — penny-jump + CLEAR (proven 867)
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od, pos):
        FAIR = 10000
        P = "EMERALDS"
        orders = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # TAKE
        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - 1 and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q; pos += q
            else:
                break
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + 1 and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q; pos -= q
            else:
                break

        # CLEAR
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # MAKE — penny-jump
        bid_price = FAIR - 4
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - 1:
                bid_price = p + 1 if od.buy_orders[p] > 1 else p
                break
        bid_price = min(bid_price, FAIR - 1)

        ask_price = FAIR + 4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + 1:
                ask_price = p - 1 if abs(od.sell_orders[p]) > 1 else p
                break
        ask_price = max(ask_price, FAIR + 1)

        if pos > 25:
            bid_price -= 1; ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -25:
            ask_price += 1; bid_price = min(bid_price + 1, FAIR - 1)

        skew = round(pos * 0.12)
        bid_price = min(bid_price - skew, FAIR - 1)
        ask_price = max(ask_price - skew, FAIR + 1)

        if buy_b > 0:
            l1 = max(1, int(buy_b * T_L1_PCT))
            l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0:
                orders.append(Order(P, bid_price - 2, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * T_L1_PCT))
            l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_price + 2, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — LADDOO's ensemble fair value
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos, td):
        P = "TOMATOES"
        orders = []

        # Deep VWAP microprice (all levels, not just L1)
        micro = self._deep_vwap(od)
        if micro is None:
            return orders

        # State
        hist = td.get("th", [])
        hist.append(micro)
        if len(hist) > 25:
            hist = hist[-25:]
        td["th"] = hist

        # Signal 1: EMA
        prev_ema = td.get("te", micro)
        ema = T_EMA_ALPHA * micro + (1.0 - T_EMA_ALPHA) * prev_ema
        td["te"] = ema

        # Signal 2: Weighted linear regression
        lr_fair = micro
        if len(hist) >= 4:
            win = hist[-min(T_LR_WINDOW, len(hist)):]
            lr_fair = self._wlinreg(win)

        # Signal 3: Order book imbalance
        obi = self._obi(od)

        # Ensemble fair value — LADDOO's exact formula
        if len(hist) >= 8:
            fair = 0.45 * lr_fair + 0.30 * ema + 0.25 * micro
        elif len(hist) >= 4:
            fair = 0.30 * lr_fair + 0.30 * ema + 0.40 * micro
        else:
            fair = micro
        fair += obi * T_OBI_WEIGHT
        fair = round(fair)

        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

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
        bid_price = fair - T_SPREAD - skew
        ask_price = fair + T_SPREAD - skew

        if pos >= T_HARD_LIMIT:
            buy_b = 0
        if pos <= -T_HARD_LIMIT:
            sell_b = 0

        if buy_b > 0:
            l1 = max(1, int(buy_b * T_L1_PCT))
            l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0:
                orders.append(Order(P, bid_price - T_L2_OFFSET, l2))
        if sell_b > 0:
            l1 = max(1, int(sell_b * T_L1_PCT))
            l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_price + T_L2_OFFSET, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # UTILS — matching LADDOO's exact implementations
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _deep_vwap(od):
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
            return prices[-1]
        w = [T_DECAY ** (n - 1 - i) for i in range(n)]
        ws = sum(w)
        wmx = sum(wi * i for wi, i in zip(w, range(n))) / ws
        wmy = sum(wi * p for wi, p in zip(w, prices)) / ws
        wcov = sum(wi * (i - wmx) * (p - wmy) for wi, i, p in zip(w, range(n), prices))
        wvar = sum(wi * (i - wmx) ** 2 for wi, i in zip(w, range(n)))
        if wvar < 1e-10:
            return prices[-1]
        b = wcov / wvar
        return (wmy - b * wmx) + b * n

    @staticmethod
    def _obi(od):
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0
