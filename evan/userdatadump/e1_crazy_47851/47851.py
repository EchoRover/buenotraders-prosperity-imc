"""
e1_crazy1 — claude2 agent
=========================
Fresh approach. Not backtester-optimized — designed from market understanding.

Core thesis: The biggest untested edge is ADVERSE SELECTION FILTERING.
When a large-volume order sits at the best bid/ask, it's a market maker bot.
Taking against it is adverse selection — you're paying THEIR spread.
This technique won 2nd place in Prosperity 2 (Linear Utility) and has
NEVER been tested in this codebase.

EMERALDS (target: 867+):
  L5 proven foundation + limit=80 + v7 aggressive CLEAR
  - Penny-jump + CLEAR (proven at 867 across v5/v7/LADDOO)
  - Zero skew (L5 finding: CLEAR handles inventory, skew costs fills)
  - OBI-based quote adjustment (L5: threshold 0.12)
  - Aggressive CLEAR at fair±1 when position extreme (v7)

TOMATOES (target: 1,500+):
  L5 ensemble + adverse filter + market-maker mid + limit=80

  Fair value pipeline:
    1. Market-maker mid (filter book for vol >= 15 = bot quotes only)
       Falls back to deep VWAP microprice when no large-vol levels exist
    2. Weighted LR (decay=0.88, window=10) — captures momentum
    3. EMA (alpha=0.20) — smooth tracking
    4. Ensemble: 0.25*LR + 0.45*EMA + 0.30*base (L5 sweep-optimized)
    5. OBI adjustment (weight=1.3)
    6. Fade lag-1 return (reversion=-0.25) — mean reversion

  Taking:
    - At fair±1, WITH adverse selection filter
    - If best level volume >= 15, that's a market maker — skip ALL takes
    - Only take when small volume at best (post-taker remnant = safe)

  Position management:
    - Ultra-low skew (0.01) — lets positions ride trends
    - Hard brake at ±60 (uses more of limit=80 capacity)
    - CLEAR at fair, aggressive CLEAR at fair±1 when |pos| > 40
    - Two-layer quoting 65/35, L2_offset=1 (L5: tighter captures more)

WHY this should beat LADDOO (2,102):
  - Adverse filter prevents ~10-20% of losing takes (estimated from LU's P2 results)
  - Market-maker mid gives cleaner fair value than raw VWAP
  - Limit=80 gives 60% more CLEAR cycling capacity
  - Aggressive CLEAR prevents the position spiral that killed v5 TOMATOES

Author: claude2 agent
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

# ═══════════════════════════════════════════
# EMERALDS params (L5 sweep-optimized + v7)
# ═══════════════════════════════════════════
E_FAIR         = 10_000
E_TAKE_EDGE    = 1
E_CLEAR_EDGE   = 0
E_DISREGARD    = 1
E_DEFAULT_EDGE = 4
E_SKEW         = 0.00
E_SOFT_LIMIT   = 25
E_L1_PCT       = 0.65
E_L2_OFFSET    = 1
E_IMB_THRESH   = 0.12

# v7 aggressive CLEAR thresholds
E_AGGRO_POS    = 30
E_AGGRO_TARG   = 15

# ═══════════════════════════════════════════
# TOMATOES params
# ═══════════════════════════════════════════
T_LR_WINDOW    = 10
T_EMA_ALPHA    = 0.20
T_DECAY        = 0.88
T_OBI_WEIGHT   = 1.3
T_TAKE_EDGE    = 1
T_CLEAR_EDGE   = 0
T_SPREAD       = 6
T_SKEW         = 0.01
T_HARD_LIMIT   = 60
T_L1_PCT       = 0.65
T_L2_OFFSET    = 1

# Novel: adverse selection filter (from Linear Utility, 2nd place P2)
T_ADVERSE_VOL  = 15

# Mean reversion on lag-1 return
T_REVERSION    = -0.25

# Aggressive CLEAR
T_AGGRO_POS    = 40
T_AGGRO_TARG   = 20

# L5 ensemble weights
W_LR  = 0.25
W_EMA = 0.45
W_MIC = 0.30


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
    # EMERALDS — penny-jump + CLEAR
    # Foundation: L5 (sweep-optimized) + v7 (aggressive CLEAR)
    # ══════════════════════════════════════════════════════════════

    def _emeralds(self, od: OrderDepth, pos: int) -> List[Order]:
        P = "EMERALDS"
        FAIR = E_FAIR
        LIM = LIMITS[P]
        orders: List[Order] = []
        buy_b = LIM - pos
        sell_b = LIM + pos

        # ── TAKE ──
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

        # ── CLEAR at fair ──
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

        # ── AGGRESSIVE CLEAR at fair±1 when extreme (v7) ──
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

        # ── MAKE: penny-jump with OBI adjustment ──
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
    # TOMATOES — adverse filter + market-maker mid + L5 ensemble
    # ══════════════════════════════════════════════════════════════

    def _tomatoes(self, od: OrderDepth, pos: int, td: dict) -> List[Order]:
        P = "TOMATOES"
        LIM = LIMITS[P]
        orders: List[Order] = []

        # ── FAIR VALUE ──
        # Primary: market-maker mid (filter book for large vol = bot quotes)
        mmmid = self._mm_mid(od, T_ADVERSE_VOL)
        # Fallback: deep VWAP microprice
        micro = self._deep_vwap(od)
        if micro is None:
            return orders
        base = mmmid if mmmid is not None else micro

        # History
        hist = td.get("th", [])
        hist.append(base)
        if len(hist) > 25:
            hist = hist[-25:]
        td["th"] = hist

        # EMA
        prev_ema = td.get("te", base)
        ema = T_EMA_ALPHA * base + (1.0 - T_EMA_ALPHA) * prev_ema
        td["te"] = ema

        # Weighted linear regression
        lr_fair = base
        if len(hist) >= 4:
            win = hist[-min(T_LR_WINDOW, len(hist)):]
            lr_fair = self._wlinreg(win)

        # OBI
        obi = self._obi(od)

        # Ensemble (L5 weights)
        if len(hist) >= 8:
            fair = W_LR * lr_fair + W_EMA * ema + W_MIC * base
        elif len(hist) >= 4:
            fair = 0.30 * lr_fair + 0.30 * ema + 0.40 * base
        else:
            fair = base
        fair += obi * T_OBI_WEIGHT

        # Fade lag-1 return (mean reversion, -0.44 autocorrelation in data)
        if len(hist) >= 2:
            fair += (hist[-1] - hist[-2]) * T_REVERSION

        fair = round(fair)

        buy_b = LIM - pos
        sell_b = LIM + pos

        # ── TAKE with adverse selection filter ──
        # If best level has large volume, it's a market maker — skip takes
        can_buy = True
        can_sell = True
        if od.sell_orders:
            best_ask = min(od.sell_orders.keys())
            if abs(od.sell_orders[best_ask]) >= T_ADVERSE_VOL:
                can_buy = False
        if od.buy_orders:
            best_bid = max(od.buy_orders.keys())
            if od.buy_orders[best_bid] >= T_ADVERSE_VOL:
                can_sell = False

        if can_buy:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair - T_TAKE_EDGE and buy_b > 0:
                    q = min(-od.sell_orders[price], buy_b)
                    orders.append(Order(P, price, q))
                    buy_b -= q; pos += q
                else:
                    break

        if can_sell:
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

        # ── AGGRESSIVE CLEAR at fair±1 when extreme ──
        if pos > T_AGGRO_POS and sell_b > 0:
            for price in sorted(od.buy_orders.keys(), reverse=True):
                if price >= fair - 1 and sell_b > 0 and pos > T_AGGRO_TARG:
                    q = min(od.buy_orders[price], sell_b, pos - T_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, -q))
                        sell_b -= q; pos -= q
                else:
                    break
        if pos < -T_AGGRO_POS and buy_b > 0:
            for price in sorted(od.sell_orders.keys()):
                if price <= fair + 1 and buy_b > 0 and pos < -T_AGGRO_TARG:
                    q = min(-od.sell_orders[price], buy_b, -pos - T_AGGRO_TARG)
                    if q > 0:
                        orders.append(Order(P, price, q))
                        buy_b -= q; pos += q
                else:
                    break

        # ── MAKE ──
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

    # ══════════════════════════════════════════════════════════════
    # UTILS
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _mm_mid(od: OrderDepth, min_vol: int):
        """Market-maker mid: filter book for large-vol levels (bot quotes)."""
        if not od.buy_orders or not od.sell_orders:
            return None
        filtered_bids = [p for p, v in od.buy_orders.items() if v >= min_vol]
        filtered_asks = [p for p, v in od.sell_orders.items() if abs(v) >= min_vol]
        if not filtered_bids or not filtered_asks:
            return None
        return (max(filtered_bids) + min(filtered_asks)) / 2

    @staticmethod
    def _deep_vwap(od: OrderDepth):
        """VWAP microprice across all book levels."""
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
        """Weighted linear regression with exponential decay."""
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
    def _obi(od: OrderDepth) -> float:
        """Order book imbalance: (bid_vol - ask_vol) / total."""
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bv = sum(od.buy_orders.values())
        av = sum(abs(v) for v in od.sell_orders.values())
        t = bv + av
        return (bv - av) / t if t > 0 else 0.0