import pandas as pd
from typing import Optional
from datetime import datetime # Added import

class BacktestDataStream:
    def __init__(self, historical_data: pd.DataFrame):
        self.historical_data = historical_data
        self.current_index = 0
        self.is_connected = False  # Always disconnected for backtesting

    def get_latest_candles(self, symbol: str, timeframe, count: int) -> pd.DataFrame:
        """
        Simulates fetching the latest candles.
        In backtesting, this provides a rolling window of historical data.
        """
        if self.current_index < len(self.historical_data):
            # Return a window of size 'count' ending at the current_index
            start_index = max(0, self.current_index - count + 1)
            window = self.historical_data.iloc[start_index:self.current_index + 1]
            return window
        else:
            # No more data
            return pd.DataFrame()

    def advance(self):
        """Advances the data stream by one candle."""
        if self.current_index < len(self.historical_data):
            self.current_index += 1

    def is_finished(self) -> bool:
        """Checks if the backtest data has been fully consumed."""
        return self.current_index >= len(self.historical_data)

    def shutdown(self):
        """No real connection to shut down in backtesting."""
        self.is_connected = False
        print("[BACKTEST DATA] Stream finished.")

    def get_all_candles_for_current_day(self, current_time: datetime) -> pd.DataFrame:
        """
        Returns all candles for the day of the given current_time.
        """
        if self.historical_data.empty:
            return pd.DataFrame()
        
        # Filter data for the current day
        current_day_data = self.historical_data[self.historical_data.index.date == current_time.date()]
        return current_day_data
