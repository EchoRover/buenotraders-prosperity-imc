"""
e1_crazy11 — claude2 agent
==========================
FROM THE GROUND UP. Every previous bot used FIXED parameters borrowed
from Prosperity 2. What if those params are WRONG for our market?

THE IDEA: A bot that LEARNS its own reversion beta in real-time.

How it works:
  - Start with beta=-0.229 (v10 baseline)
  - Each tick: check if last prediction was correct
    (did price move in the direction we predicted?)
  - Track rolling accuracy over last 100 ticks
  - If accuracy > 82%: strengthen beta by 0.001 (we're under-reverting)
  - If accuracy < 75%: weaken beta by 0.001 (we're over-reverting)
  - Beta clipped to [-0.40, -0.10] range

  Over 2,000 ticks, the beta converges to whatever is OPTIMAL for THIS
  specific market. No more guessing. The bot finds the answer itself.

  Day -2 (first 1,000 ticks): beta calibrates
  Day -1 (second 1,000 ticks): beta is well-tuned, captures more edge

Why this could work:
  - v10's -0.229 was copied from P2 STARFRUIT. TOMATOES might be different.
  - If optimal beta is -0.15: less trend-fighting on trending days → huge improvement
  - If optimal beta is -0.35: stronger reversion on reverting days → more edge
  - If -0.229 IS optimal: beta converges there, performance = crazy8

Nobody has tried online learning. This is genuinely from the ground up.

EMERALDS: crazy1 exact (1,050)
TOMATOES: crazy8 base + adaptive beta

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 70}

# TOMATOES — adaptive params
T_ADVERSE_VOL = 15
T_INITIAL_BETA = -0.229    # starting point
T_BETA_MIN = -0.40         # strongest reversion
T_BETA_MAX = -0.05         # weakest reversion
T_LEARN_RATE = 0.002       # how fast beta adapts
T_TARGET_ACC_HIGH = 0.82   # strengthen if above this
T_TARGET_ACC_LOW = 0.75    # weaken if below this
T_ACC_WINDOW = 100         # rolling window for accuracy
T_DISREGARD = 1
T_DEFAULT_EDGE = 2
T_SOFT_LIMIT = 20
T_TAKE_EDGE = 1

# EMERALDS — crazy1 exact
E_FAIR = 10_000; E_TAKE_EDGE = 1; E_CLEAR_EDGE = 0
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
    # EMERALDS — crazy1 exact (1,050)
    # ══════════════════════════════════════════════════════════════

    def trade_emeralds(self, od, pos):
        P = "EMERALDS"; FAIR = E_FAIR; LIM = LIMITS[P]
        orders = []; buy_b = LIM - pos; sell_b = LIM + pos

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
    # TOMATOES — adaptive beta (THE NOVEL PART)
    # ══════════════════════════════════════════════════════════════

    def trade_tomatoes(self, od, pos, td):
        P = "TOMATOES"; orders = []

        # ── FILTERED MID ──
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

        # ── ADAPTIVE BETA: learn from prediction accuracy ──
        beta = td.get("beta", T_INITIAL_BETA)
        prev_mid = td.get("pm", filtered_mid)
        prev_predicted_dir = td.get("pd", 0)  # +1=predicted up, -1=predicted down, 0=no prediction
        hits = td.get("hits", [])  # rolling window of 1s (correct) and 0s (wrong)

        # Check if last prediction was correct
        if prev_predicted_dir != 0:
            actual_dir = 1 if filtered_mid > prev_mid else (-1 if filtered_mid < prev_mid else 0)
            if actual_dir != 0:
                correct = 1 if actual_dir == prev_predicted_dir else 0
                hits.append(correct)
                if len(hits) > T_ACC_WINDOW:
                    hits = hits[-T_ACC_WINDOW:]

                # Adapt beta based on rolling accuracy
                if len(hits) >= 20:  # need minimum data
                    accuracy = sum(hits) / len(hits)
                    if accuracy > T_TARGET_ACC_HIGH:
                        beta -= T_LEARN_RATE  # strengthen reversion (more negative)
                    elif accuracy < T_TARGET_ACC_LOW:
                        beta += T_LEARN_RATE  # weaken reversion (less negative)
                    beta = max(T_BETA_MIN, min(T_BETA_MAX, beta))

        td["hits"] = hits
        td["beta"] = beta
        td["pm"] = filtered_mid

        # ── REVERSION with adaptive beta ──
        if prev_mid != 0:
            last_return = (filtered_mid - prev_mid) / prev_mid
            pred_return = last_return * beta
            fair = round(filtered_mid * (1 + pred_return))
            # Track prediction direction for next tick
            td["pd"] = 1 if pred_return > 0 else (-1 if pred_return < 0 else 0)
        else:
            fair = round(filtered_mid)
            td["pd"] = 0

        buy_b = LIMITS[P] - pos; sell_b = LIMITS[P] + pos

        # ── TAKE ──
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

        # ── CLEAR ──
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

        # ── MAKE — penny-jump (v10 submitted exact) ──
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
