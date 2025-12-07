import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any


class FairValueGap:
    def __init__(self, low: float, high: float, index: int, direction: str):
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
    def __init__(self, price: float, index: int, direction: str):
        self.price = price
        self.index = index
        self.direction = direction
        self.touched = False

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
            next_c = df.iloc[i]

            # Bullish FVG: low[0] > high[2]
            if curr['low'] > prev['high']:
                fvg = FairValueGap(low=curr['low'], high=prev['high'], index=i-1, direction="bullish")
                self.fvgs.append(fvg)

            # Bearish FVG: high[0] < low[2]
            if curr['high'] < prev['low']:
                fvg = FairValueGap(low=prev['low'], high=curr['high'], index=i-1, direction="bearish")
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
        return [ob for ob in self.order_blocks[-10:] if not ob.touched]  # last 10

    def scan(self, df: pd.DataFrame):
        """Run full PD-Array scan"""
        print(f"[SCANNER] Scanning {len(df)} candles...")
        self.scan_fvgs(df)
        self.scan_order_blocks(df)
        print(f"[SCANNER] Found {len(self.get_active_fvgs())} active FVGs | {len(self.get_active_obs())} OBs")