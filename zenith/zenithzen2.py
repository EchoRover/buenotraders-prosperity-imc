"""
IMC Prosperity 4 — Final Optimized Algorithm v3
=================================================
Baseline: 1,722 PnL on real sim. Target: significant improvement.

CRITICAL FIXES discovered via grid search on CSV data:
  1. EMERALDS: inv_skew was pushing quotes off bot trade levels (9992/10008).
     FIX: mm_half=7, inv_factor=0 → +17% on EMERALDS alone.
  2. TOMATOES: mm_half too tight (5→6), inv_skew on spread was wasteful.
     FIX: mm_half=6, light fv_skew=1, no dynamic spread → +10% on TOMATOES.

Strategy architecture:
  EMERALDS: Pure market making at FV=10000 ± 7. No inventory skew.
            All bot trades at 9992/10008 cross our 9993/10007 → max profit/fill.
  TOMATOES: Big-volume FV estimator + EMA blend + regime-aware taking.
            Light FV inventory adjustment. Slope detection for regime info.

Backtest (10K iters, both days): 30,906 (+13% vs v1's 27,351)
Allowed imports: pandas, numpy, statistics, math, typing, jsonpickle
"""

from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import jsonpickle
import math
import numpy as np


# ═════════════════════════════════════════════════════════════════════════════
# POSITION LIMITS
# ═════════════════════════════════════════════════════════════════════════════
LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# ═════════════════════════════════════════════════════════════════════════════
# EMERALDS: Stationary at FV=10000
# Bot quotes: bid@9992 / ask@10008 (98%+ of time)
# Bot trades happen at 9992 and 10008 → cross our quotes at 9993/10007
# KEY INSIGHT: NO inventory skew — it pushes quotes off bot levels
# ═════════════════════════════════════════════════════════════════════════════
EM_FV = 10000
EM_MM_HALF = 7  # widest safe: 9993 bid / 10007 ask

# ═════════════════════════════════════════════════════════════════════════════
# TOMATOES: Trending, lag-1 AC≈-0.42
# Grid-optimized: take=3, mm=6, fv_skew=1.0
# L2 big-volume mid is best FV estimator
# ═════════════════════════════════════════════════════════════════════════════
TOM_TAKE = 3          # take orders ≥3 ticks from FV
TOM_MM_HALF = 6       # MM at FV±6 (wider = more profit per fill)
TOM_EMA_ALPHA = 0.30  # EMA blend weight
TOM_FV_SKEW = 1.0     # light FV shift per unit of inv_ratio
TOM_SLOPE_WIN = 50    # slope lookback window


class Trader:
    def __init__(self):
        pass

    def run(self, state: TradingState):
        """
        Main entry point. Called each iteration with TradingState.
        Returns: (Dict[str, List[Order]], int, str)
        """
        result: Dict[str, List[Order]] = {}
        conversions = 0

        # Restore persistent state
        sd = {}
        if state.traderData and state.traderData != "":
            try:
                sd = jsonpickle.decode(state.traderData)
            except Exception:
                sd = {}

        for product in state.order_depths:
            if product == "EMERALDS":
                result[product] = self._emeralds(state, product, sd)
            elif product == "TOMATOES":
                result[product] = self._tomatoes(state, product, sd)
            else:
                result[product] = self._generic(state, product, sd)

        return result, conversions, jsonpickle.encode(sd)

    # ═════════════════════════════════════════════════════════════════════════
    # EMERALDS — Pure Stationary Market Maker
    # ═════════════════════════════════════════════════════════════════════════
    # Key finding: inventory skew HURTS because it pushes quotes off the
    # bot trade levels (9992/10008). With mm_half=7 and NO skew:
    #   bid=9993 → 9992 <= 9993 ✓ (bots sell to us)
    #   ask=10007 → 10008 >= 10007 ✓ (bots buy from us)
    # Every bot trade fills us at 7 ticks profit. ~200 trades/10K iters.
    # ═════════════════════════════════════════════════════════════════════════
    def _emeralds(self, state: TradingState, product: str,
                  sd: dict) -> List[Order]:
        orders: List[Order] = []
        od: OrderDepth = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = LIMITS.get(product, 50)
        fv = EM_FV

        # ── Take any rare mispricing (when mid shifts to 10004/9996) ──
        if od.sell_orders:
            for ap in sorted(od.sell_orders.keys()):
                if ap < fv and (limit - pos) > 0:
                    vol = abs(od.sell_orders[ap])
                    qty = min(vol, limit - pos)
                    if qty > 0:
                        orders.append(Order(product, ap, qty))
                        pos += qty

        if od.buy_orders:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp > fv and (limit + pos) > 0:
                    vol = od.buy_orders[bp]
                    qty = min(vol, limit + pos)
                    if qty > 0:
                        orders.append(Order(product, bp, -qty))
                        pos -= qty

        # ── Market making: fixed spread, NO inventory skew ──
        # The bot buys/sells are ~balanced so position stays near zero naturally
        buy_cap = limit - pos
        sell_cap = limit + pos

        bid = fv - EM_MM_HALF  # 9993
        ask = fv + EM_MM_HALF  # 10007

        if buy_cap > 0:
            orders.append(Order(product, bid, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask, -sell_cap))

        return orders

    # ═════════════════════════════════════════════════════════════════════════
    # TOMATOES — Adaptive Market Maker with Regime Awareness
    # ═════════════════════════════════════════════════════════════════════════
    # FV estimation: big-volume mid (L2) + EMA(α=0.30) blend
    # Regime detection: rolling slope via np.polyfit (50-tick window)
    #   TREND: |slope/vol| > 0.15 → report regime, mild FV adjustment
    #   RANGE: default parameters
    # Inventory: light FV skew (1 tick per unit of inv_ratio)
    # No dynamic spread widening (it reduces fills without benefit)
    # ═════════════════════════════════════════════════════════════════════════
    def _tomatoes(self, state: TradingState, product: str,
                  sd: dict) -> List[Order]:
        orders: List[Order] = []
        od: OrderDepth = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = LIMITS.get(product, 50)

        buy_prices = sorted(od.buy_orders.keys(), reverse=True)
        sell_prices = sorted(od.sell_orders.keys())
        if not buy_prices or not sell_prices:
            return orders

        # ── Fair value from big-volume levels ──
        big_bid = max(od.buy_orders, key=lambda k: od.buy_orders[k])
        big_ask = max(od.sell_orders, key=lambda k: abs(od.sell_orders[k]))
        book_fv = (big_bid + big_ask) / 2.0

        # EMA tracking
        ema_key = f"{product}_ema"
        if ema_key in sd:
            ema = TOM_EMA_ALPHA * book_fv + (1 - TOM_EMA_ALPHA) * sd[ema_key]
        else:
            ema = book_fv
        sd[ema_key] = ema

        # Blended fair value
        fv = 0.7 * book_fv + 0.3 * ema

        # ── Price history for regime detection ──
        hist_key = f"{product}_hist"
        if hist_key not in sd:
            sd[hist_key] = []
        sd[hist_key].append(fv)
        if len(sd[hist_key]) > 200:
            sd[hist_key] = sd[hist_key][-200:]

        # ── Regime detection (slope + vol) ──
        slope = 0.0
        regime = "RANGE"
        hist = sd[hist_key]

        if len(hist) >= TOM_SLOPE_WIN:
            y = np.array(hist[-TOM_SLOPE_WIN:])
            x = np.arange(len(y))
            slope, _ = np.polyfit(x, y, 1)

            # Normalize by recent volatility
            if len(hist) >= 21:
                rets = np.diff(hist[-21:])
                vol = max(np.std(rets), 0.01)
                if abs(slope) / vol > 0.15:
                    regime = "TREND"

        # ── Inventory-adjusted fair value ──
        # Light skew: 1 tick per unit of inventory ratio
        inv_ratio = pos / limit if limit > 0 else 0
        fv_adj = fv - inv_ratio * TOM_FV_SKEW

        # ── PHASE 1: Take mispriced levels ──
        take_w = TOM_TAKE

        # Regime-aware: in strong trend opposing our position, tighten take
        if regime == "TREND" and abs(pos) > 40:
            if (slope > 0 and pos < 0) or (slope < 0 and pos > 0):
                take_w = max(1, take_w - 1)  # more willing to reduce bad position

        for ap in sorted(od.sell_orders.keys()):
            if ap <= fv_adj - take_w and (limit - pos) > 0:
                vol = abs(od.sell_orders[ap])
                qty = min(vol, limit - pos)
                if qty > 0:
                    orders.append(Order(product, ap, qty))
                    pos += qty

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp >= fv_adj + take_w and (limit + pos) > 0:
                vol = od.buy_orders[bp]
                qty = min(vol, limit + pos)
                if qty > 0:
                    orders.append(Order(product, bp, -qty))
                    pos -= qty

        # ── PHASE 2: Market making ──
        buy_cap = limit - pos
        sell_cap = limit + pos

        mm_bid = int(math.floor(fv_adj - TOM_MM_HALF))
        mm_ask = int(math.ceil(fv_adj + TOM_MM_HALF))

        if mm_bid >= mm_ask:
            mm_bid = int(math.floor(fv_adj)) - 1
            mm_ask = int(math.ceil(fv_adj)) + 1

        if buy_cap > 0:
            orders.append(Order(product, mm_bid, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, mm_ask, -sell_cap))

        return orders

    # ═════════════════════════════════════════════════════════════════════════
    # GENERIC — Fallback for future rounds
    # ═════════════════════════════════════════════════════════════════════════
    def _generic(self, state: TradingState, product: str,
                 sd: dict) -> List[Order]:
        orders: List[Order] = []
        od: OrderDepth = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = LIMITS.get(product, 50)

        bp = sorted(od.buy_orders.keys(), reverse=True)
        sp = sorted(od.sell_orders.keys())
        if not bp or not sp:
            return orders

        mid = (bp[0] + sp[0]) / 2
        ema_key = f"{product}_ema"
        if ema_key in sd:
            ema = 0.2 * mid + 0.8 * sd[ema_key]
        else:
            ema = mid
        sd[ema_key] = ema

        fv = ema

        for ap in sorted(od.sell_orders.keys()):
            if ap < fv - 1 and (limit - pos) > 0:
                vol = abs(od.sell_orders[ap])
                qty = min(vol, limit - pos)
                orders.append(Order(product, ap, qty))
                pos += qty

        for b in sorted(od.buy_orders.keys(), reverse=True):
            if b > fv + 1 and (limit + pos) > 0:
                vol = od.buy_orders[b]
                qty = min(vol, limit + pos)
                orders.append(Order(product, b, -qty))
                pos -= qty

        bc = limit - pos
        sc = limit + pos
        if bc > 0:
            orders.append(Order(product, int(math.floor(fv - 3)), bc))
        if sc > 0:
            orders.append(Order(product, int(math.ceil(fv + 3)), -sc))

        return orders
