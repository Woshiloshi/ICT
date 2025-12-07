from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd


class MarketPhase(Enum):
    CONSOLIDATION = "Consolidation"
    MANIPULATION = "Manipulation"
    RETRACEMENT = "Retracement"
    DISTRIBUTION = "Distribution"
    UNKNOWN = "Unknown"


class IPDAStateMachine:
    def __init__(self):
        self._current_phase: MarketPhase = MarketPhase.UNKNOWN
        self._phase_start_time: datetime = datetime.utcnow()
        self._phase_data: Dict[str, Any] = {}
        self._last_price = None
        self._asian_high = None
        self._asian_low = None

    @property
    def current_phase(self) -> MarketPhase:
        return self._current_phase

    @property
    def phase_duration(self) -> float:
        return (datetime.utcnow() - self._phase_start_time).total_seconds() / 60  # minutes

    def transition_to(self, new_phase: MarketPhase, data: Optional[Dict[str, Any]] = None):
        if not isinstance(new_phase, MarketPhase):
            raise TypeError("new_phase must be MarketPhase enum")

        if self._current_phase != new_phase:
            previous = self._current_phase.value
            self._current_phase = new_phase
            self._phase_start_time = datetime.utcnow()
            self._phase_data = data or {}
            print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] IPDA → {previous} → {new_phase.value}")
        else:
            if data:
                self._phase_data.update(data)

    def update(self, df: pd.DataFrame, timestamp: Optional[datetime] = None):
        """The brain of TITAN — called every bar"""
        if df.empty or len(df) < 50:
            return

        current_time = timestamp if timestamp else datetime.utcnow()
        current_hour = current_time.hour

        close = df['close'].iloc[-1]
        high = df['high'].iloc[-1]
        low = df['low'].iloc[-1]
        atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]

        # === 1. ASIAN CONSOLIDATION (22:00–07:00 UTC) ===
        if 22 <= current_hour or current_hour < 7:
            if self.current_phase != MarketPhase.CONSOLIDATION:
                self._asian_high = df['high'].max()
                self._asian_low = df['low'].min()
                self.transition_to(MarketPhase.CONSOLIDATION, {
                    "session": "Asian Range",
                    "asian_high": self._asian_high,
                    "asian_low": self._asian_low,
                    "range_pips": round((self._asian_high - self._asian_low) / 0.0001, 1)
                })
            return

        # === 2. LONDON MANIPULATION (07:00–10:00 UTC) ===
        if 7 <= current_hour < 10:
            if self._asian_high and self._asian_low:
                if high > self._asian_high * 1.0005 or low < self._asian_low * 0.9995:
                    direction = "UP" if high > self._asian_high else "DOWN"
                    level = high if direction == "UP" else low
                    self.transition_to(MarketPhase.MANIPULATION, {
                        "raid": f"London {direction} Sweep",
                        "level": level,
                        "break_size_pips": round(abs(level - (self._asian_high if direction == "UP" else self._asian_low)) / 0.0001, 1)
                    })
                    return

        # === 3. RETRACEMENT (Pullback after Manipulation) ===
        if self.current_phase == MarketPhase.MANIPULATION:
            recent_atr = df['high'].sub(df['low']).rolling(14).mean().iloc[-5:].mean()
            if atr > recent_atr * 1.4:  # Strong pullback
                self.transition_to(MarketPhase.RETRACEMENT, {
                    "strength": "Strong",
                    "expected_zone": "FVG / OB Confluence"
                })
                return

        # === 4. DISTRIBUTION (Displacement Run) ===
        if self.current_phase in [MarketPhase.RETRACEMENT, MarketPhase.MANIPULATION]:
            move = abs(close - df['close'].iloc[-10]) / 0.0001
            if move > 35:  # 35+ pip displacement
                trend = "Bullish" if close > df['close'].iloc[-10] else "Bearish"
                self.transition_to(MarketPhase.DISTRIBUTION, {
                    "displacement": f"{trend} Run",
                    "pips_moved": round(move, 1),
                    "trigger": "Confirmed Trend"
                })

    def get_phase_info(self) -> Dict[str, Any]:
        return {
            "phase": self.current_phase.value,
            "duration_min": round(self.phase_duration, 1),
            "since_utc": self._phase_start_time.strftime("%H:%M:%S"),
            "data": self._phase_data
        }

    def __str__(self):
        return f"IPDA[{self.current_phase.value}] @ {self._phase_start_time.strftime('%H:%M:%S')} UTC"