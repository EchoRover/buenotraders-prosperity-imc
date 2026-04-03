
from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import json
import math
 
 
# ── Configuration ────────────────────────────────────────────────────────────
 
POSITION_LIMITS = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}
 
# EMERALDS parameters
EMERALD_FAIR_VALUE   = 10_000       # rock-solid anchor
EMERALD_TAKE_WIDTH   = 1            # take anything within ±1 of fair
EMERALD_MAKE_SPREAD  = 3            # quote 3 away from fair (bid 9997, ask 10003)
EMERALD_SKEW_FACTOR  = 0.15         # basis points of skew per unit of inventory
 
# TOMATOES parameters
TOMATO_LR_LOOKBACK   = 10           # ticks of mid-price history for linear regression
TOMATO_TAKE_WIDTH    = 1            # take anything within ±1 of fair
TOMATO_MAKE_SPREAD   = 3            # quote spread half-width from fair
TOMATO_SKEW_FACTOR   = 0.20         # stronger skew — this product drifts
 
 
# ── Helper functions ─────────────────────────────────────────────────────────
 
def get_mid_price(order_depth: OrderDepth) -> float | None:
    """Compute mid-price from best bid / best ask."""
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    best_bid = max(order_depth.buy_orders.keys())
    best_ask = min(order_depth.sell_orders.keys())
    return (best_bid + best_ask) / 2.0
 
 
def get_vwap_mid(order_depth: OrderDepth) -> float | None:
    """Volume-weighted mid: weights each side by the OTHER side's top volume."""
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    best_bid = max(order_depth.buy_orders.keys())
    best_ask = min(order_depth.sell_orders.keys())
    bid_vol  = order_depth.buy_orders[best_bid]
    ask_vol  = abs(order_depth.sell_orders[best_ask])
    if bid_vol + ask_vol == 0:
        return (best_bid + best_ask) / 2.0
    return (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
 
 
def linear_regression_fair(prices: list[float]) -> float:
    """
    Fit y = a + b*x on the last N mid-prices and extrapolate 1 step ahead.
    This captures local drift/trend in TOMATOES.
    """
    n = len(prices)
    if n < 2:
        return prices[-1]
    x  = list(range(n))
    mx = sum(x) / n
    my = sum(prices) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, prices))
    var = sum((xi - mx) ** 2 for xi in x)
    if var == 0:
        return prices[-1]
    b = cov / var
    a = my - b * mx
    return a + b * n  # extrapolate to x = n (one step ahead)
 
 
def clamp_order_quantity(
    product: str,
    current_position: int,
    desired_qty: int,   # positive = buy, negative = sell
) -> int:
    """Clip order quantity so that resulting position stays within limits."""
    limit = POSITION_LIMITS.get(product, 50)
    if desired_qty > 0:
        max_buy = limit - current_position
        return max(0, min(desired_qty, max_buy))
    else:
        max_sell = limit + current_position    # how much more we can sell
        return min(0, max(-max_sell, desired_qty))
 
 
# ── Core strategy per product ───────────────────────────────────────────────
 
def trade_emeralds(
    order_depth: OrderDepth,
    position: int,
    trader_data: dict,
) -> List[Order]:
    """
    EMERALDS — Static Market Making around 10,000
    -----------------------------------------------
    1. TAKE phase:  sweep any resting orders that are mispriced
       (asks ≤ fair - take_width  OR  bids ≥ fair + take_width).
    2. MAKE phase:  place our own bid/ask quotes at fair ± spread,
       skewed by current inventory to push position back toward zero.
    """
    orders: List[Order] = []
    fair = EMERALD_FAIR_VALUE  # 10,000
 
    # ── 1. TAKE: aggressively hit mispriced resting orders ──────────────
    # Buy from anyone selling at or below (fair - take_width)
    for ask_price in sorted(order_depth.sell_orders.keys()):
        if ask_price <= fair - EMERALD_TAKE_WIDTH:
            ask_vol = order_depth.sell_orders[ask_price]  # negative number
            qty = clamp_order_quantity("EMERALDS", position, -ask_vol)
            if qty > 0:
                orders.append(Order("EMERALDS", ask_price, qty))
                position += qty
        else:
            break
 
    # Sell to anyone buying at or above (fair + take_width)
    for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
        if bid_price >= fair + EMERALD_TAKE_WIDTH:
            bid_vol = order_depth.buy_orders[bid_price]
            qty = clamp_order_quantity("EMERALDS", position, -bid_vol)
            if qty < 0:
                orders.append(Order("EMERALDS", bid_price, qty))
                position += qty
        else:
            break
 
    # ── 2. MAKE: place quotes with inventory-aware skew ──────────────────
    # Skew: if we're long, lower our bid and improve our ask to sell faster
    skew = round(position * EMERALD_SKEW_FACTOR)
 
    bid_price = round(fair - EMERALD_MAKE_SPREAD - skew)
    ask_price = round(fair + EMERALD_MAKE_SPREAD - skew)
 
    bid_qty = clamp_order_quantity("EMERALDS", position, POSITION_LIMITS["EMERALDS"] - position)
    ask_qty = clamp_order_quantity("EMERALDS", position, -(POSITION_LIMITS["EMERALDS"] + position))
 
    if bid_qty > 0:
        orders.append(Order("EMERALDS", bid_price, bid_qty))
    if ask_qty < 0:
        orders.append(Order("EMERALDS", ask_price, ask_qty))
 
    return orders
 
 
def trade_tomatoes(
    order_depth: OrderDepth,
    position: int,
    trader_data: dict,
) -> (List[Order], dict):
    """
    TOMATOES — Adaptive Fair-Value Market Making
    ----------------------------------------------
    1. Compute fair value via linear regression on recent mid-prices.
    2. TAKE phase: sweep mispriced orders relative to our fair value.
    3. MAKE phase: post quotes at fair ± spread, skewed by inventory.
    """
    orders: List[Order] = []
 
    # ── Update mid-price history ─────────────────────────────────────────
    mid = get_mid_price(order_depth)
    if mid is None:
        return orders, trader_data
 
    history = trader_data.get("tomato_history", [])
    history.append(mid)
    # Keep only what we need
    if len(history) > TOMATO_LR_LOOKBACK + 5:
        history = history[-(TOMATO_LR_LOOKBACK + 5):]
    trader_data["tomato_history"] = history
 
    # ── Compute fair value ───────────────────────────────────────────────
    if len(history) >= TOMATO_LR_LOOKBACK:
        fair = linear_regression_fair(history[-TOMATO_LR_LOOKBACK:])
    else:
        fair = mid  # not enough data yet, just use mid
    fair = round(fair, 1)
 
    # ── 1. TAKE: hit mispriced resting orders ────────────────────────────
    for ask_price in sorted(order_depth.sell_orders.keys()):
        if ask_price <= fair - TOMATO_TAKE_WIDTH:
            ask_vol = order_depth.sell_orders[ask_price]
            qty = clamp_order_quantity("TOMATOES", position, -ask_vol)
            if qty > 0:
                orders.append(Order("TOMATOES", ask_price, qty))
                position += qty
        else:
            break
 
    for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
        if bid_price >= fair + TOMATO_TAKE_WIDTH:
            bid_vol = order_depth.buy_orders[bid_price]
            qty = clamp_order_quantity("TOMATOES", position, -bid_vol)
            if qty < 0:
                orders.append(Order("TOMATOES", bid_price, qty))
                position += qty
        else:
            break
 
    # ── 2. MAKE: quotes with inventory skew ──────────────────────────────
    skew = round(position * TOMATO_SKEW_FACTOR)
 
    bid_price = round(fair - TOMATO_MAKE_SPREAD - skew)
    ask_price = round(fair + TOMATO_MAKE_SPREAD - skew)
 
    bid_qty = clamp_order_quantity("TOMATOES", position, POSITION_LIMITS["TOMATOES"] - position)
    ask_qty = clamp_order_quantity("TOMATOES", position, -(POSITION_LIMITS["TOMATOES"] + position))
 
    if bid_qty > 0:
        orders.append(Order("TOMATOES", bid_price, bid_qty))
    if ask_qty < 0:
        orders.append(Order("TOMATOES", ask_price, ask_qty))
 
    return orders, trader_data
 
 
# ── Main Trader class (required by Prosperity) ──────────────────────────────
 
class Trader:
    """
    Entry point for the Prosperity simulation engine.
    The `run` method is called every iteration with the current TradingState.
    It must return:
        result      — Dict[str, List[Order]]   orders per product
        conversions — int                        (0, not used in tutorial)
        traderData  — str                        serialised state for next tick
    """
 
    def run(self, state: TradingState):
        # ── Deserialise persistent state ─────────────────────────────────
        trader_data: dict = {}
        if state.traderData and state.traderData != "":
            try:
                trader_data = json.loads(state.traderData)
            except (json.JSONDecodeError, TypeError):
                trader_data = {}
 
        result: Dict[str, List[Order]] = {}
 
        # ── Trade each product ───────────────────────────────────────────
        for product in state.order_depths:
            order_depth = state.order_depths[product]
            position = state.position.get(product, 0)
 
            if product == "EMERALDS":
                result[product] = trade_emeralds(order_depth, position, trader_data)
 
            elif product == "TOMATOES":
                orders, trader_data = trade_tomatoes(order_depth, position, trader_data)
                result[product] = orders
 
        # ── Serialise state for next iteration ───────────────────────────
        conversions = 0
        trader_data_str = json.dumps(trader_data)
 
        return result, conversions, trader_data_str
 