import datetime
import pytz
from typing import Optional

class TimeKeeper:
    """
    Manages and synchronizes time for Project TITAN, converting broker server time
    (assumed UTC/EET as per instructions) to "True Market Time" (America/New_York)
    and accounting for Daylight Savings.

    The system executes only during specific "Killzones" (London Open, New York AM/PM)
    and Macro windows. This module will provide utilities to check current time
    against these zones.
    """
    NY_TIMEZONE = pytz.timezone("America/New_York")
    
    # Define Killzones in True Market Time (America/New_York)
    # These are illustrative and can be expanded/made configurable
    KILLZONES = {
        "london_open_am": {"start": datetime.time(2, 0), "end": datetime.time(5, 0)}, # 2:00-5:00 AM NY
        "new_york_am": {"start": datetime.time(8, 30), "end": datetime.time(11, 0)}, # 8:30-11:00 AM NY
        "new_york_pm": {"start": datetime.time(13, 0), "end": datetime.time(16, 0)}, # 1:00-4:00 PM NY
        "silver_bullet": {"start": datetime.time(10, 0), "end": datetime.time(11, 0)} # 10:00-11:00 AM NY
    }

    # Define common non-trading hours
    NON_TRADING_HOURS = [
        {"start": datetime.time(12, 0), "end": datetime.time(13, 0)} # Lunch Hour 12:00-1:00 PM NY
    ]

    # Define Major Trading Sessions in True Market Time (America/New_York)
    SESSIONS = {
        # Using a common definition for the Asian Range build-up
        "asian": {"start": datetime.time(20, 0), "end": datetime.time(23, 59)},
        "london": {"start": datetime.time(2, 0), "end": datetime.time(5, 0)},
        "new_york": {"start": datetime.time(8, 0), "end": datetime.time(17, 0)}, # Covering AM and PM macros
    }

    def __init__(self, broker_timezone_str: str = "UTC"):
        """
        Initializes the TimeKeeper with the broker's timezone.

        Args:
            broker_timezone_str: A string representing the broker's timezone
                                 (e.g., "UTC", "Europe/Helsinki" for EET).
        """
        try:
            self.broker_timezone = pytz.timezone(broker_timezone_str)
        except pytz.UnknownTimeZoneError:
            raise ValueError(f"Unknown broker timezone: {broker_timezone_str}")
        print(f"TimeKeeper initialized. Broker timezone: {self.broker_timezone.tzname(datetime.datetime.now())}")

    def get_current_session(self, ny_time: datetime.datetime) -> Optional[str]:
        """
        Determines the current major trading session based on the provided NY time.

        Args:
            ny_time: A timezone-aware datetime object in America/New_York timezone.

        Returns:
            Optional[str]: The name of the current session ('asian', 'london', 'new_york') or None.
        """
        if str(ny_time.tzinfo) != str(self.NY_TIMEZONE):
            raise ValueError("ny_time must be a timezone-aware datetime in America/New_York.")
        
        current_time = ny_time.time()
        # Handle overnight Asian session
        if self.SESSIONS["asian"]["start"] <= current_time <= self.SESSIONS["asian"]["end"]:
            return "asian"

        for session_name, session_range in self.SESSIONS.items():
            if session_name == "asian": continue # Already handled
            if session_range["start"] <= current_time < session_range["end"]:
                return session_name
        return None


    def _convert_to_ny_time(self, dt_obj: datetime.datetime) -> datetime.datetime:
        """
        Converts a datetime object from its original timezone to America/New_York timezone.
        Assumes the input datetime is timezone-aware.

        Args:
            dt_obj: A timezone-aware datetime object.

        Returns:
            A datetime object localized to America/New_York timezone.
        """
        if dt_obj.tzinfo is None:
            raise ValueError("Input datetime object must be timezone-aware.")
        return dt_obj.astimezone(self.NY_TIMEZONE)

    def get_current_ny_time(self, broker_current_dt: Optional[datetime.datetime] = None) -> datetime.datetime:
        """
        Returns the current "True Market Time" in America/New_York timezone.
        If broker_current_dt is provided, it's used as the reference time,
        otherwise, the system's current UTC time is used.

        Args:
            broker_current_dt: Optional. The current datetime from the broker server,
                                expected to be timezone-aware (in broker_timezone_str).
                                If None, uses datetime.datetime.now(pytz.utc) as base.

        Returns:
            A timezone-aware datetime object representing the current time in America/New_York.
        """
        if broker_current_dt:
            # Ensure broker_current_dt is localized to its stated timezone
            if broker_current_dt.tzinfo is None:
                broker_current_dt = self.broker_timezone.localize(broker_current_dt)
            else:
                # If already timezone-aware, just ensure it's in the broker's expected timezone
                broker_current_dt = broker_current_dt.astimezone(self.broker_timezone)
            
            return self._convert_to_ny_time(broker_current_dt)
        else:
            # Fallback to current UTC time if no broker time is provided
            utc_now = datetime.datetime.now(pytz.utc)
            return self._convert_to_ny_time(utc_now)

    def is_in_killzone(self, ny_time: datetime.datetime, killzone_name: Optional[str] = None) -> bool:
        """
        Checks if the given New York time falls within any defined Killzone,
        or a specific Killzone if specified.

        Args:
            ny_time: A timezone-aware datetime object in America/New_York timezone.
            killzone_name: Optional. If provided, checks only this specific killzone.

        Returns:
            True if the time is within a Killzone (or the specified one), False otherwise.
        """
        if str(ny_time.tzinfo) != str(self.NY_TIMEZONE):
            raise ValueError("ny_time must be a timezone-aware datetime in America/New_York.")

        current_time = ny_time.time()

        if killzone_name:
            if killzone_name in self.KILLZONES:
                kz = self.KILLZONES[killzone_name]
                return kz["start"] <= current_time < kz["end"]
            else:
                print(f"Warning: Killzone '{killzone_name}' not defined.")
                return False
        else:
            for kz_name, kz_range in self.KILLZONES.items():
                if kz_range["start"] <= current_time < kz_range["end"]:
                    return True
            return False

    def is_in_non_trading_hours(self, ny_time: datetime.datetime) -> bool:
        """
        Checks if the given New York time falls within defined non-trading hours.
        (e.g., Lunch Hour)

        Args:
            ny_time: A timezone-aware datetime object in America/New_York timezone.

        Returns:
            True if the time is within non-trading hours, False otherwise.
        """
        if str(ny_time.tzinfo) != str(self.NY_TIMEZONE):
            raise ValueError("ny_time must be a timezone-aware datetime in America/New_York.")
        
        current_time = ny_time.time()
        for nt_range in self.NON_TRADING_HOURS:
            if nt_range["start"] <= current_time < nt_range["end"]:
                return True
        return False

# Example Usage (for testing purposes, remove in production main.py)
if __name__ == "__main__":
    time_keeper = TimeKeeper(broker_timezone_str="Europe/Helsinki") # Assuming EET for MT5

    # Simulate current broker time (e.g., from MT5)
    # Example: December 6, 2025, 15:30 EET (13:30 UTC)
    # Should convert to 08:30 AM NY Time (EDT/EST depending on date)
    # Note: Dec 6 2025 -> NY is EST (UTC-5)
    # 15:30 EET -> 13:30 UTC -> 08:30 NY EST
    
    print("\n--- Testing with simulated broker time (EET) ---")
    simulated_broker_dt = datetime.datetime(2025, 12, 6, 15, 30, 0)
    # Localize the simulated time to the broker's timezone
    eet_tz = pytz.timezone("Europe/Helsinki")
    simulated_broker_dt_aware = eet_tz.localize(simulated_broker_dt)

    ny_current_time = time_keeper.get_current_ny_time(simulated_broker_dt_aware)
    print(f"Simulated Broker Time (EET): {simulated_broker_dt_aware}")
    print(f"Converted NY Time: {ny_current_time}")
    print(f"Is in NY AM Killzone? {time_keeper.is_in_killzone(ny_current_time, 'new_york_am')}")
    print(f"Is in London Open Killzone? {time_keeper.is_in_killzone(ny_current_time, 'london_open_am')}")
    print(f"Is in Non-Trading Hours? {time_keeper.is_in_non_trading_hours(ny_current_time)}")

    print("\n--- Testing with current system UTC time ---")
    ny_current_time_system = time_keeper.get_current_ny_time()
    print(f"Current NY Time (from system UTC): {ny_current_time_system}")
    print(f"Is in NY AM Killzone? {time_keeper.is_in_killzone(ny_current_time_system, 'new_york_am')}")
    print(f"Is in London Open Killzone? {time_keeper.is_in_killzone(ny_current_time_system, 'london_open_am')}")
    print(f"Is in Non-Trading Hours? {time_keeper.is_in_non_trading_hours(ny_current_time_system)}")
