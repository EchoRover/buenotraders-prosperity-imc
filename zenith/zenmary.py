"""
HYBRID CHAMPION v3 — Data-Driven Optimization
================================================
Baseline: e1_fake1 = 2,787 (E:1050, T:1737)  |  ultrazen = 2,236 (E:1050, T:1186)
Target: 3,000+ PnL

Analysis Summary (from official sim log comparison):
  - EMERALDS: Both algos produce IDENTICAL PnL (1050). Solved product.
  - TOMATOES gap (551.4) breakdown:
      86% from position limit (70 vs 50) → use limit=75
      14% from tighter spread quoting → use e1's dynamic spread
  - Ultrazen 80k-94k dip: -488 drawdown vs e1's -287
      → Add rolling drawdown circuit breaker

Strategy:
  EMERALDS: e1_fake1 exact approach (proven 1050)
  TOMATOES: e1_fake1 FV (fat bid/ask + beta reversion) + 2-layer quoting
            + adaptive risk scaling + circuit breaker
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
from typing import Dict, List

# ── Position Limits ────────────────────────────────────────────────
LIMITS = {"EMERALDS": 80, "TOMATOES": 75}

# ── EMERALDS Constants (unchanged from e1_fake1 proven config) ─────
E_FAIR = 10000

# ── TOMATOES Constants ─────────────────────────────────────────────
# FV estimation: fat bid/ask midpoint + mean reversion (from e1_fake1)
T_ADVOL = 16          # minimum volume for "fat level" detection
T_BETA = -0.229       # mean reversion coefficient (proven in Rust sweep)
T_EDGE = 1            # take edge (buy at fair-1 or better)

# Quoting: hybrid of e1's dynamic spread + ultrazen's 2-layer
T_L1_PCT = 0.65       # 65% of budget at L1, 35% at L2
T_L2_OFFSET = 1       # L2 is 1 tick behind L1

# Risk management: circuit breaker for sustained drawdowns
T_DD_WINDOW = 15      # rolling window for drawdown detection (ticks)
T_DD_THRESH = 8       # if FV drops > this over window, reduce size
T_DD_SCALE = 0.60     # scale position limit to 60% during drawdown
T_SOFT = 60           # soft limit for quote skewing


class Trader:
    def run(self, state: TradingState):
        td = {}
        if state.traderData:
            try:
                td = json.loads(state.traderData)
            except:
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

    # ═══════════════════════════════════════════════════════════════
    # EMERALDS — Exact e1_fake1 logic (proven 1050 PnL)
    # ═══════════════════════════════════════════════════════════════
    def _emeralds(self, od, pos):
        FAIR = E_FAIR
        P = "EMERALDS"
        o = []
        bb = LIMITS[P] - pos   # buy budget
        sb = LIMITS[P] + pos   # sell budget

        # Phase 1: TAKE — hit mispriced orders
        for p in sorted(od.sell_orders.keys()):
            if p <= FAIR - 1 and bb > 0:
                q = min(-od.sell_orders[p], bb)
                o.append(Order(P, p, q))
                bb -= q
                pos += q
            else:
                break

        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= FAIR + 1 and sb > 0:
                q = min(od.buy_orders[p], sb)
                o.append(Order(P, p, -q))
                sb -= q
                pos -= q
            else:
                break

        # Phase 2: CLEAR — reduce inventory at fair
        if pos > 0 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR and sb > 0 and pos > 0:
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0:
                        o.append(Order(P, p, -q))
                        sb -= q
                        pos -= q
                else:
                    break

        if pos < 0 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR and bb > 0 and pos < 0:
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0:
                        o.append(Order(P, p, q))
                        bb -= q
                        pos += q
                else:
                    break

        # Phase 2b: AGGRESSIVE CLEAR — big positions at FAIR±1
        if pos > 20 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR - 1 and sb > 0 and pos > 5:
                    q = min(od.buy_orders[p], sb, pos - 5)
                    if q > 0:
                        o.append(Order(P, p, -q))
                        sb -= q
                        pos -= q
                else:
                    break

        if pos < -20 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR + 1 and bb > 0 and pos < -5:
                    q = min(-od.sell_orders[p], bb, -pos - 5)
                    if q > 0:
                        o.append(Order(P, p, q))
                        bb -= q
                        pos += q
                else:
                    break

        # Phase 3: MAKE — post resting orders
        bp = FAIR - 4
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < FAIR - 1:
                bp = p + 1
                break
        bp = min(bp, FAIR - 1)

        ap = FAIR + 4
        for p in sorted(od.sell_orders.keys()):
            if p > FAIR + 1:
                ap = p - 1
                break
        ap = max(ap, FAIR + 1)

        if pos > 25:
            bp -= 1
            ap = max(ap - 1, FAIR + 1)
        elif pos < -25:
            ap += 1
            bp = min(bp + 1, FAIR - 1)

        bp = min(bp, FAIR - 1)
        ap = max(ap, FAIR + 1)

        if bb > 0:
            l1 = max(1, int(bb * 0.65))
            o.append(Order(P, bp, l1))
            if bb - l1 > 0:
                o.append(Order(P, bp - 1, bb - l1))

        if sb > 0:
            l1 = max(1, int(sb * 0.65))
            o.append(Order(P, ap, -l1))
            if sb - l1 > 0:
                o.append(Order(P, ap + 1, -(sb - l1)))

        return o

    # ═══════════════════════════════════════════════════════════════
    # TOMATOES — Enhanced e1_fake1 core + circuit breaker + 2-layer
    # ═══════════════════════════════════════════════════════════════
    def _tomatoes(self, od, pos, td):
        P = "TOMATOES"
        o = []
        LIM = LIMITS[P]

        # ── Step 1: Fair Value via fat bid/ask + beta reversion ──
        fb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= T_ADVOL:
                fb = p
                break
        fa = None
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= T_ADVOL:
                fa = p
                break

        # Fallback: best bid/ask if no fat level found
        if fb is None:
            fb = max(od.buy_orders.keys()) if od.buy_orders else None
        if fa is None:
            fa = min(od.sell_orders.keys()) if od.sell_orders else None
        if fb is None or fa is None:
            return o

        fm = (fb + fa) / 2.0

        # Beta mean reversion
        pm = td.get("pm", fm)
        td["pm"] = fm
        if pm != 0:
            lr = (fm - pm) / pm
            pr = lr * T_BETA
            fair = round(fm * (1 + pr))
        else:
            fair = round(fm)

        # ── Step 2: Circuit Breaker — detect sustained drawdown ──
        fv_hist = td.get("fh", [])
        fv_hist.append(fm)
        if len(fv_hist) > T_DD_WINDOW:
            fv_hist = fv_hist[-T_DD_WINDOW:]
        td["fh"] = fv_hist

        in_drawdown = False
        if len(fv_hist) >= T_DD_WINDOW:
            peak = max(fv_hist[:T_DD_WINDOW // 2])  # peak in first half
            current = fv_hist[-1]
            if peak - current > T_DD_THRESH:
                in_drawdown = True

        # Effective limit (reduce during drawdown)
        eff_lim = int(LIM * T_DD_SCALE) if in_drawdown else LIM

        bb = eff_lim - pos   # buy budget
        sb = eff_lim + pos   # sell budget

        # Clamp to hard limit (never exceed LIMITS)
        bb = min(bb, LIMITS[P] - pos)
        sb = min(sb, LIMITS[P] + pos)

        # ── Step 3: TAKE — aggressive fills ──
        for p in sorted(od.sell_orders.keys()):
            if p <= fair - T_EDGE and bb > 0:
                q = min(-od.sell_orders[p], bb)
                o.append(Order(P, p, q))
                bb -= q
                pos += q
            else:
                break

        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= fair + T_EDGE and sb > 0:
                q = min(od.buy_orders[p], sb)
                o.append(Order(P, p, -q))
                sb -= q
                pos -= q
            else:
                break

        # ── Step 4: CLEAR — reduce inventory at fair ──
        if pos > 0 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= fair and sb > 0 and pos > 0:
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0:
                        o.append(Order(P, p, -q))
                        sb -= q
                        pos -= q
                else:
                    break

        if pos < 0 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= fair and bb > 0 and pos < 0:
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0:
                        o.append(Order(P, p, q))
                        bb -= q
                        pos += q
                else:
                    break

        # ── Step 5: MAKE — post resting orders ──
        # Dynamic spread: penny ahead of best resting level (e1 approach)
        bbb = None
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - 1:
                bbb = p
                break
        baa = None
        for p in sorted(od.sell_orders.keys()):
            if p > fair + 1:
                baa = p
                break

        if bbb is not None:
            bidp = bbb + 1
        else:
            bidp = fair - 2
        bidp = min(bidp, fair - 1)

        if baa is not None:
            askp = baa - 1
        else:
            askp = fair + 2
        askp = max(askp, fair + 1)

        # Soft limit skewing
        if pos > T_SOFT:
            askp = max(askp - 1, fair + 1)
        elif pos < -T_SOFT:
            bidp = min(bidp + 1, fair - 1)

        # Hard position cap
        if pos >= LIM:
            bb = 0
        if pos <= -LIM:
            sb = 0

        # 2-layer quoting (from ultrazen — better fill distribution)
        if bb > 0:
            l1 = max(1, int(bb * T_L1_PCT))
            l2 = bb - l1
            o.append(Order(P, bidp, l1))
            if l2 > 0:
                o.append(Order(P, bidp - T_L2_OFFSET, l2))

        if sb > 0:
            l1 = max(1, int(sb * T_L1_PCT))
            l2 = sb - l1
            o.append(Order(P, askp, -l1))
            if l2 > 0:
                o.append(Order(P, askp + T_L2_OFFSET, -(sb - l1)))

        return o