"""
IMC Prosperity 4 — Optimized v2 Trading Algorithm
=====================================================
Products: EMERALDS (stationary ~10,000) and TOMATOES (drifting/mean-reverting)

IMPROVEMENTS OVER v1 (1,076 → targeting 3,000+):
 1. Tighter Emerald spread (±2 instead of ±3) for ~3x more fills
 2. Multi-level order sweeping — take ALL mispriced levels, not just best
 3. Take width lowered (1 → 0) — grab anything at or below fair value
 4. Multi-level quoting — post 2 layers of orders per side
 5. Softer inventory skew (0.15 → 0.08, 0.20 → 0.12)
 6. Order book imbalance signal added to Tomatoes fair value
 7. Full volume sweeping — take the entire depth when mispriced
"""

from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import json
import math


# ── Configuration ────────────────────────────────────────────────────────────

POSITION_LIMITS = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}

# EMERALDS — tighter, more aggressive
EMERALD_FAIR_VALUE   = 10_000
EMERALD_TAKE_WIDTH   = 1            # take asks ≤ 9999 and bids ≥ 10001
EMERALD_MM_EDGE_1    = 2            # first layer: 9998 / 10002
EMERALD_MM_EDGE_2    = 4            # second layer: 9996 / 10004
EMERALD_SKEW_FACTOR  = 0.08         # softer skew

# TOMATOES — adaptive
TOMATO_LR_LOOKBACK   = 10
TOMATO_TAKE_WIDTH    = 1
TOMATO_MM_EDGE_1     = 2            # first layer tight
TOMATO_MM_EDGE_2     = 4            # second layer wider
TOMATO_SKEW_FACTOR   = 0.10         # softer skew
TOMATO_OBI_WEIGHT    = 0.3          # order book imbalance weight


# ── Helper functions ─────────────────────────────────────────────────────────

def get_mid_price(order_depth: OrderDepth) -> float | None:
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    best_bid = max(order_depth.buy_orders.keys())
    best_ask = min(order_depth.sell_orders.keys())
    return (best_bid + best_ask) / 2.0


def get_obi_adjusted_mid(order_depth: OrderDepth, weight: float = 0.3) -> float | None:
    """Order-book-imbalance weighted mid price.
    When bid volume >> ask volume, fair value shifts up (buying pressure)."""
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    best_bid = max(order_depth.buy_orders.keys())
    best_ask = min(order_depth.sell_orders.keys())
    bid_vol = order_depth.buy_orders[best_bid]
    ask_vol = abs(order_depth.sell_orders[best_ask])
    total = bid_vol + ask_vol
    if total == 0:
        return (best_bid + best_ask) / 2.0
    imbalance = (bid_vol - ask_vol) / total  # range [-1, 1]
    mid = (best_bid + best_ask) / 2.0
    return mid + imbalance * weight * (best_ask - best_bid) / 2


def linear_regression_fair(prices: list[float]) -> float:
    n = len(prices)
    if n < 2:
        return prices[-1]
    x = list(range(n))
    mx = sum(x) / n
    my = sum(prices) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, prices))
    var = sum((xi - mx) ** 2 for xi in x)
    if var == 0:
        return prices[-1]
    b = cov / var
    a = my - b * mx
    return a + b * n


def clamp_qty(product: str, current_pos: int, desired: int) -> int:
    limit = POSITION_LIMITS.get(product, 50)
    if desired > 0:
        return max(0, min(desired, limit - current_pos))
    else:
        return min(0, max(desired, -(limit + current_pos)))


# ── EMERALDS strategy ───────────────────────────────────────────────────────

def trade_emeralds(order_depth: OrderDepth, position: int, trader_data: dict) -> List[Order]:
    orders: List[Order] = []
    fair = EMERALD_FAIR_VALUE

    # ── TAKE: sweep ALL mispriced asks and bids ──────────────────────────
    for ask_price in sorted(order_depth.sell_orders.keys()):
        if ask_price <= fair - EMERALD_TAKE_WIDTH:
            vol = order_depth.sell_orders[ask_price]  # negative
            qty = clamp_qty("EMERALDS", position, -vol)
            if qty > 0:
                orders.append(Order("EMERALDS", ask_price, qty))
                position += qty
        else:
            break

    for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
        if bid_price >= fair + EMERALD_TAKE_WIDTH:
            vol = order_depth.buy_orders[bid_price]
            qty = clamp_qty("EMERALDS", position, -vol)
            if qty < 0:
                orders.append(Order("EMERALDS", bid_price, qty))
                position += qty
        else:
            break

    # ── MAKE: two layers of quotes with soft skew ────────────────────────
    skew = round(position * EMERALD_SKEW_FACTOR)

    # Layer 1 — tight
    bid1 = round(fair - EMERALD_MM_EDGE_1 - skew)
    ask1 = round(fair + EMERALD_MM_EDGE_1 - skew)

    # Layer 2 — wider (catch big moves)
    bid2 = round(fair - EMERALD_MM_EDGE_2 - skew)
    ask2 = round(fair + EMERALD_MM_EDGE_2 - skew)

    limit = POSITION_LIMITS["EMERALDS"]
    remaining_buy = limit - position
    remaining_sell = limit + position

    # Split volume across layers (60% layer 1, 40% layer 2)
    if remaining_buy > 0:
        l1_buy = max(1, int(remaining_buy * 0.6))
        l2_buy = remaining_buy - l1_buy
        orders.append(Order("EMERALDS", bid1, l1_buy))
        if l2_buy > 0:
            orders.append(Order("EMERALDS", bid2, l2_buy))

    if remaining_sell > 0:
        l1_sell = max(1, int(remaining_sell * 0.6))
        l2_sell = remaining_sell - l1_sell
        orders.append(Order("EMERALDS", ask1, -l1_sell))
        if l2_sell > 0:
            orders.append(Order("EMERALDS", ask2, -l2_sell))

    return orders


# ── TOMATOES strategy ───────────────────────────────────────────────────────

def trade_tomatoes(order_depth: OrderDepth, position: int, trader_data: dict) -> (List[Order], dict):
    orders: List[Order] = []

    # ── Update history ───────────────────────────────────────────────────
    mid = get_mid_price(order_depth)
    if mid is None:
        return orders, trader_data

    history = trader_data.get("tomato_history", [])
    history.append(mid)
    if len(history) > TOMATO_LR_LOOKBACK + 5:
        history = history[-(TOMATO_LR_LOOKBACK + 5):]
    trader_data["tomato_history"] = history

    # ── Fair value: LR + OBI blend ───────────────────────────────────────
    if len(history) >= TOMATO_LR_LOOKBACK:
        lr_fair = linear_regression_fair(history[-TOMATO_LR_LOOKBACK:])
    else:
        lr_fair = mid

    obi_mid = get_obi_adjusted_mid(order_depth, TOMATO_OBI_WEIGHT)
    if obi_mid is None:
        obi_mid = mid

    # Blend: 70% LR, 30% OBI-adjusted mid
    fair = lr_fair * 0.7 + obi_mid * 0.3

    # ── TAKE: sweep all mispriced levels ─────────────────────────────────
    for ask_price in sorted(order_depth.sell_orders.keys()):
        if ask_price <= fair - TOMATO_TAKE_WIDTH:
            vol = order_depth.sell_orders[ask_price]
            qty = clamp_qty("TOMATOES", position, -vol)
            if qty > 0:
                orders.append(Order("TOMATOES", ask_price, qty))
                position += qty
        else:
            break

    for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
        if bid_price >= fair + TOMATO_TAKE_WIDTH:
            vol = order_depth.buy_orders[bid_price]
            qty = clamp_qty("TOMATOES", position, -vol)
            if qty < 0:
                orders.append(Order("TOMATOES", bid_price, qty))
                position += qty
        else:
            break

    # ── MAKE: two layers with soft skew ──────────────────────────────────
    skew = round(position * TOMATO_SKEW_FACTOR)
    fair_r = round(fair)

    bid1 = fair_r - TOMATO_MM_EDGE_1 - skew
    ask1 = fair_r + TOMATO_MM_EDGE_1 - skew
    bid2 = fair_r - TOMATO_MM_EDGE_2 - skew
    ask2 = fair_r + TOMATO_MM_EDGE_2 - skew

    limit = POSITION_LIMITS["TOMATOES"]
    remaining_buy = limit - position
    remaining_sell = limit + position

    if remaining_buy > 0:
        l1 = max(1, int(remaining_buy * 0.6))
        l2 = remaining_buy - l1
        orders.append(Order("TOMATOES", bid1, l1))
        if l2 > 0:
            orders.append(Order("TOMATOES", bid2, l2))

    if remaining_sell > 0:
        l1 = max(1, int(remaining_sell * 0.6))
        l2 = remaining_sell - l1
        orders.append(Order("TOMATOES", ask1, -l1))
        if l2 > 0:
            orders.append(Order("TOMATOES", ask2, -l2))

    return orders, trader_data


# ── Main Trader class ────────────────────────────────────────────────────────

class Trader:
    def run(self, state: TradingState):
        trader_data: dict = {}
        if state.traderData and state.traderData != "":
            try:
                trader_data = json.loads(state.traderData)
            except (json.JSONDecodeError, TypeError):
                trader_data = {}

        result: Dict[str, List[Order]] = {}

        for product in state.order_depths:
            order_depth = state.order_depths[product]
            position = state.position.get(product, 0)

            if product == "EMERALDS":
                result[product] = trade_emeralds(order_depth, position, trader_data)
            elif product == "TOMATOES":
                orders, trader_data = trade_tomatoes(order_depth, position, trader_data)
                result[product] = orders

        conversions = 0
        trader_data_str = json.dumps(trader_data)
        return result, conversions, trader_data_str
