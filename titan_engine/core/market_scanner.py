import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta


class FairValueGap:
    def __init__(self, low: float, high: float, index: datetime, direction: str):
        self.low = low
        self.high = high
        self.index = index
        self.direction = direction  # "bullish" or "bearish"
        self.mitigated = False
        self.mitigated_at = None

    def is_mitigated(self, price: float) -> bool:
        if self.mitigated:
            return True
        if self.direction == "bullish" and price <= self.low:
            self.mitigated = True
            self.mitigated_at = price
            return True
        if self.direction == "bearish" and price >= self.high:
            self.mitigated = True
            self.mitigated_at = price
            return True
        return False

    def __repr__(self):
        return f"FVG[{self.direction.upper()}] {self.low:.5f}-{self.high:.5f} @ {self.index}"


class OrderBlock:
    def __init__(self, price: float, index: datetime, direction: str):
        self.price = price
        self.index = index
        self.direction = direction
        self.mitigated = False  # Added mitigated attribute
        self.mitigated_at = None

    def is_mitigated(self, price: float) -> bool:
        if self.mitigated:
            return True
        if self.direction == "bullish" and price <= self.price: # Price crosses below OB
            self.mitigated = True
            self.mitigated_at = price
            return True
        if self.direction == "bearish" and price >= self.price: # Price crosses above OB
            self.mitigated = True
            self.mitigated_at = price
            return True
        return False

    def __repr__(self):
        return f"OB[{self.direction.upper()}] {self.price:.5f} @ {self.index}"


class MarketScanner:
    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        self.fvgs: List[FairValueGap] = []
        self.order_blocks: List[OrderBlock] = []
        self.breaker_blocks = []
        self.mitigation_blocks = []

    def scan_fvgs(self, df: pd.DataFrame) -> List[FairValueGap]:
        """Detect 3-candle Fair Value Gaps"""
        self.fvgs = []
        for i in range(2, len(df) - 1):
            prev = df.iloc[i-2]
            curr = df.iloc[i-1]
            # next_c = df.iloc[i] # This variable is not used

            # Bullish FVG: low[0] > high[2] - should be low[curr] > high[prev]
            if curr['low'] > prev['high']: # Corrected FVG logic
                fvg = FairValueGap(low=curr['low'], high=prev['high'], index=df.index[i-1], direction="bullish")
                self.fvgs.append(fvg)

            # Bearish FVG: high[0] < low[2] - should be high[curr] < low[prev]
            if curr['high'] < prev['low']: # Corrected FVG logic
                fvg = FairValueGap(low=prev['low'], high=curr['high'], index=df.index[i-1], direction="bearish")
                self.fvgs.append(fvg)
        return self.fvgs

    def scan_order_blocks(self, df: pd.DataFrame) -> List[OrderBlock]:
        """Detect last opposing candle before displacement (simplified)"""
        self.order_blocks = []
        for i in range(5, len(df)):
            window = df.iloc[i-5:i]
            if len(window) < 5:
                continue

            # Bullish OB: last red candle before strong green move
            bullish_candidates = window[window['close'] < window['open']]
            if not bullish_candidates.empty and (window['close'] > window['open']).sum() >= 4:
                last_red = bullish_candidates.iloc[-1]
                ob = OrderBlock(price=last_red['high'], index=last_red.name, direction="bullish")
                self.order_blocks.append(ob)

            # Bearish OB
            bearish_candidates = window[window['close'] > window['open']]
            if not bearish_candidates.empty and (window['close'] < window['open']).sum() >= 4:
                last_green = bearish_candidates.iloc[-1]
                ob = OrderBlock(price=last_green['low'], index=last_green.name, direction="bearish")
                self.order_blocks.append(ob)
        return self.order_blocks

    def get_active_fvgs(self) -> List[FairValueGap]:
        return [fvg for fvg in self.fvgs if not fvg.mitigated]

    def get_active_obs(self) -> List[OrderBlock]:
        return [ob for ob in self.order_blocks[-10:] if not ob.mitigated]  # Filter out mitigated OBs

    def scan(self, df: pd.DataFrame):
        """Run full PD-Array scan"""
        print(f"[SCANNER] Scanning {len(df)} candles...")
        self.scan_fvgs(df)
        self.scan_order_blocks(df)
        print(f"[SCANNER] Found {len(self.get_active_fvgs())} active FVGs | {len(self.get_active_obs())} OBs")

    def calculate_average_body_size(self, df: pd.DataFrame, lookback: int = 10) -> float:
        """Calculates the average candle body size over a given lookback period."""
        if len(df) < lookback:
            return 0.0
        bodies = abs(df['open'].iloc[-lookback:] - df['close'].iloc[-lookback:])
        return bodies.mean()

    def detect_displacement(self, df: pd.DataFrame, multiplier: float = 2.0, lookback: int = 5) -> bool:
        """
        Detects if the last candle's body size indicates a displacement.
        Displacement is when the current candle body is > `multiplier` * average body size.
        """
        if len(df) < lookback + 1:  # Need enough data for average and current candle
            return False

        avg_body_size = self.calculate_average_body_size(df.iloc[:-1], lookback) # Avg of previous candles
        current_candle_body = abs(df['open'].iloc[-1] - df['close'].iloc[-1])

        return current_candle_body > (avg_body_size * multiplier)

    def detect_market_structure_shift(self, df: pd.DataFrame, lookback: int = 10, swing_strength: int = 2) -> Optional[str]:
        """
        Detects a Market Structure Shift (MSS) based on breaking a recent swing high/low.
        A swing high/low is identified by 'swing_strength' candles before and after it
        having lower/higher highs/lows respectively.

        Returns "bullish" for a bullish MSS, "bearish" for a bearish MSS, or None.
        """
        if len(df) < lookback + swing_strength * 2 + 1:
            return None

        # Simplified approach: find recent swing high/low within lookback window
        window = df.iloc[-lookback-1:-1] # Exclude the very last candle for MSS detection
        
        # Detect swing highs
        swing_highs = []
        for i in range(swing_strength, len(window) - swing_strength):
            is_swing_high = True
            for j in range(1, swing_strength + 1):
                if window['high'].iloc[i] < window['high'].iloc[i-j] or \
                   window['high'].iloc[i] < window['high'].iloc[i+j]:
                    is_swing_high = False
                    break
            if is_swing_high:
                swing_highs.append(window['high'].iloc[i])
        
        # Detect swing lows
        swing_lows = []
        for i in range(swing_strength, len(window) - swing_strength):
            is_swing_low = True
            for j in range(1, swing_strength + 1):
                if window['low'].iloc[i] > window['low'].iloc[i-j] or \
                   window['low'].iloc[i] > window['low'].iloc[i+j]:
                    is_swing_low = False
                    break
            if is_swing_low:
                swing_lows.append(window['low'].iloc[i])

        current_price = df['close'].iloc[-1]
        
        # Check for bullish MSS (price breaks above a recent swing high)
        if swing_highs and current_price > max(swing_highs):
            return "bullish"
            
        # Check for bearish MSS (price breaks below a recent swing low)
        if swing_lows and current_price < min(swing_lows):
            return "bearish"
            
        return None

    def detect_judas_swing(self, df: pd.DataFrame, lookback: int = 10, swing_strength: int = 2) -> Optional[str]:
        """
        Detects a Judas Swing (liquidity raid and immediate rejection).
        Looks for a candle that sweeps a recent swing high/low and then closes with significant rejection.
        """
        if len(df) < lookback + swing_strength * 2 + 1:
            return None

        window = df.iloc[-lookback-1:-1] # Exclude the very last candle for swing point detection

        # Detect swing highs and lows in the window
        swing_highs = []
        for i in range(swing_strength, len(window) - swing_strength):
            is_swing_high = True
            for j in range(1, swing_strength + 1):
                if window['high'].iloc[i] < window['high'].iloc[i-j] or \
                   window['high'].iloc[i] < window['high'].iloc[i+j]:
                    is_swing_high = False
                    break
            if is_swing_high:
                swing_highs.append(window['high'].iloc[i])
        
        swing_lows = []
        for i in range(swing_strength, len(window) - swing_strength):
            is_swing_low = True
            for j in range(1, swing_strength + 1):
                if window['low'].iloc[i] > window['low'].iloc[i-j] or \
                   window['low'].iloc[i] > window['low'].iloc[i+j]:
                    is_swing_low = False
                    break
            if is_swing_low:
                swing_lows.append(window['low'].iloc[i])
        
        current_candle = df.iloc[-1]
        
        # Check for bearish Judas Swing (sweeps old high, rejects lower)
        if swing_highs and current_candle['high'] > max(swing_highs):
            # Rejection: closes bearish AND upper wick is larger than body
            if current_candle['close'] < current_candle['open'] and \
               (current_candle['high'] - current_candle['close']) > (current_candle['close'] - current_candle['low']):
                return "bearish"
        
        # Check for bullish Judas Swing (sweeps old low, rejects higher)
        if swing_lows and current_candle['low'] < min(swing_lows):
            # Rejection: closes bullish AND lower wick is larger than body
            if current_candle['close'] > current_candle['open'] and \
               (current_candle['close'] - current_candle['low']) > (current_candle['high'] - current_candle['close']):
                return "bullish"
                
        return None

    def get_last_swing_high_low(self, df: pd.DataFrame, lookback: int = 20, swing_strength: int = 2) -> Dict[str, Optional[float]]:
        """
        Identifies the last confirmed swing high and swing low within the lookback period.
        A swing high/low is identified by 'swing_strength' candles before and after it
        having lower/higher highs/lows respectively.
        """
        swing_high = None
        swing_low = None

        if len(df) < lookback + swing_strength * 2 + 1:
            return {"high": None, "low": None}

        # Iterate backwards from the second to last candle to find the most recent swing points
        for i in range(len(df) - 1 - swing_strength, swing_strength - 1, -1):
            is_swing_high = True
            is_swing_low = True
            
            # Check for swing high
            for j in range(1, swing_strength + 1):
                if df['high'].iloc[i] < df['high'].iloc[i-j] or \
                   df['high'].iloc[i] < df['high'].iloc[i+j]:
                    is_swing_high = False
                    break
            if is_swing_high and swing_high is None:
                swing_high = df['high'].iloc[i]
            
            # Check for swing low
            for j in range(1, swing_strength + 1):
                if df['low'].iloc[i] > df['low'].iloc[i-j] or \
                   df['low'].iloc[i] > df['low'].iloc[i+j]:
                    is_swing_low = False
                    break
            if is_swing_low and swing_low is None:
                swing_low = df['low'].iloc[i]
            
            if swing_high is not None and swing_low is not None:
                break # Found both, no need to continue

        return {"high": swing_high, "low": swing_low}

    def is_range_bound(self, df: pd.DataFrame, range_threshold_multiplier: float = 2.0, lookback_candles: int = 30) -> bool:
        """
        Determines if the market is range-bound based on the average candle body size.
        A market is considered range-bound if the total high-low range over a lookback period
        is not significantly larger than the average candle body size.
        """
        if len(df) < lookback_candles:
            return False

        window = df.iloc[-lookback_candles:]
        max_high = window['high'].max()
        min_low = window['low'].min()
        total_range = max_high - min_low

        avg_body_size = self.calculate_average_body_size(window, lookback_candles)

        # If the total range is less than a multiplier of the average body size, it's range-bound
        return total_range < (avg_body_size * range_threshold_multiplier)

    def get_liquidity_pools(self, df: pd.DataFrame, lookback: int = 20, swing_strength: int = 2) -> Dict[str, List[float]]:
        """
        Identifies significant swing highs and lows within a specified lookback period
        that can serve as liquidity pools.
        """
        liquidity_highs = []
        liquidity_lows = []

        if len(df) < lookback + swing_strength * 2 + 1:
            return {"highs": [], "lows": []}
        
        # Consider a window to detect liquidity pools
        window = df.iloc[-lookback:]

        for i in range(swing_strength, len(window) - swing_strength):
            # Detect swing high
            is_swing_high = True
            for j in range(1, swing_strength + 1):
                if window['high'].iloc[i] < window['high'].iloc[i-j] or \
                   window['high'].iloc[i] < window['high'].iloc[i+j]:
                    is_swing_high = False
                    break
            if is_swing_high:
                liquidity_highs.append(window['high'].iloc[i])
            
            # Detect swing low
            is_swing_low = True
            for j in range(1, swing_strength + 1):
                if window['low'].iloc[i] > window['low'].iloc[i-j] or \
                   window['low'].iloc[i] > window['low'].iloc[i+j]:
                    is_swing_low = False
                    break
            if is_swing_low:
                liquidity_lows.append(window['low'].iloc[i])
        
        return {"highs": liquidity_highs, "lows": liquidity_lows}
