"""
e1_crazy3 — claude2 agent
=========================
Three contrarian bets on TOMATOES. Same energy that found the EMERALDS breakthrough.

EMERALDS: crazy1 exact (proven 1,050, don't touch)

TOMATOES — challenging every convention:

  1. ZERO SKEW (contrarian bet #1)
     Every bot uses skew 0.01-0.20. But CLEAR handles inventory.
     Skew is a tax on fills — it pushes your quotes away from the action.
     Proven on EMERALDS (0.00 → +21% fills). Never tested on TOMATOES.
     With limit=50 + hard_limit=40, positions can't spiral.

  2. WIDER SPREAD = 8 (contrarian bet #2)
     Everyone uses 6. But filtered mid is accurate, so wider spread
     = more profit per fill without losing fill quality.
     Our quotes land BEHIND the bot makers (~fair±6.5).
     Takers hit bots first — we only fill on strong moves = less adverse selection.
     Each fill is +33% more profitable (8 vs 6 per side).

  3. CONDITIONAL REVERSION (contrarian bet #3)
     v10 fades every tick at -0.229. But data shows:
     - Tight spread (<10) = post-taker event, 97.8% reversion win rate
     - Normal spread (>=10) = drift, reversion may fight trend
     So: only fade on tight-spread ticks (strong -0.40), raw filtered mid otherwise.
     This maximizes edge on the 7% of high-quality ticks.

Limit=50, hard=40 — learned from crazy2 that limit=80 kills TOMATOES.
CLEAR at fair — standard, proven.

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 50}

# ═══════════════════════════════════════════
# EMERALDS — crazy1 exact (proven 1,050)
# ═══════════════════════════════════════════
E_FAIR         = 10_000
E_TAKE_EDGE    = 1
E_CLEAR_EDGE   = 0
E_DEFAULT_EDGE = 4
E_DISREGARD    = 1
E_SKEW         = 0.00
E_SOFT_LIMIT   = 25
E_L1_PCT       = 0.65
E_L2_OFFSET    = 1
E_IMB_THRESH   = 0.12
E_AGGRO_POS    = 30
E_AGGRO_TARG   = 15

# ═══════════════════════════════════════════
# TOMATOES — the three contrarian bets
# ═══════════════════════════════════════════
T_ADVERSE_VOL  = 15        # filtered mid threshold
T_TAKE_EDGE    = 1
T_CLEAR_EDGE   = 0
T_SPREAD       = 8         # BET #2: wider (was 6)
T_SKEW         = 0.00      # BET #1: zero (was 0.10-0.15)
T_HARD_LIMIT   = 40        # keep tight (learned from crazy2)
T_L1_PCT       = 0.65
T_L2_OFFSET    = 2

# Regime-switching reversion (BET #3)
T_TIGHT_SPREAD = 10        # spread threshold for regime switch
T_REVERSION_TIGHT = -0.40  # strong fade on taker events
T_REVERSION_NORMAL = 0.00  # no fade on normal ticks (don't fight trend)


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
                result[product] = self._emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self._tomatoes(od, pos, td)

        return result, 0, json.dumps(td, separators=(',', ':'))

    # ══════════════════════════════════════════════════════════════
    # EMERALDS — crazy1 exact (proven 1,050)
    # ══════════════════════════════════════════════════════════════

    def _emeralds(self, od, pos):
        P = "EMERALDS"
        FAIR = E_FAIR
        LIM = LIMITS[P]
        orders = []
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

        # CLEAR at fair
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

        # AGGRESSIVE CLEAR at fair±1 when extreme
        if pos > E_AGGRO_POS and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= FAIR - 1 and sell_b > 0 and pos > E_AGGRO_TARG:
                    q = min(od.buy_orders[price], sell_b, pos - E_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < -E_AGGRO_POS and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= FAIR + 1 and buy_b > 0 and pos < -E_AGGRO_TARG:
                    q = min(-od.sell_orders[price], buy_b, -pos - E_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # MAKE: penny-jump + OBI
        bid_p = FAIR - E_DEFAULT_EDGE
        if od.buy_orders:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p < FAIR - E_DISREGARD:
                    bid_p = p + 1
                    break
        bid_p = min(bid_p, FAIR - 1)

        ask_p = FAIR + E_DEFAULT_EDGE
        if od.sell_orders:
            for p in sorted(od.sell_orders.keys()):
                if p > FAIR + E_DISREGARD:
                    ask_p = p - 1
                    break
        ask_p = max(ask_p, FAIR + 1)

        if pos > E_SOFT_LIMIT:
            bid_p -= 1
            ask_p = max(ask_p - 1, FAIR + 1)
        if pos < -E_SOFT_LIMIT:
            ask_p += 1
            bid_p = min(bid_p + 1, FAIR - 1)

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

    # ══════════════════════════════════════════════════════════════
    # TOMATOES — three contrarian bets
    # ══════════════════════════════════════════════════════════════

    def _tomatoes(self, od, pos, td):
        P = "TOMATOES"
        LIM = LIMITS[P]
        orders = []

        # ── FILTERED MID (v10's proven approach) ──
        filtered_bid = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVERSE_VOL:
                filtered_bid = p
                break
        filtered_ask = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVERSE_VOL:
                filtered_ask = p
                break
        if filtered_bid is None:
            filtered_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        if filtered_ask is None:
            filtered_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if filtered_bid is None or filtered_ask is None:
            return orders

        fmid = (filtered_bid + filtered_ask) / 2
        spread_width = filtered_ask - filtered_bid

        # ── CONDITIONAL REVERSION (BET #3) ──
        # Only fade after taker events (tight spread), don't fight trends otherwise
        prev_mid = td.get("pm", fmid)
        td["pm"] = fmid

        if spread_width < T_TIGHT_SPREAD and prev_mid != 0:
            # Tight spread = post-taker event, strong reversion signal
            last_return = (fmid - prev_mid) / prev_mid
            pred_return = last_return * T_REVERSION_TIGHT
            fair = round(fmid * (1 + pred_return))
        else:
            # Normal spread = no reversion, just use filtered mid
            fair = round(fmid)

        buy_b = LIM - pos
        sell_b = LIM + pos

        # ── TAKE ──
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

        # ── CLEAR at fair ──
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

        # ── MAKE: wider spread + zero skew (BETS #1 and #2) ──
        skew = round(pos * T_SKEW)  # = 0 with T_SKEW=0.00
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

    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _obi(od) -> float:
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0