"""
PROSPERITY 4 — ULTIMATE MODULAR TRADING ALGORITHM
===================================================
Tutorial baseline: 2,787 PnL (E:1050, T:1737) — matches e1_fake1 proven ceiling
Architecture: Ready for Round 1+ with per-product config, bot fingerprinting,
              basket arbitrage, mean-reversion, and regime detection.

Modules:
  1. STABLE MM    — For fixed-FV products (EMERALDS = 10000)
  2. WALL-MID MM  — For slow-moving products (TOMATOES, Kelp-like)
  3. MEAN REVERT  — For volatile products (Squid Ink-like)
  4. BASKET ARB   — For ETF/composite products (Picnic Basket-like)
  5. BOT TRACKER  — Fingerprints trader IDs from market_trades
  6. REGIME ENGINE — Rolling vol detector + adaptive sizing

Based on: Frankfurt Hedgehogs (2nd P3), Linear Utility (2nd P2),
          Alpha Animals (9th P3), e1_fake1 (proven tutorial config)
"""

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:
    from prosperity4bt.datamodel import OrderDepth, TradingState, Order

import json
import math
from typing import Dict, List, Any, Optional

# ═══════════════════════════════════════════════════════════════════
# PER-PRODUCT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
# Add new products here when rounds drop. Each product gets a strategy
# type and its own parameter set.
#
# Strategy types:
#   "stable"    — fixed fair value, pure market making (EMERALDS)
#   "wallmid"   — wall-mid FV estimation + beta reversion (TOMATOES)
#   "meanrev"   — z-score mean reversion for volatile products
#   "basket"    — ETF/composite arbitrage
#   "copy"      — copy a specific bot trader (Round 5 style)

PRODUCTS = {
    "EMERALDS": {
        "strategy": "stable",
        "fair": 10000,
        "limit": 80,
        "take_edge": 1,        # take at fair ± this
        "clear_edge": 0,       # clear inventory at fair ± this
        "default_spread": 4,   # fallback quote distance from fair
        "disregard": 1,        # ignore book levels within this of fair
        "soft_limit": 25,      # start skewing quotes at this position
        "aggro_pos": 20,       # aggressive clear threshold
        "aggro_target": 5,     # aggressive clear target position
        "l1_pct": 0.65,        # fraction of budget at L1
    },
    "TOMATOES": {
        "strategy": "wallmid",
        "limit": 70,
        "take_edge": 1,
        "clear_edge": 0,
        "wall_vol": 16,        # min volume to detect "wall" level
        "beta": -0.229,        # mean reversion on FV changes
        "default_spread": 4,
        "disregard": 1,
        "soft_limit": 100,     # effectively disabled (proven config)
        "l1_pct": 1.0,         # single layer (proven config)
    },
    # ── ROUND 1+ TEMPLATES (uncomment and calibrate when products appear) ──
    #
    # "KELP_LIKE": {
    #     "strategy": "wallmid",
    #     "limit": 50,
    #     "take_edge": 1,
    #     "clear_edge": 0,
    #     "wall_vol": 12,
    #     "beta": 0.0,           # no reversion for random walk
    #     "default_spread": 3,
    #     "disregard": 1,
    #     "soft_limit": 30,
    #     "l1_pct": 0.65,
    # },
    # "SQUID_LIKE": {
    #     "strategy": "meanrev",
    #     "limit": 50,
    #     "take_edge": 1,
    #     "clear_edge": 0,
    #     "ema_alpha": 0.15,
    #     "z_window": 20,        # rolling window for z-score
    #     "z_entry": 2.5,        # enter at this many sigma
    #     "z_exit": 0.5,         # exit when z drops to this
    #     "max_trade_size": 15,  # per-tick directional limit
    #     "default_spread": 3,
    #     "l1_pct": 0.65,
    # },
    # "BASKET": {
    #     "strategy": "basket",
    #     "limit": 60,
    #     "components": {"CROISSANT": 6, "JAM": 3, "DJEMBE": 1},
    #     "z_window": 50,
    #     "z_entry": 1.5,
    #     "z_exit": 0.3,
    #     "hedge": True,
    # },
}


class Trader:
    """
    Main entry point. Dispatches each product to its configured strategy.
    Maintains state across ticks via traderData JSON serialization.
    """

    def run(self, state: TradingState):
        td = {}
        if state.traderData:
            try:
                td = json.loads(state.traderData)
            except Exception:
                td = {}

        result: Dict[str, List[Order]] = {}

        # ── Bot fingerprinting (runs every tick, all products) ──
        td = self._track_bots(state, td)

        # ── Regime detection (rolling vol per product) ──
        td = self._update_regimes(state, td)

        # ── Dispatch to per-product strategy ──
        for product in state.order_depths:
            if product not in PRODUCTS:
                # Unknown product: skip (or add a default MM)
                continue

            cfg = PRODUCTS[product]
            od = state.order_depths[product]
            pos = state.position.get(product, 0)
            strat = cfg["strategy"]

            if strat == "stable":
                result[product] = self._stable_mm(product, od, pos, cfg)
            elif strat == "wallmid":
                result[product] = self._wallmid_mm(product, od, pos, cfg, td)
            elif strat == "meanrev":
                result[product] = self._meanrev(product, od, pos, cfg, td)
            elif strat == "basket":
                result[product] = self._basket_arb(
                    product, state.order_depths, state.position, cfg, td
                )
            elif strat == "copy":
                result[product] = self._copy_trade(product, od, pos, cfg, td)

        return result, 0, json.dumps(td, separators=(",", ":"))

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY 1: STABLE MARKET MAKING (EMERALDS)
    # Known fixed fair value. TAKE → CLEAR → AGGRO CLEAR → MAKE.
    # ═══════════════════════════════════════════════════════════════
    def _stable_mm(self, P, od, pos, cfg):
        FAIR = cfg["fair"]
        LIM = cfg["limit"]
        o = []
        bb = LIM - pos
        sb = LIM + pos

        # TAKE: hit anything mispriced
        for p in sorted(od.sell_orders.keys()):
            if p <= FAIR - cfg["take_edge"] and bb > 0:
                q = min(-od.sell_orders[p], bb)
                o.append(Order(P, p, q)); bb -= q; pos += q
            else:
                break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= FAIR + cfg["take_edge"] and sb > 0:
                q = min(od.buy_orders[p], sb)
                o.append(Order(P, p, -q)); sb -= q; pos -= q
            else:
                break

        # CLEAR: reduce inventory at fair
        if pos > 0 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR - cfg["clear_edge"] and sb > 0 and pos > 0:
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0:
                        o.append(Order(P, p, -q)); sb -= q; pos -= q
                else:
                    break
        if pos < 0 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR + cfg["clear_edge"] and bb > 0 and pos < 0:
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0:
                        o.append(Order(P, p, q)); bb -= q; pos += q
                else:
                    break

        # AGGRESSIVE CLEAR: large positions at FAIR±1
        ap = cfg.get("aggro_pos", 20)
        at = cfg.get("aggro_target", 5)
        if pos > ap and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= FAIR - 1 and sb > 0 and pos > at:
                    q = min(od.buy_orders[p], sb, pos - at)
                    if q > 0:
                        o.append(Order(P, p, -q)); sb -= q; pos -= q
                else:
                    break
        if pos < -ap and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= FAIR + 1 and bb > 0 and pos < -at:
                    q = min(-od.sell_orders[p], bb, -pos - at)
                    if q > 0:
                        o.append(Order(P, p, q)); bb -= q; pos += q
                else:
                    break

        # MAKE: post resting orders
        bp, ap_price = self._find_quote_prices(od, FAIR, cfg)

        sl = cfg.get("soft_limit", 25)
        if pos > sl:
            bp -= 1; ap_price = max(ap_price - 1, FAIR + 1)
        elif pos < -sl:
            ap_price += 1; bp = min(bp + 1, FAIR - 1)
        bp = min(bp, FAIR - 1)
        ap_price = max(ap_price, FAIR + 1)

        l1_pct = cfg.get("l1_pct", 0.65)
        self._post_quotes(o, P, bp, ap_price, bb, sb, l1_pct)

        return o

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY 2: WALL-MID MARKET MAKING (TOMATOES, KELP-like)
    # Detect "wall" bid/ask → compute fair → TAKE → CLEAR → MAKE.
    # ═══════════════════════════════════════════════════════════════
    def _wallmid_mm(self, P, od, pos, cfg, td):
        LIM = cfg["limit"]
        o = []

        # Step 1: Find wall mid (fat bid/ask levels)
        wall_vol = cfg.get("wall_vol", 16)
        fb = self._find_wall_bid(od, wall_vol)
        fa = self._find_wall_ask(od, wall_vol)
        if fb is None or fa is None:
            return o

        fm = (fb + fa) / 2.0

        # Step 2: Beta mean reversion adjustment
        beta = cfg.get("beta", 0.0)
        key_pm = f"{P}_pm"
        pm = td.get(key_pm, fm)
        td[key_pm] = fm

        if beta != 0 and pm != 0:
            lr = (fm - pm) / pm
            fair = round(fm * (1 + lr * beta))
        else:
            fair = round(fm)

        # Step 3: TAKE
        bb = LIM - pos
        sb = LIM + pos
        for p in sorted(od.sell_orders.keys()):
            if p <= fair - cfg["take_edge"] and bb > 0:
                q = min(-od.sell_orders[p], bb)
                o.append(Order(P, p, q)); bb -= q; pos += q
            else:
                break
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p >= fair + cfg["take_edge"] and sb > 0:
                q = min(od.buy_orders[p], sb)
                o.append(Order(P, p, -q)); sb -= q; pos -= q
            else:
                break

        # Step 4: CLEAR at fair
        if pos > 0 and sb > 0:
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= fair - cfg.get("clear_edge", 0) and sb > 0 and pos > 0:
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0:
                        o.append(Order(P, p, -q)); sb -= q; pos -= q
                else:
                    break
        if pos < 0 and bb > 0:
            for p in sorted(od.sell_orders.keys()):
                if p <= fair + cfg.get("clear_edge", 0) and bb > 0 and pos < 0:
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0:
                        o.append(Order(P, p, q)); bb -= q; pos += q
                else:
                    break

        # Step 5: MAKE — dynamic spread (penny ahead of best resting)
        bp, ap_price = self._find_quote_prices(od, fair, cfg)

        sl = cfg.get("soft_limit", 100)
        if pos > sl:
            ap_price = max(ap_price - 1, fair + 1)
        elif pos < -sl:
            bp = min(bp + 1, fair - 1)

        if pos >= LIM:
            bb = 0
        if pos <= -LIM:
            sb = 0

        l1_pct = cfg.get("l1_pct", 1.0)
        self._post_quotes(o, P, bp, ap_price, bb, sb, l1_pct)

        return o

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY 3: MEAN REVERSION (Squid Ink-like volatile products)
    # Z-score of price vs EMA. Fade spikes > z_entry sigma.
    # ═══════════════════════════════════════════════════════════════
    def _meanrev(self, P, od, pos, cfg, td):
        LIM = cfg["limit"]
        o = []
        if not od.buy_orders or not od.sell_orders:
            return o

        mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2.0

        # Update rolling stats
        key_h = f"{P}_hist"
        key_ema = f"{P}_ema"
        hist = td.get(key_h, [])
        hist.append(mid)
        window = cfg.get("z_window", 20)
        if len(hist) > window * 2:
            hist = hist[-(window * 2):]
        td[key_h] = hist

        alpha = cfg.get("ema_alpha", 0.15)
        prev_ema = td.get(key_ema, mid)
        ema = alpha * mid + (1 - alpha) * prev_ema
        td[key_ema] = ema

        # Need enough data for z-score
        if len(hist) < window:
            # Not enough data — fall back to basic MM around mid
            fair = round(mid)
            bb = LIM - pos; sb = LIM + pos
            spread = cfg.get("default_spread", 3)
            if bb > 0:
                o.append(Order(P, fair - spread, bb))
            if sb > 0:
                o.append(Order(P, fair + spread, -sb))
            return o

        # Compute z-score
        recent = hist[-window:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = math.sqrt(variance) if variance > 0 else 1.0
        z = (mid - mean) / std if std > 0.01 else 0.0

        fair = round(ema)
        z_entry = cfg.get("z_entry", 2.5)
        z_exit = cfg.get("z_exit", 0.5)
        max_size = cfg.get("max_trade_size", 15)
        bb = LIM - pos
        sb = LIM + pos

        # Directional signal: fade the spike
        if z > z_entry and sb > 0:
            # Price is high — sell
            for p in sorted(od.buy_orders.keys(), reverse=True):
                if p >= fair and sb > 0:
                    q = min(od.buy_orders[p], sb, max_size)
                    if q > 0:
                        o.append(Order(P, p, -q)); sb -= q; pos -= q
                else:
                    break
        elif z < -z_entry and bb > 0:
            # Price is low — buy
            for p in sorted(od.sell_orders.keys()):
                if p <= fair and bb > 0:
                    q = min(-od.sell_orders[p], bb, max_size)
                    if q > 0:
                        o.append(Order(P, p, q)); bb -= q; pos += q
                else:
                    break

        # Exit signal: clear when z reverts
        if abs(z) < z_exit:
            if pos > 0 and sb > 0:
                for p in sorted(od.buy_orders.keys(), reverse=True):
                    if sb > 0 and pos > 0:
                        q = min(od.buy_orders[p], sb, pos)
                        if q > 0:
                            o.append(Order(P, p, -q)); sb -= q; pos -= q
                    else:
                        break
            elif pos < 0 and bb > 0:
                for p in sorted(od.sell_orders.keys()):
                    if bb > 0 and pos < 0:
                        q = min(-od.sell_orders[p], bb, -pos)
                        if q > 0:
                            o.append(Order(P, p, q)); bb -= q; pos += q
                    else:
                        break

        # Passive quotes with skew based on z-score
        spread = cfg.get("default_spread", 3)
        skew = round(z * 0.5)  # lean quotes against the deviation
        bid_p = fair - spread - skew
        ask_p = fair + spread - skew

        if pos >= LIM:
            bb = 0
        if pos <= -LIM:
            sb = 0

        l1_pct = cfg.get("l1_pct", 0.65)
        self._post_quotes(o, P, bid_p, ask_p, bb, sb, l1_pct)
        return o

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY 4: BASKET ARBITRAGE (ETF-like composites)
    # Trade the spread between basket price and NAV of components.
    # ═══════════════════════════════════════════════════════════════
    def _basket_arb(self, P, order_depths, positions, cfg, td):
        LIM = cfg["limit"]
        components = cfg.get("components", {})
        o = []

        od = order_depths.get(P)
        if not od or not od.buy_orders or not od.sell_orders:
            return o

        basket_mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2.0

        # Compute NAV (net asset value) from component mids
        nav = 0.0
        for comp, weight in components.items():
            comp_od = order_depths.get(comp)
            if not comp_od or not comp_od.buy_orders or not comp_od.sell_orders:
                return o  # can't price — skip
            comp_mid = (max(comp_od.buy_orders.keys()) +
                        min(comp_od.sell_orders.keys())) / 2.0
            nav += comp_mid * weight

        spread = basket_mid - nav

        # Track spread history for z-score
        key_sh = f"{P}_spread_hist"
        sh = td.get(key_sh, [])
        sh.append(spread)
        window = cfg.get("z_window", 50)
        if len(sh) > window * 2:
            sh = sh[-(window * 2):]
        td[key_sh] = sh

        if len(sh) < max(10, window // 2):
            return o  # not enough data

        recent = sh[-window:] if len(sh) >= window else sh
        mean_s = sum(recent) / len(recent)
        var_s = sum((x - mean_s) ** 2 for x in recent) / len(recent)
        std_s = math.sqrt(var_s) if var_s > 0 else 1.0
        z = (spread - mean_s) / std_s if std_s > 0.01 else 0.0

        pos = positions.get(P, 0)
        bb = LIM - pos
        sb = LIM + pos
        z_entry = cfg.get("z_entry", 1.5)
        z_exit = cfg.get("z_exit", 0.3)

        if z > z_entry and sb > 0:
            # Basket expensive relative to NAV — sell basket
            for p in sorted(od.buy_orders.keys(), reverse=True):
                q = min(od.buy_orders[p], sb, 10)
                if q > 0:
                    o.append(Order(P, p, -q)); sb -= q
                break
        elif z < -z_entry and bb > 0:
            # Basket cheap relative to NAV — buy basket
            for p in sorted(od.sell_orders.keys()):
                q = min(-od.sell_orders[p], bb, 10)
                if q > 0:
                    o.append(Order(P, p, q)); bb -= q
                break

        # Exit when spread normalizes
        if abs(z) < z_exit:
            if pos > 0:
                for p in sorted(od.buy_orders.keys(), reverse=True):
                    q = min(od.buy_orders[p], sb, pos)
                    if q > 0:
                        o.append(Order(P, p, -q))
                    break
            elif pos < 0:
                for p in sorted(od.sell_orders.keys()):
                    q = min(-od.sell_orders[p], bb, -pos)
                    if q > 0:
                        o.append(Order(P, p, q))
                    break

        return o

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY 5: COPY TRADE (follow a specific bot)
    # Tracks a named trader's positions and mirrors them.
    # ═══════════════════════════════════════════════════════════════
    def _copy_trade(self, P, od, pos, cfg, td):
        LIM = cfg["limit"]
        o = []
        target = cfg.get("target_trader", "")
        key = f"{P}_copy_pos"

        # Get the target's implied direction from bot tracker
        bots = td.get("bots", {})
        bot_data = bots.get(P, {}).get(target, {})
        net_dir = bot_data.get("net_dir", 0)  # +1 = buying, -1 = selling

        bb = LIM - pos
        sb = LIM + pos
        size = cfg.get("copy_size", 10)

        if net_dir > 0 and bb > 0:
            # Bot is buying — follow
            for p in sorted(od.sell_orders.keys()):
                q = min(-od.sell_orders[p], bb, size)
                if q > 0:
                    o.append(Order(P, p, q)); bb -= q
                break
        elif net_dir < 0 and sb > 0:
            # Bot is selling — follow
            for p in sorted(od.buy_orders.keys(), reverse=True):
                q = min(od.buy_orders[p], sb, size)
                if q > 0:
                    o.append(Order(P, p, -q)); sb -= q
                break

        return o

    # ═══════════════════════════════════════════════════════════════
    # BOT FINGERPRINTING
    # Tracks trader IDs from market_trades, records direction + volume.
    # ═══════════════════════════════════════════════════════════════
    def _track_bots(self, state: TradingState, td):
        bots = td.get("bots", {})

        if hasattr(state, "market_trades") and state.market_trades:
            for product, trades in state.market_trades.items():
                if product not in bots:
                    bots[product] = {}
                for trade in trades:
                    buyer = trade.buyer if hasattr(trade, "buyer") else ""
                    seller = trade.seller if hasattr(trade, "seller") else ""
                    qty = trade.quantity if hasattr(trade, "quantity") else 0

                    for trader, direction in [(buyer, 1), (seller, -1)]:
                        if not trader or trader == "SUBMISSION":
                            continue
                        if trader not in bots[product]:
                            bots[product][trader] = {
                                "buys": 0, "sells": 0,
                                "total_qty": 0, "net_dir": 0,
                                "last_5": [],
                            }
                        bd = bots[product][trader]
                        if direction > 0:
                            bd["buys"] += qty
                        else:
                            bd["sells"] += qty
                        bd["total_qty"] += qty
                        bd["last_5"].append(direction)
                        if len(bd["last_5"]) > 5:
                            bd["last_5"] = bd["last_5"][-5:]
                        bd["net_dir"] = (
                            1 if sum(bd["last_5"]) > 0
                            else -1 if sum(bd["last_5"]) < 0
                            else 0
                        )

        td["bots"] = bots
        return td

    # ═══════════════════════════════════════════════════════════════
    # REGIME DETECTION
    # Rolling volatility per product. Stored in td for strategies
    # to use for adaptive sizing.
    # ═══════════════════════════════════════════════════════════════
    def _update_regimes(self, state: TradingState, td):
        regimes = td.get("regimes", {})

        for product, od in state.order_depths.items():
            if not od.buy_orders or not od.sell_orders:
                continue
            mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2.0

            key = f"{product}_mids"
            mids = td.get(key, [])
            mids.append(mid)
            if len(mids) > 30:
                mids = mids[-30:]
            td[key] = mids

            if len(mids) >= 10:
                returns = [
                    mids[i] - mids[i - 1] for i in range(1, len(mids))
                ]
                mean_r = sum(returns) / len(returns)
                var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
                vol = math.sqrt(var_r) if var_r > 0 else 0.0

                # Classify regime
                if vol > 3.0:
                    regime = "HIGH_VOL"
                elif vol > 1.5:
                    regime = "NORMAL"
                else:
                    regime = "LOW_VOL"

                regimes[product] = {
                    "vol": round(vol, 3),
                    "regime": regime,
                }

        td["regimes"] = regimes
        return td

    # ═══════════════════════════════════════════════════════════════
    # SHARED UTILITIES
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _find_wall_bid(od, min_vol):
        """Find highest bid with volume >= min_vol (the 'wall')."""
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[p] >= min_vol:
                return p
        # Fallback: best bid
        return max(od.buy_orders.keys()) if od.buy_orders else None

    @staticmethod
    def _find_wall_ask(od, min_vol):
        """Find lowest ask with volume >= min_vol (the 'wall')."""
        for p in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[p]) >= min_vol:
                return p
        # Fallback: best ask
        return min(od.sell_orders.keys()) if od.sell_orders else None

    @staticmethod
    def _find_quote_prices(od, fair, cfg):
        """Find optimal quote prices: penny ahead of best resting level."""
        default = cfg.get("default_spread", 4)
        disregard = cfg.get("disregard", 1)

        # Bid: find best resting bid below fair-disregard, place 1 above it
        bp = fair - default
        for p in sorted(od.buy_orders.keys(), reverse=True):
            if p < fair - disregard:
                bp = p + 1
                break
        bp = min(bp, fair - 1)

        # Ask: find best resting ask above fair+disregard, place 1 below it
        ap = fair + default
        for p in sorted(od.sell_orders.keys()):
            if p > fair + disregard:
                ap = p - 1
                break
        ap = max(ap, fair + 1)

        return bp, ap

    @staticmethod
    def _post_quotes(orders, P, bid_p, ask_p, bb, sb, l1_pct):
        """Post 1 or 2 layer resting quotes."""
        if bb > 0:
            if l1_pct >= 1.0:
                orders.append(Order(P, bid_p, bb))
            else:
                l1 = max(1, int(bb * l1_pct))
                orders.append(Order(P, bid_p, l1))
                l2 = bb - l1
                if l2 > 0:
                    orders.append(Order(P, bid_p - 1, l2))
        if sb > 0:
            if l1_pct >= 1.0:
                orders.append(Order(P, ask_p, -sb))
            else:
                l1 = max(1, int(sb * l1_pct))
                orders.append(Order(P, ask_p, -l1))
                l2 = sb - l1
                if l2 > 0:
                    orders.append(Order(P, ask_p + 1, -l2))