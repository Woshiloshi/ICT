from datetime import datetime, time
import pytz
from typing import Optional


class TimeKeeper:
    def __init__(self, broker_timezone_str: str = "America/New_York"): # Changed default to America/New_York
        self.broker_tz = pytz.timezone(broker_timezone_str)
        self.current_time_for_backtest: Optional[datetime] = None # New attribute for backtesting

        self.update_current_time() # Initial update

        print(f"[TIME] Broker timezone: {broker_timezone_str} | Current broker time: {self._current_broker_time().strftime('%H:%M')}")

    def update_current_time(self, dt: Optional[datetime] = None):
        """Updates the internal current_time, used for backtesting or live operation."""
        if dt:
            # Ensure the datetime is timezone-aware UTC before conversion
            if dt.tzinfo is None:
                self.current_time_for_backtest = pytz.UTC.localize(dt)
            else:
                self.current_time_for_backtest = dt.astimezone(pytz.UTC)
        else:
            self.current_time_for_backtest = datetime.utcnow().replace(tzinfo=pytz.UTC)

    def _current_broker_time(self) -> time:
        """Returns the current time in the broker's timezone."""
        if self.current_time_for_backtest:
            return self.current_time_for_backtest.astimezone(self.broker_tz).time()
        else:
            # Fallback for live, though update_current_time should always be called
            return datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(self.broker_tz).time()

    def is_london_open(self) -> bool:
        """London Open Killzone: 2:00 - 5:00 AM NY (doc.txt)"""
        t = self._current_broker_time()
        return time(2, 0) <= t <= time(5, 0)

    def is_newyork_am(self) -> bool:
        """New York AM Killzone: 8:30 - 11:00 AM NY (doc.txt)"""
        t = self._current_broker_time()
        return time(8, 30) <= t <= time(11, 0)

    def is_newyork_pm(self) -> bool:
        """New York PM Killzone: 14:00 - 16:00 PM NY (doc.txt)"""
        t = self._current_broker_time()
        return time(14, 0) <= t <= time(16, 0)

    def is_silver_bullet(self) -> bool:
        """Silver Bullet Killzone: 10:00 - 11:00 AM NY (doc.txt) - Part of NY AM"""
        t = self._current_broker_time()
        return time(10, 0) <= t <= time(11, 0)

    def is_asian_session_active(self) -> bool:
        """Asian Session: 19:00 - 00:00 NY (previous day) / 00:00 - 02:00 NY (current day)"""
        t = self._current_broker_time()
        # Asian session is 00:00-03:00 GMT, which is 19:00-22:00 NY previous day and 00:00-02:00 NY current day
        # From doc.txt: Asian Range 00:00-03:00 GMT; convert to NY time:
        # 00:00 GMT = 19:00 NY (previous day)
        # 03:00 GMT = 22:00 NY (previous day)
        # So Asian Range is roughly 19:00 (prev day) to 02:00 (current day) for "avoid trading"
        return time(19,0) <= t or t <= time(2,0) # Covers from 7 PM NY to 2 AM NY

    def is_killzone_active(self) -> bool:
        return self.is_london_open() or self.is_newyork_am() or self.is_newyork_pm()

    def get_current_session(self) -> str:
        if self.is_silver_bullet():
            return "SILVER BULLET (10-11 NY)"
        elif self.is_london_open():
            return "LONDON OPEN (2-5 NY)"
        elif self.is_newyork_am():
            return "NEW YORK AM (8:30-11 NY)"
        elif self.is_newyork_pm():
            return "NEW YORK PM (14-16 NY)"
        elif self.is_asian_session_active():
            return "ASIAN RANGE (19-02 NY - AVOID)"
        else:
            return "DEAD ZONE"

    def is_news_event_imminent(self) -> bool:
        """
        Placeholder for checking if a high-impact news event is scheduled soon.
        For now, it always returns False. In a real scenario, this would check
        an economic calendar.
        """
        # doc.txt: "IF High-Impact News (Red Folder) is scheduled in < 20 mins: Pause."
        # For backtesting, we'd need to pre-load news events. For now, always False.
        return False

    def should_trade(self) -> bool:
        """
        Determines if trading is allowed based on killzones, Asian session, and news events.
        Hard Block outside killzones, during Asian session, and if news is imminent.
        """
        if self.is_asian_session_active():
            return False
        
        if self.is_news_event_imminent(): # New check for news
            return False

        if self.is_killzone_active():
            return True
        
        return False

    def __str__(self):
        session = self.get_current_session()
        trade_ok = "YES" if self.should_trade() else "NO"
        return f"TIME → {session} | Trade Allowed: {trade_ok}"