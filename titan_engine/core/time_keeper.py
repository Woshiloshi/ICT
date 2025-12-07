from datetime import datetime, time
import pytz


class TimeKeeper:
    def __init__(self, broker_timezone_str: str = "Europe/Helsinki"):
        self.broker_tz = pytz.timezone(broker_timezone_str)
        self.utc_now = datetime.utcnow().replace(tzinfo=pytz.UTC)
        self.broker_time = self.utc_now.astimezone(self.broker_tz).time()

        print(f"[TIME] Broker timezone: {broker_timezone_str} | Current broker time: {self.broker_time.strftime('%H:%M')}")

    def _current_broker_time(self) -> time:
        return datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(self.broker_tz).time()

    def is_london_open(self) -> bool:
        t = self._current_broker_time()
        return time(7, 0) <= t <= time(11, 0)

    def is_newyork_open(self) -> bool:
        t = self._current_broker_time()
        return time(13, 0) <= t <= time(16, 0)

    def is_silver_bullet(self) -> bool:
        t = self._current_broker_time()
        return time(10, 0) <= t <= time(11, 0)

    def is_asian_session(self) -> bool:
        t = self._current_broker_time()
        return t >= time(22, 0) or t <= time(7, 0)

    def is_killzone_active(self) -> bool:
        return self.is_london_open() or self.is_newyork_open()

    def get_current_session(self) -> str:
        if self.is_silver_bullet():
            return "SILVER BULLET (10-11 NY)"
        elif self.is_london_open():
            return "LONDON OPEN"
        elif self.is_newyork_open():
            return "NEW YORK AM"
        elif self.is_asian_session():
            return "ASIAN RANGE"
        else:
            return "DEAD ZONE"

    def should_trade(self) -> bool:
        """Only allow trades in killzones + Silver Bullet"""
        return self.is_killzone_active() or self.is_silver_bullet()

    def __str__(self):
        session = self.get_current_session()
        trade_ok = "YES" if self.should_trade() else "NO"
        return f"TIME → {session} | Trade Allowed: {trade_ok}"