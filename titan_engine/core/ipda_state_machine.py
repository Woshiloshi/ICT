from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional

class MarketPhase(Enum):
    """
    Represents the three core market phases as defined by IPDA.
    """
    CONSOLIDATION = "Consolidation" # Wait phase (e.g., Asian Session range-bound)
    MANIPULATION = "Manipulation"   # Judas Swing, Liquidity Raid
    DISTRIBUTION = "Distribution"   # Trend continuation, displacement, actual trade execution
    RETRACEMENT = "Retracement"     # Entry phase (e.g., price retrace into FVG/OB)
    UNKNOWN = "Unknown"             # Initial or unclassified state

class IPDAStateMachine:
    """
    A finite state machine that classifies the market into one of the defined phases
    (Consolidation, Manipulation, Distribution, Retracement).
    This machine's state transitions will be driven by market data analysis,
    as detailed in the "Logic Flow" section of the specification.
    """
    def __init__(self):
        self._current_phase: MarketPhase = MarketPhase.UNKNOWN
        self._phase_start_time: datetime = datetime.utcnow()
        self._phase_data: Dict[str, Any] = {} # To store relevant data for the current phase

    @property
    def current_phase(self) -> MarketPhase:
        """Returns the current market phase."""
        return self._current_phase

    @property
    def phase_start_time(self) -> datetime:
        """Returns the UTC datetime when the current phase started."""
        return self._phase_start_time

    @property
    def phase_data(self) -> Dict[str, Any]:
        """Returns a dictionary of data associated with the current phase."""
        return self._phase_data

    def transition_to(self, new_phase: MarketPhase, data: Optional[Dict[str, Any]] = None):
        """
        Transitions the state machine to a new market phase.

        Args:
            new_phase: The MarketPhase to transition to.
            data: Optional dictionary of data relevant to the new phase.
        """
        if not isinstance(new_phase, MarketPhase):
            raise TypeError("new_phase must be an instance of MarketPhase Enum.")

        if self._current_phase != new_phase:
            previous_phase = self._current_phase
            self._current_phase = new_phase
            self._phase_start_time = datetime.utcnow() # Mark transition time in UTC
            self._phase_data = data if data is not None else {}
            print(f"[{datetime.utcnow().isoformat()}] State Transition: {previous_phase.value} -> {self._current_phase.value}")
        else:
            # If attempting to transition to the same phase, just update data if provided
            if data is not None:
                self._phase_data.update(data)
            print(f"[{datetime.utcnow().isoformat()}] Current phase ({self._current_phase.value}) maintained. Data updated.")

    def update_phase_data(self, key: str, value: Any):
        """
        Updates a specific piece of data within the current phase's data dictionary.

        Args:
            key: The key for the data item.
            value: The value to associate with the key.
        """
        self._phase_data[key] = value
        print(f"[{datetime.utcnow().isoformat()}] Phase '{self.current_phase.value}' data updated: {key} = {value}")

    def get_phase_info(self) -> Dict[str, Any]:
        """
        Returns a dictionary containing the current phase, start time, and associated data.
        """
        return {
            "phase": self.current_phase.value,
            "start_time_utc": self.phase_start_time.isoformat(),
            "data": self.phase_data
        }
    
    def __str__(self) -> str:
        return f"IPDA State Machine: Current Phase={self.current_phase.value}, Started={self.phase_start_time.isoformat()} UTC"

# Example Usage (for testing purposes, remove in production main.py)
if __name__ == "__main__":
    print("--- IPDA State Machine Example ---")
    sm = IPDAStateMachine()
    print(sm)

    # Simulate market progression
    print("\nSimulating: Market enters Consolidation (Asian Range)")
    sm.transition_to(MarketPhase.CONSOLIDATION, {"range_high": 1.0800, "range_low": 1.0750})
    print(sm.get_phase_info())

    print("\nSimulating: Manipulation (London Open Liquidity Raid)")
    sm.transition_to(MarketPhase.MANIPULATION, {"raid_target": "Asian_High", "false_break_level": 1.0805})
    print(sm.get_phase_info())
    sm.update_phase_data("rejection_candle_size", "large")
    print(sm.get_phase_info())


    print("\nSimulating: Price shows Displacement, entering Retracement for Entry")
    sm.transition_to(MarketPhase.RETRACEMENT, {"fvg_level": 1.0790, "order_block_level": 1.0785})
    print(sm.get_phase_info())

    print("\nSimulating: Entry confirmed, moving to Distribution (Trade execution)")
    sm.transition_to(MarketPhase.DISTRIBUTION, {"entry_price": 1.0788, "stop_loss": 1.0760, "take_profit": 1.0850})
    print(sm.get_phase_info())

    print("\nAttempting to transition to same phase (should just update data if provided)")
    sm.transition_to(MarketPhase.DISTRIBUTION, {"current_rr": "1:2"})
    print(sm.get_phase_info())
