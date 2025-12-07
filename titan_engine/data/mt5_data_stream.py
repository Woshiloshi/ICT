import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
from typing import Optional, Dict


class MT5DataStream:
    def __init__(self, symbol: str = "EURUSD", timeframe=mt5.TIMEFRAME_M1, bars: int = 500):
        self.symbol = symbol
        self.timeframe = timeframe
        self.bars = bars
        self.is_connected = False
        self.last_rates = pd.DataFrame()

        print("[DATA] Initializing MT5 connection...")
        self.connect()

    def connect(self) -> bool:
        if not mt5.initialize():
            print(f"[DATA] Failed to connect to MT5 | Error: {mt5.last_error()}")
            return False

        if not mt5.symbol_select(self.symbol, True):
            print(f"[DATA] Symbol {self.symbol} not found")
            return False

        print(f"[DATA] Connected to MT5 | Symbol: {self.symbol} | TF: {self.timeframe}")
        self.is_connected = True
        self.refresh_data()
        return True

    def refresh_data(self) -> pd.DataFrame:
        """Fetch latest OHLC bars"""
        if not self.is_connected:
            return pd.DataFrame()

        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, self.bars)
        if rates is None or len(rates) == 0:
            print(f"[DATA] No data received for {self.symbol}")
            return self.last_rates

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        self.last_rates = df
        return df

    def get_latest_tick(self) -> Optional[Dict]:
        """Get real-time tick"""
        if not self.is_connected:
            return None
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "time": datetime.fromtimestamp(tick.time)
        }

    def get_current_price(self) -> float:
        tick = self.get_latest_tick()
        return tick["ask"] if tick else 0.0
    
    def get_latest_candles(self, symbol: str, timeframe, count: int) -> pd.DataFrame:
        """Fetches the latest 'count' candles for a given symbol and timeframe."""
        if not self.is_connected:
            return pd.DataFrame()
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            print(f"[DATA] No data received for {symbol} for latest {count} candles.")
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def shutdown(self):
        if self.is_connected:
            mt5.shutdown()
            self.is_connected = False
            print("[DATA] MT5 connection closed")

    def __del__(self):
        self.shutdown()