import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List

class MT5DataStream:
    """
    Manages the connection to the MetaTrader 5 terminal and provides methods for
    fetching and processing market data, including tick-to-OHLC normalization.
    """
    def __init__(self, account: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None):
        """
        Initializes the MT5 connection.

        Args:
            account (Optional[int]): The account number.
            password (Optional[str]): The password.
            server (Optional[str]): The server name.
        """
        self._is_connected: bool = False
        self._account_info = None

        if account and password and server:
            if not mt5.initialize(login=account, password=password, server=server):
                print(f"Failed to initialize MT5 with credentials: {mt5.last_error()}")
            else:
                self._is_connected = True
        else:
            if not mt5.initialize():
                print(f"Failed to initialize MT5 without credentials: {mt5.last_error()}")
            else:
                self._is_connected = True
        
        if self._is_connected:
            self._account_info = mt5.account_info()
            if self._account_info:
                print(f"MT5 Initialized. Connected to account #{self._account_info.login} on {self._account_info.server}")
            else:
                 print(f"MT5 Initialized, but failed to get account info: {mt5.last_error()}")
    
    @property
    def is_connected(self) -> bool:
        """Returns the connection status."""
        return self._is_connected

    def shutdown(self):
        """Shuts down the connection to the MT5 terminal."""
        if self._is_connected:
            mt5.shutdown()
            self._is_connected = False
            print("MT5 connection shut down.")

    def get_bars(self, symbol: str, timeframe: int, num_bars: int) -> Optional[pd.DataFrame]:
        """
        Fetches historical OHLC data for a given symbol and timeframe.

        Args:
            symbol (str): The financial instrument symbol (e.g., "EURUSD").
            timeframe (mt5.TIMEFRAME): The timeframe constant from MetaTrader5 library.
            num_bars (int): The number of bars to fetch.

        Returns:
            Optional[pd.DataFrame]: A pandas DataFrame with OHLC data, or None if failed.
                                    The DataFrame is indexed by datetime.
        """
        if not self.is_connected:
            print("Not connected to MT5.")
            return None
        
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
            if rates is None:
                print(f"Failed to get rates for {symbol}: {mt5.last_error()}")
                return None

            df = pd.DataFrame(rates)
            # MT5 returns time as a Unix timestamp, convert it to datetime
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            return df

        except Exception as e:
            print(f"An error occurred while fetching bars: {e}")
            return None

    @staticmethod
    def normalize_ticks_to_ohlc(ticks: List[tuple], timeframe_minutes: int) -> pd.DataFrame:
        """
        Aggregates a list of raw ticks into an OHLC pandas DataFrame for a specified timeframe.
        This is a static method as it's a pure data transformation function.

        Args:
            ticks (List[tuple]): A list of tick data tuples. 
                                 Expected format: (time, bid, ask, volume).
                                 'time' should be a datetime object.
            timeframe_minutes (int): The timeframe in minutes for aggregation (e.g., 1, 5, 15).

        Returns:
            pd.DataFrame: A DataFrame with OHLC data, indexed by datetime.
        """
        if not ticks:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'tick_volume'])

        df = pd.DataFrame(ticks, columns=['time', 'bid', 'ask', 'volume'])
        df['price'] = (df['bid'] + df['ask']) / 2  # Use mid-price for OHLC
        df.set_index('time', inplace=True)

        resample_rule = f'{timeframe_minutes}T'
        
        ohlc = df['price'].resample(resample_rule).ohlc()
        volume = df['volume'].resample(resample_rule).count().rename('tick_volume')
        
        return pd.concat([ohlc, volume], axis=1).dropna()


# Example Usage (for testing purposes)
if __name__ == "__main__":
    print("--- MT5DataStream Example ---")
    
    # Attempt to initialize connection (will likely fail if MT5 is not running)
    data_stream = MT5DataStream()

    if data_stream.is_connected:
        print("\n--- Fetching Live Data (if connected) ---")
        symbol = "EURUSD"
        
        # 1. Get last 10 M1 bars
        bars_m1 = data_stream.get_bars(symbol, mt5.TIMEFRAME_M1, 10)
        if bars_m1 is not None and not bars_m1.empty:
            print(f"Successfully fetched {len(bars_m1)} M1 bars for {symbol}:")
            print(bars_m1.tail(3))
        else:
            print(f"Could not fetch M1 bars for {symbol}.")

        data_stream.shutdown()
    else:
        print("\nSkipping live data fetching example as MT5 is not connected.")


    print("\n--- Testing Tick Normalization (offline) ---")
    # Simulate a stream of ticks for 5 minutes
    start_time = datetime.now().replace(second=0, microsecond=0)
    simulated_ticks = [
        (start_time + timedelta(seconds=10), 1.0801, 1.0802, 1),   # Min 1
        (start_time + timedelta(seconds=30), 1.0805, 1.0806, 1),
        (start_time + timedelta(seconds=55), 1.0800, 1.0801, 1),
        (start_time + timedelta(minutes=1, seconds=5), 1.0810, 1.0811, 1),   # Min 2
        (start_time + timedelta(minutes=1, seconds=20), 1.0812, 1.0813, 1),
        (start_time + timedelta(minutes=2, seconds=15), 1.0808, 1.0809, 1),   # Min 3
        (start_time + timedelta(minutes=3, seconds=40), 1.0815, 1.0816, 1),   # Min 4
        (start_time + timedelta(minutes=4, seconds=10), 1.0820, 1.0821, 1),   # Min 5
        (start_time + timedelta(minutes=4, seconds=50), 1.0818, 1.0819, 1),
    ]

    # Normalize to 1-minute OHLC
    ohlc_m1 = MT5DataStream.normalize_ticks_to_ohlc(simulated_ticks, 1)
    print("\nSimulated Ticks normalized to M1 OHLC:")
    print(ohlc_m1)

    # Normalize to 3-minute OHLC
    ohlc_m3 = MT5DataStream.normalize_ticks_to_ohlc(simulated_ticks, 3)
    print("\nSimulated Ticks normalized to M3 OHLC:")
    print(ohlc_m3)
