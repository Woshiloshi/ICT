import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

@dataclass
class FairValueGap:
    """Represents a Fair Value Gap (FVG) identified on the chart."""
    timestamp: datetime
    top: float
    bottom: float
    is_bullish: bool # Bullish FVG is an imbalance pointing up, bearish is pointing down
    is_mitigated: bool = False
    
    def __repr__(self):
        return (
            f"FVG({'Bullish' if self.is_bullish else 'Bearish'} at {self.timestamp} "
            f"[{self.bottom:.5f} - {self.top:.5f}], "
            f"Mitigated: {self.is_mitigated})"
        )

@dataclass
class OrderBlock:
    """Represents an Order Block (OB) identified on the chart."""
    timestamp: datetime # Timestamp of the OB candle
    open: float
    high: float
    low: float
    close: float
    is_bullish: bool # A bullish OB is the last down-candle before an up-move
    is_mitigated: bool = False
    
    @property
    def mean_threshold(self) -> float:
        """The mean threshold (50% level) of the order block's body."""
        return (self.open + self.close) / 2

    def __repr__(self):
        return (
            f"OrderBlock({'Bullish' if self.is_bullish else 'Bearish'} at {self.timestamp} "
            f"[{self.open:.5f}, {self.high:.5f}, {self.low:.5f}, {self.close:.5f}], "
            f"Mitigated: {self.is_mitigated})"
        )

@dataclass
class BreakerBlock:
    """Represents a failed Order Block that has become a Breaker."""
    timestamp: datetime # Timestamp of the original OB candle
    open: float
    high: float
    low: float
    close: float
    is_bullish: bool # A bullish breaker was a bullish OB that failed (now a sell setup)
    break_timestamp: datetime # When the block was broken

    def __repr__(self):
        return (
            f"BreakerBlock({'Bullish' if self.is_bullish else 'Bearish'} at {self.timestamp}, "
            f"Broken at {self.break_timestamp})"
        )

@dataclass
class MitigationBlock:
    """Represents a failed swing point that has become a Mitigation Block."""
    timestamp: datetime # Timestamp of the failed swing point candle
    high: float
    low: float
    is_bullish: bool # A bullish mitigation block is a failed swing low
    break_timestamp: datetime

    def __repr__(self):
        return (
            f"MitigationBlock({'Bullish' if self.is_bullish else 'Bearish'} at {self.timestamp}, "
            f"Broken at {self.break_timestamp})"
        )

class MarketScanner:
    """
    Scans OHLC data for specific ICT patterns like Fair Value Gaps and Order Blocks.
    """
    
    @staticmethod
    def is_displacement(candle: pd.Series, avg_body_size: float, multiplier: float = 1.5) -> bool:
        """
        Checks if a candle is a 'Displacement' candle.
        Condition: The candle body must be > (multiplier * average body size).
        """
        body_size = abs(candle['close'] - candle['open'])
        return body_size > (multiplier * avg_body_size)

    @staticmethod
    def find_fair_value_gaps(ohlc_data: pd.DataFrame) -> List[FairValueGap]:
        """
        Finds Fair Value Gaps (FVGs) in the provided OHLC data.
        """
        if len(ohlc_data) < 3:
            return []
        gaps = []
        df = ohlc_data.copy()
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['next_high'] = df['high'].shift(-1)
        df['next_low'] = df['low'].shift(-1)
        bullish_fvg_mask = df['prev_high'] < df['next_low']
        bearish_fvg_mask = df['prev_low'] > df['next_high']
        for i, row in df[bullish_fvg_mask].iterrows():
            gaps.append(FairValueGap(timestamp=row.name, top=row['next_low'], bottom=row['prev_high'], is_bullish=True))
        for i, row in df[bearish_fvg_mask].iterrows():
            gaps.append(FairValueGap(timestamp=row.name, top=row['prev_low'], bottom=row['next_high'], is_bullish=False))
        return sorted(gaps, key=lambda g: g.timestamp)
    
    @staticmethod
    def find_order_blocks(ohlc_data: pd.DataFrame, lookback: int = 20, displacement_multiplier: float = 1.5) -> List[OrderBlock]:
        """
        Finds Order Blocks (OBs) based on preceding displacement moves.
        """
        if len(ohlc_data) < lookback:
            return []
        df = ohlc_data.copy()
        df['body_size'] = abs(df['close'] - df['open'])
        df['avg_body_size'] = df['body_size'].rolling(window=lookback).mean()
        order_blocks = []
        for i in range(lookback, len(df)):
            candle = df.iloc[i]
            prev_candle = df.iloc[i-1]
            avg_body = candle['avg_body_size']
            if MarketScanner.is_displacement(candle, avg_body, displacement_multiplier):
                is_bullish_displacement = candle['close'] > candle['open']
                is_bearish_displacement = candle['close'] < candle['open']
                if is_bullish_displacement and prev_candle['close'] < prev_candle['open']:
                    order_blocks.append(OrderBlock(
                        timestamp=prev_candle.name, open=prev_candle['open'], high=prev_candle['high'],
                        low=prev_candle['low'], close=prev_candle['close'], is_bullish=True))
                elif is_bearish_displacement and prev_candle['close'] > prev_candle['open']:
                    order_blocks.append(OrderBlock(
                        timestamp=prev_candle.name, open=prev_candle['open'], high=prev_candle['high'],
                        low=prev_candle['low'], close=prev_candle['close'], is_bullish=False))
        return order_blocks

    @staticmethod
    def find_swing_points(ohlc_data: pd.DataFrame, n: int = 2) -> Dict[str, List[pd.Series]]:
        """
        Identifies swing high and swing low points in the OHLC data.
        """
        swing_highs = []
        swing_lows = []
        if len(ohlc_data) < (2 * n + 1):
            return {"highs": swing_highs, "lows": swing_lows}
        for i in range(n, len(ohlc_data) - n):
            current_candle = ohlc_data.iloc[i]
            is_swing_high = True
            for j in range(1, n + 1):
                if current_candle['high'] < ohlc_data.iloc[i - j]['high'] or \
                   current_candle['high'] < ohlc_data.iloc[i + j]['high']:
                    is_swing_high = False
                    break
            if is_swing_high:
                swing_highs.append(current_candle)
            is_swing_low = True
            for j in range(1, n + 1):
                if current_candle['low'] > ohlc_data.iloc[i - j]['low'] or \
                   current_candle['low'] > ohlc_data.iloc[i + j]['low']:
                    is_swing_low = False
                    break
            if is_swing_low:
                swing_lows.append(current_candle)
        return {"highs": swing_highs, "lows": swing_lows}

    @staticmethod
    def find_market_structure_shift(ohlc_data: pd.DataFrame, swing_points: Dict[str, List[pd.Series]], last_n_candles: int = 5) -> Optional[Dict[str, Any]]:
        """
        Detects a Market Structure Shift (MSS) based on breaking swing points.
        """
        if ohlc_data.empty or not swing_points["highs"] and not swing_points["lows"]:
            return None
        recent_ohlc = ohlc_data.iloc[-last_n_candles:]
        for swing_high in swing_points["highs"]:
            if swing_high.name < recent_ohlc.index[0]: 
                breaking_candles = recent_ohlc[recent_ohlc['close'] > swing_high['high']]
                if not breaking_candles.empty:
                    return {'type': 'bullish', 'broken_level': swing_high['high'], 'timestamp': breaking_candles.index[-1], 'swing_point_timestamp': swing_high.name}
        for swing_low in swing_points["lows"]:
            if swing_low.name < recent_ohlc.index[0]:
                breaking_candles = recent_ohlc[recent_ohlc['close'] < swing_low['low']]
                if not breaking_candles.empty:
                    return {'type': 'bearish', 'broken_level': swing_low['low'], 'timestamp': breaking_candles.index[-1], 'swing_point_timestamp': swing_low.name}
        return None

    @staticmethod
    def get_session_range(ohlc_data: pd.DataFrame, start_time: datetime.time, end_time: datetime.time) -> Optional[Dict[str, float]]:
        """
        Calculates the high and low of a specific time window in the data.
        """
        try:
            session_data = ohlc_data.between_time(start_time, end_time)
            if session_data.empty:
                return None
            return {"high": session_data['high'].max(), "low": session_data['low'].min()}
        except Exception as e:
            print(f"Error calculating session range: {e}")
            return None

    @staticmethod
    def find_optimal_trade_entry_zone(ohlc_data: pd.DataFrame, swing_points: Dict[str, List[pd.Series]]) -> Optional[Dict[str, Any]]:
        """
        Identifies the OTE zone (62%-79% Fib retracement) of the last major displacement leg.
        """
        if not swing_points['highs'] or not swing_points['lows']:
            return None
        last_swing_high = swing_points['highs'][-1]
        last_swing_low = swing_points['lows'][-1]
        leg_start_price, leg_end_price, direction = (last_swing_low['low'], last_swing_high['high'], 'bullish') if last_swing_high.name > last_swing_low.name else (last_swing_high['high'], last_swing_low['low'], 'bearish')
        leg_range = abs(leg_end_price - leg_start_price)
        if direction == 'bullish':
            ote_top = leg_end_price - (leg_range * 0.62)
            ote_bottom = leg_end_price - (leg_range * 0.79)
            return {"top": ote_top, "bottom": ote_bottom, "direction": "bullish"}
        elif direction == 'bearish':
            ote_top = leg_end_price + (leg_range * 0.79)
            ote_bottom = leg_end_price + (leg_range * 0.62)
            return {"top": ote_top, "bottom": ote_bottom, "direction": "bearish"}
        return None

    @staticmethod
    def find_breaker_blocks(ohlc_data: pd.DataFrame, order_blocks: List[OrderBlock]) -> List[BreakerBlock]:
        """
        Identifies Breaker Blocks from a list of Order Blocks that have failed.
        """
        breakers = []
        for ob in order_blocks:
            subsequent_candles = ohlc_data[ohlc_data.index > ob.timestamp]
            if ob.is_bullish:
                breaking_candles = subsequent_candles[subsequent_candles['close'] > ob.high]
                if not breaking_candles.empty:
                    breakers.append(BreakerBlock(
                        timestamp=ob.timestamp, open=ob.open, high=ob.high, low=ob.low, close=ob.close,
                        is_bullish=True, break_timestamp=breaking_candles.index[0]))
            else:
                breaking_candles = subsequent_candles[subsequent_candles['close'] < ob.low]
                if not breaking_candles.empty:
                    breakers.append(BreakerBlock(
                        timestamp=ob.timestamp, open=ob.open, high=ob.high, low=ob.low, close=ob.close,
                        is_bullish=False, break_timestamp=breaking_candles.index[0]))
        return breakers

    @staticmethod
    def find_mitigation_blocks(ohlc_data: pd.DataFrame, swing_points: Dict[str, List[pd.Series]]) -> List[MitigationBlock]:
        """
        Identifies Mitigation Blocks from failed swing points.
        """
        mitigations = []
        for sh in swing_points['highs']:
            subsequent_candles = ohlc_data[ohlc_data.index > sh.name]
            breaking_candles = subsequent_candles[subsequent_candles['close'] < sh['low']]
            if not breaking_candles.empty:
                mitigations.append(MitigationBlock(
                    timestamp=sh.name, high=sh['high'], low=sh['low'], is_bullish=False,
                    break_timestamp=breaking_candles.index[0]))
        for sl in swing_points['lows']:
            subsequent_candles = ohlc_data[ohlc_data.index > sl.name]
            breaking_candles = subsequent_candles[subsequent_candles['close'] > sl['high']]
            if not breaking_candles.empty:
                mitigations.append(MitigationBlock(
                    timestamp=sl.name, high=sl['high'], low=sl['low'], is_bullish=True,
                    break_timestamp=breaking_candles.index[0]))
        return mitigations

    @staticmethod
    def find_judas_swing(
        ohlc_data: pd.DataFrame,
        asian_range_high: float,
        asian_range_low: float,
        lookback_candles: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Detects a Judas Swing (liquidity sweep of Asian range followed by rejection).

        Args:
            ohlc_data (pd.DataFrame): OHLC data for analysis.
            asian_range_high (float): The high of the Asian session range.
            asian_range_low (float): The low of the Asian session range.
            lookback_candles (int): How many recent candles to check for the sweep and rejection.

        Returns:
            Optional[Dict[str, Any]]: {'type': 'bullish'/'bearish', 'timestamp': rejection_candle_time}
                                      if a Judas Swing is found, otherwise None.
        """
        if len(ohlc_data) < lookback_candles:
            return None

        # Iterate backwards from the most recent candle
        for i in range(len(ohlc_data) - 1, len(ohlc_data) - lookback_candles - 1, -1):
            current_candle = ohlc_data.iloc[i]
            
            # Check for sweep of Asian High
            if current_candle['high'] > asian_range_high and current_candle['close'] < asian_range_high:
                # Price swept above high and closed back inside (bearish rejection)
                return {'type': 'bearish', 'timestamp': current_candle.name}
            
            # Check for sweep of Asian Low
            if current_candle['low'] < asian_range_low and current_candle['close'] > asian_range_low:
                # Price swept below low and closed back inside (bullish rejection)
                return {'type': 'bullish', 'timestamp': current_candle.name}
                
        return None

# Example Usage (for testing purposes)
if __name__ == "__main__":
    print("--- MarketScanner Example ---")
    data = {
        'open':  [1.0800, 1.0810, 1.0790, 1.0780, 1.0830, 1.0840, 1.0850, 1.0820, 1.0810, 1.0795],
        'high':  [1.0815, 1.0820, 1.0805, 1.0855, 1.0860, 1.0855, 1.0865, 1.0835, 1.0825, 1.0800],
        'low':   [1.0795, 1.0805, 1.0785, 1.0775, 1.0825, 1.0830, 1.0845, 1.0815, 1.0805, 1.0790],
        'close': [1.0810, 1.0808, 1.0795, 1.0850, 1.0855, 1.0848, 1.0825, 1.0820, 1.0798, 1.0792]
    }
    index = pd.to_datetime([f'2025-12-08 10:{i:02d}:00' for i in range(10)])
    sample_ohlc = pd.DataFrame(data, index=index)
    
    print("\n--- Finding Order Blocks ---")
    found_obs = MarketScanner.find_order_blocks(sample_ohlc.head(5), lookback=3)
    print(f"Found Order Blocks: {found_obs}")

    print("\n--- Finding Breaker Blocks ---")
    found_breakers = MarketScanner.find_breaker_blocks(sample_ohlc, found_obs)
    print(f"Found Breaker Blocks: {found_breakers}")

    print("\n--- Finding Mitigation Blocks ---")
    swing_points = MarketScanner.find_swing_points(sample_ohlc, n=1)
    found_mitigations = MarketScanner.find_mitigation_blocks(sample_ohlc, swing_points)
    print(f"Found Mitigation Blocks: {found_mitigations}")

    # 5. Test Judas Swing detection
    print("\n--- Finding Judas Swing ---")
    asian_high = 1.0800
    asian_low = 1.0750
    # Simulate a candle that sweeps high and closes back in, then a rejection
    judas_data = {
        'open':  [1.0790, 1.0780, 1.0810, 1.0795],
        'high':  [1.0795, 1.0805, 1.0815, 1.0800],
        'low':   [1.0785, 1.0775, 1.0800, 1.0790],
        'close': [1.0788, 1.0798, 1.0802, 1.0792],
    }
    judas_ohlc = pd.DataFrame(judas_data, index=pd.to_datetime([f'2025-12-08 02:{i:02d}:00' for i in range(4)]))
    
    # Expected: Candle at 02:02 sweeps 1.0800 high (high=1.0815), closes at 1.0802 (back below or near 1.0800)
    judas_swing = MarketScanner.find_judas_swing(judas_ohlc, asian_high, asian_low, lookback_candles=4)
    print(f"Found Judas Swing: {judas_swing}")
