"""
e1_v5 — Target: 3,000+ baseline.

Built from proven techniques across all research:
- EMERALDS: penny-jump + CLEAR + limit=80 (target: 1,050+)
- TOMATOES: low skew + CLEAR + linreg + 2-layer quoting + limit=80 (target: 2,000+)
- 3-phase pipeline every tick: TAKE → CLEAR → MAKE (from Linear Utility, 2nd place P2)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# EMERALDS
E_FAIR = 10000
E_TAKE_EDGE = 1        # take anything ≥1 from fair
E_DISREGARD = 1        # ignore bids/asks within 1 of fair for penny-jump
E_DEFAULT_EDGE = 4     # fallback if no book to penny-jump
E_SKEW = 0.12
E_SOFT_LIM = 25        # shift quotes 1 tick when inventory exceeds this
E_L1_PCT = 0.65        # 65% at tight level, 35% at backup
E_L2_OFFSET = 2

# TOMATOES
T_SPREAD = 6
T_SKEW = 0.03          # ultra-low skew — let positions ride trends
T_LR_LOOKBACK = 10
T_TAKE_EDGE = 1
T_HARD_LIM = 70        # stop quoting the increasing side past this
T_L1_PCT = 0.65
T_L2_OFFSET = 2


def mid_price(od):
    if not od.buy_orders or not od.sell_orders:
        return None
    return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2


def linreg_fair(prices):
    n = len(prices)
    if n < 2:
        return prices[-1]
    mx = (n - 1) / 2
    my = sum(prices) / n
    cov = sum((i - mx) * (p - my) for i, p in enumerate(prices))
    var = sum((i - mx) ** 2 for i in range(n))
    if var == 0:
        return prices[-1]
    b = cov / var
    return (my - b * mx) + b * n


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
    # EMERALDS — penny-jump + CLEAR (proven 867→1050 path)
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od: OrderDepth, pos: int) -> List[Order]:
        FAIR = E_FAIR
        P = "EMERALDS"
        orders: List[Order] = []
        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # ── PHASE 1: TAKE — sweep mispriced ──
        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR - E_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q
                pos += q
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR + E_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q
                pos -= q
            else:
                break

        # ── PHASE 2: CLEAR — flatten inventory at fair ──
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q
                        pos -= q
                else:
                    break

        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q
                        pos += q
                else:
                    break

        # ── PHASE 3: MAKE — penny-jump ──
        # Find best bot bid below fair (skip within DISREGARD of fair)
        bid_price = FAIR - E_DEFAULT_EDGE
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - E_DISREGARD:
                if od.buy_orders[p] > 1:
                    bid_price = p + 1  # penny-jump large orders
                else:
                    bid_price = p      # join small orders
                break
        bid_price = min(bid_price, FAIR - 1)

        # Find best bot ask above fair
        ask_price = FAIR + E_DEFAULT_EDGE
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + E_DISREGARD:
                if abs(od.sell_orders[p]) > 1:
                    ask_price = p - 1  # penny-jump
                else:
                    ask_price = p      # join
                break
        ask_price = max(ask_price, FAIR + 1)

        # Inventory-based adjustment
        if pos > E_SOFT_LIM:
            bid_price -= 1
            ask_price = max(ask_price - 1, FAIR + 1)
        elif pos < -E_SOFT_LIM:
            ask_price += 1
            bid_price = min(bid_price + 1, FAIR - 1)

        # Skew
        skew = round(pos * E_SKEW)
        bid_price -= skew
        ask_price -= skew
        bid_price = min(bid_price, FAIR - 1)
        ask_price = max(ask_price, FAIR + 1)

        # Two-layer quoting
        if buy_b > 0:
            l1 = max(1, int(buy_b * E_L1_PCT))
            l2 = buy_b - l1
            orders.append(Order(P, bid_price, l1))
            if l2 > 0:
                orders.append(Order(P, bid_price - E_L2_OFFSET, l2))

        if sell_b > 0:
            l1 = max(1, int(sell_b * E_L1_PCT))
            l2 = sell_b - l1
            orders.append(Order(P, ask_price, -l1))
            if l2 > 0:
                orders.append(Order(P, ask_price + E_L2_OFFSET, -l2))

        return orders

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — low skew + CLEAR + linreg + 2-layer
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        orders: List[Order] = []

        mid = mid_price(od)
        if mid is None:
            return orders

        # Price history for linreg
        hist = td.get("h", [])
        hist.append(mid)
        if len(hist) > 25:
            hist = hist[-25:]
        td["h"] = hist

        # Fair value
        if len(hist) >= T_LR_LOOKBACK:
            fair = round(linreg_fair(hist[-T_LR_LOOKBACK:]))
        else:
            fair = round(mid)

        buy_b = LIMITS[P] - pos
        sell_b = LIMITS[P] + pos

        # ── PHASE 1: TAKE ──
        for price in sorted(od.sell_orders.keys()):
            if price <= fair - T_TAKE_EDGE and buy_b > 0:
                q = min(-od.sell_orders[price], buy_b)
                orders.append(Order(P, price, q))
                buy_b -= q
                pos += q
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + T_TAKE_EDGE and sell_b > 0:
                q = min(od.buy_orders[price], sell_b)
                orders.append(Order(P, price, -q))
                sell_b -= q
                pos -= q
            else:
                break

        # ── PHASE 2: CLEAR — flatten at fair ──
        if pos > 0 and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair and sell_b > 0 and pos > 0:
                    q = min(od.buy_orders[price], sell_b, pos)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q
                        pos -= q
                else:
                    break

        if pos < 0 and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair and buy_b > 0 and pos < 0:
                    q = min(-od.sell_orders[price], buy_b, -pos)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q
                        pos += q
                else:
                    break

        # ── PHASE 3: MAKE ──
        skew = round(pos * T_SKEW)
        bid_price = fair - T_SPREAD - skew
        ask_price = fair + T_SPREAD - skew

        # Hard brake at extreme inventory
        if pos >= T_HARD_LIM:
            buy_b = 0
        if pos <= -T_HARD_LIM:
            sell_b = 0

        # Two-layer quoting
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
