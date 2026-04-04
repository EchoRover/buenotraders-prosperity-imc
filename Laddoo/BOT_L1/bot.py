"""
LADDOO BOT_L1 — IMC Prosperity 4 Tutorial Round
=================================================
Products: EMERALDS (stable, fair=10000) + TOMATOES (trending ~5000)
Position limits: 50 each

Beats all competitor bots (45609-45834) via:
 - Multi-layer passive quoting (3 price levels per side)
 - Deep VWAP microprice from all order book levels
 - EMA + Weighted Regression + Order Book Imbalance ensemble
 - Asymmetric inventory skewing (sell faster when long, buy faster when short)
 - Volatility-adaptive spreads for TOMATOES
 - Trend-aware quoting with dynamic cap
 - Correct position budget tracking (no double-count bug)
 - Emergency inventory dump at high utilization
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
import math
from typing import Dict, List

# ============================================================
# CONSTANTS
# ============================================================
LIMITS = {"EMERALDS": 50, "TOMATOES": 50}

# EMERALDS: proven optimal from parameter sweep on tutorial data
E_FAIR = 10000

# TOMATOES: tuned for adaptive behavior
T_LR_WINDOW = 12        # weighted regression lookback
T_BASE_SPREAD = 4       # base half-spread (adaptive ± volatility)
T_DECAY = 0.82          # exponential weight decay for regression
T_EMA_BASE_ALPHA = 0.15 # base EMA smoothing factor


# ============================================================
# TRADER CLASS
# ============================================================
class Trader:

    def run(self, state: TradingState):
        # --- Load persistent state ---
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
                result[product] = self._trade_emeralds(od, pos, td)
            elif product == "TOMATOES":
                result[product] = self._trade_tomatoes(od, pos, td)

        return result, 0, json.dumps(td, separators=(',', ':'))

    # ============================================================
    # EMERALDS — Fixed fair value, multi-layer market making
    # ============================================================
    def _trade_emeralds(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "EMERALDS"
        FAIR = E_FAIR
        LIM = LIMITS[P]
        orders: List[Order] = []

        buy_bgt = LIM - pos   # max additional units we can buy
        sell_bgt = LIM + pos   # max additional units we can sell

        # ----------------------------------------------------------
        # PHASE 1: AGGRESSIVE TAKE — sweep all mispriced orders
        # ----------------------------------------------------------
        # Buy every ask strictly below fair value (guaranteed profit)
        for price in sorted(od.sell_orders.keys()):
            if price < FAIR and buy_bgt > 0:
                qty = min(-od.sell_orders[price], buy_bgt)
                if qty > 0:
                    orders.append(Order(P, price, qty))
                    buy_bgt -= qty
                    pos += qty
            elif price == FAIR and buy_bgt > 0:
                # Take at exactly fair only to reduce heavy short exposure
                if pos < -int(LIM * 0.3):
                    qty = min(-od.sell_orders[price], buy_bgt,
                              abs(pos) - int(LIM * 0.2))
                    if qty > 0:
                        orders.append(Order(P, price, qty))
                        buy_bgt -= qty
                        pos += qty
            else:
                break

        # Sell every bid strictly above fair value
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price > FAIR and sell_bgt > 0:
                qty = min(od.buy_orders[price], sell_bgt)
                if qty > 0:
                    orders.append(Order(P, price, -qty))
                    sell_bgt -= qty
                    pos -= qty
            elif price == FAIR and sell_bgt > 0:
                # Take at exactly fair only to reduce heavy long exposure
                if pos > int(LIM * 0.3):
                    qty = min(od.buy_orders[price], sell_bgt,
                              pos - int(LIM * 0.2))
                    if qty > 0:
                        orders.append(Order(P, price, -qty))
                        sell_bgt -= qty
                        pos -= qty
            else:
                break

        # ----------------------------------------------------------
        # PHASE 2: MULTI-LAYER PASSIVE QUOTING
        # ----------------------------------------------------------
        # Asymmetric skew: push harder on the side that reduces position
        if pos > 0:
            skew_b = round(pos * 0.08)   # gentle on buy side
            skew_a = round(pos * 0.18)   # aggressive on sell side
        elif pos < 0:
            skew_b = round(pos * 0.18)   # aggressive on buy side (neg * neg = pull up)
            skew_a = round(pos * 0.08)
        else:
            skew_b = 0
            skew_a = 0

        # Layer allocation — heavier on wide levels (proven more profitable)
        #   offset from fair, fraction of remaining budget
        layers = [
            (4, 0.15),   # tight: captures aggressive counterparties
            (7, 0.50),   # sweet spot (45769's winning parameter)
            (9, 0.35),   # wide: maximum profit per fill
        ]

        for offset, frac in layers:
            bp = FAIR - offset - skew_b
            ap = FAIR + offset - skew_a

            bq = max(1, round(buy_bgt * frac))
            aq = max(1, round(sell_bgt * frac))
            bq = min(bq, buy_bgt)
            aq = min(aq, sell_bgt)

            if bq > 0 and buy_bgt > 0:
                orders.append(Order(P, bp, bq))
                buy_bgt -= bq
            if aq > 0 and sell_bgt > 0:
                orders.append(Order(P, ap, -aq))
                sell_bgt -= aq

        # Remainder at ultra-wide safety net
        if buy_bgt > 0:
            orders.append(Order(P, FAIR - 11 - skew_b, buy_bgt))
        if sell_bgt > 0:
            orders.append(Order(P, FAIR + 11 - skew_a, -sell_bgt))

        return orders

    # ============================================================
    # TOMATOES — Adaptive trend-following market maker
    # ============================================================
    def _trade_tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        LIM = LIMITS[P]
        orders: List[Order] = []

        # --- Deep VWAP microprice from all order book levels ---
        micro = self._deep_vwap(od)
        if micro is None:
            return orders

        # --- Persistent state ---
        hist = td.get("th", [])
        hist.append(micro)
        if len(hist) > 30:
            hist = hist[-30:]
        td["th"] = hist

        prev_ema = td.get("te", micro)

        # ----------------------------------------------------------
        # FAIR VALUE ENSEMBLE
        # ----------------------------------------------------------

        # Signal 1: EMA with volatility-adaptive alpha
        vol = self._rolling_vol(hist)
        alpha = min(0.30, max(0.08, T_EMA_BASE_ALPHA + vol * 0.008))
        ema = alpha * micro + (1.0 - alpha) * prev_ema
        td["te"] = ema

        # Signal 2: Exponentially weighted linear regression
        lr_fair = micro
        slope = 0.0
        n_hist = len(hist)
        if n_hist >= 4:
            window = hist[-min(T_LR_WINDOW, n_hist):]
            lr_fair, slope = self._wlinreg(window)

        # Signal 3: Order book imbalance (short-term directional bias)
        obi = self._obi(od)

        # Blend — weights shift as history grows
        if n_hist >= 8:
            fair = 0.40 * lr_fair + 0.35 * ema + 0.25 * micro
        elif n_hist >= 4:
            fair = 0.30 * lr_fair + 0.30 * ema + 0.40 * micro
        else:
            fair = micro

        # OBI micro-adjustment (predicts next-tick direction)
        fair += obi * 1.2
        fair = round(fair)

        # ----------------------------------------------------------
        # TREND SHIFT  (higher cap than 45811's puny +/-1)
        # ----------------------------------------------------------
        trend_shift = 0
        if abs(slope) > 0.05:
            trend_shift = int(round(slope * 2.5))
            trend_shift = max(-3, min(3, trend_shift))

        # ----------------------------------------------------------
        # ADAPTIVE SPREAD  (wider when volatile, tighter when calm)
        # ----------------------------------------------------------
        vol_adj = int(round(vol * 0.3))
        spread = max(2, min(8, T_BASE_SPREAD + vol_adj))

        # ----------------------------------------------------------
        # POSITION BUDGETS
        # ----------------------------------------------------------
        buy_bgt = LIM - pos
        sell_bgt = LIM + pos
        util = abs(pos) / LIM if LIM > 0 else 0.0

        # ----------------------------------------------------------
        # PHASE 1: AGGRESSIVE TAKE
        # ----------------------------------------------------------
        # Tighter edge when neutral (capture more), wider when loaded (protect)
        take_edge = 1 if util < 0.50 else 2

        for price in sorted(od.sell_orders.keys()):
            if price <= fair - take_edge and buy_bgt > 0:
                # Stop buying when dangerously long
                if pos >= int(LIM * 0.92):
                    break
                qty = min(-od.sell_orders[price], buy_bgt)
                if qty > 0:
                    orders.append(Order(P, price, qty))
                    buy_bgt -= qty
                    pos += qty
            else:
                break

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair + take_edge and sell_bgt > 0:
                if pos <= -int(LIM * 0.92):
                    break
                qty = min(od.buy_orders[price], sell_bgt)
                if qty > 0:
                    orders.append(Order(P, price, -qty))
                    sell_bgt -= qty
                    pos -= qty
            else:
                break

        # ----------------------------------------------------------
        # PHASE 2: EMERGENCY INVENTORY DUMP
        # ----------------------------------------------------------
        if util > 0.82:
            if pos > 0 and sell_bgt > 0:
                dump = min(sell_bgt, pos - int(LIM * 0.35))
                if dump > 0:
                    # Sell aggressively — accept 1 tick loss to free capacity
                    orders.append(Order(P, fair - 1, -dump))
                    sell_bgt -= dump
                    pos -= dump
            elif pos < 0 and buy_bgt > 0:
                dump = min(buy_bgt, abs(pos) - int(LIM * 0.35))
                if dump > 0:
                    orders.append(Order(P, fair + 1, dump))
                    buy_bgt -= dump
                    pos += dump

        # ----------------------------------------------------------
        # PHASE 3: MULTI-LAYER PASSIVE QUOTING
        # ----------------------------------------------------------
        # Asymmetric skew — stronger on the side that reduces position
        if pos > 0:
            skew_b = round(pos * 0.10)
            skew_a = round(pos * 0.28)
        elif pos < 0:
            skew_b = round(pos * 0.28)  # pos is negative → pulls bid up
            skew_a = round(pos * 0.10)
        else:
            skew_b = 0
            skew_a = 0

        # Three layers with trend awareness
        layers = [
            (spread,     0.35),   # tight: captures momentum fills
            (spread + 3, 0.40),   # medium: balanced edge & volume
            (spread + 6, 0.25),   # wide: high profit safety net
        ]

        for offset, frac in layers:
            bp = fair - offset - skew_b + trend_shift
            ap = fair + offset - skew_a + trend_shift

            bq = max(1, round(buy_bgt * frac))
            aq = max(1, round(sell_bgt * frac))
            bq = min(bq, buy_bgt)
            aq = min(aq, sell_bgt)

            if bq > 0 and buy_bgt > 0:
                orders.append(Order(P, bp, bq))
                buy_bgt -= bq
            if aq > 0 and sell_bgt > 0:
                orders.append(Order(P, ap, -aq))
                sell_bgt -= aq

        # Remainder at ultra-wide level
        if buy_bgt > 0:
            orders.append(Order(P, fair - spread - 9 - skew_b + trend_shift,
                                buy_bgt))
        if sell_bgt > 0:
            orders.append(Order(P, fair + spread + 9 - skew_a + trend_shift,
                                -sell_bgt))

        return orders

    # ============================================================
    # UTILITY METHODS
    # ============================================================

    @staticmethod
    def _deep_vwap(od: OrderDepth):
        """Volume-weighted microprice using ALL order book levels.
        Skews toward the side with less volume (where information lives).
        """
        if not od.buy_orders or not od.sell_orders:
            return None

        bid_wsum = sum(p * v for p, v in od.buy_orders.items())
        bid_vol = sum(od.buy_orders.values())

        ask_wsum = sum(p * abs(v) for p, v in od.sell_orders.items())
        ask_vol = sum(abs(v) for v in od.sell_orders.values())

        if bid_vol <= 0 or ask_vol <= 0:
            if bid_vol > 0:
                return bid_wsum / bid_vol
            if ask_vol > 0:
                return ask_wsum / ask_vol
            return None

        bid_vwap = bid_wsum / bid_vol
        ask_vwap = ask_wsum / ask_vol

        # Microprice: weight each side by OPPOSITE side's volume
        return (ask_vol * bid_vwap + bid_vol * ask_vwap) / (bid_vol + ask_vol)

    @staticmethod
    def _wlinreg(prices: list):
        """Exponentially weighted linear regression.
        Returns (extrapolated_fair, slope).
        Recent data points get exponentially more weight.
        """
        n = len(prices)
        if n < 2:
            return prices[-1], 0.0

        w = [T_DECAY ** (n - 1 - i) for i in range(n)]
        ws = sum(w)

        wmx = sum(wi * i for wi, i in zip(w, range(n))) / ws
        wmy = sum(wi * p for wi, p in zip(w, prices)) / ws

        wcov = sum(wi * (i - wmx) * (p - wmy)
                   for wi, i, p in zip(w, range(n), prices))
        wvar = sum(wi * (i - wmx) ** 2 for wi, i in zip(w, range(n)))

        if wvar < 1e-10:
            return prices[-1], 0.0

        b = wcov / wvar
        a = wmy - b * wmx
        return a + b * n, b  # extrapolate 1 step ahead

    @staticmethod
    def _obi(od: OrderDepth) -> float:
        """Order book imbalance: +1 = strong bids, -1 = strong asks.
        Predicts short-term price direction.
        """
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        total = bv + av
        return (bv - av) / total if total > 0 else 0.0

    @staticmethod
    def _rolling_vol(prices: list) -> float:
        """Rolling standard deviation of recent price changes."""
        if len(prices) < 3:
            return 3.0  # conservative default
        start = max(1, len(prices) - 15)
        changes = [prices[i] - prices[i - 1] for i in range(start, len(prices))]
        if not changes:
            return 3.0
        n = len(changes)
        m = sum(changes) / n
        v = sum((c - m) ** 2 for c in changes) / n
        return math.sqrt(v) if v > 0 else 0.5
