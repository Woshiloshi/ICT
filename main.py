import MetaTrader5 as mt5
import pandas as pd
import pytz
from typing import Optional, Dict, Any, Union
from datetime import datetime, time, timedelta # Import time and timedelta

from titan_engine.data.mt5_data_stream import MT5DataStream
from titan_engine.data.backtest_data_stream import BacktestDataStream
from titan_engine.execution.sniper_module import SniperModule
from titan_engine.core.ipda_state_machine import IPDAStateMachine


class Bot:
    def __init__(self, symbol: str, timeframe, risk_per_trade: float, data_stream: Union[MT5DataStream, BacktestDataStream], sniper: SniperModule):
        self.symbol = symbol
        self.timeframe = timeframe
        self.risk_per_trade = risk_per_trade
        self.data_stream = data_stream
        self.sniper = sniper
        self.ipda = IPDAStateMachine() # Initialize the IPDA state machine

        self.asian_session_high: Optional[float] = None
        self.asian_session_low: Optional[float] = None
        self.asian_session_processed_date: Optional[datetime.date] = None

        print(f"[BOT] Initialized Bot for {self.symbol}")

    def run(self, interval: int = 0) -> Optional[Dict[str, Any]]:
        # In a live scenario, this method would fetch new data and run the trading logic.
        # For backtesting, data is fed by the backtester.
        
        # Get the latest data (window) from the data stream
        # This will work for both MT5DataStream and BacktestDataStream
        window = self.data_stream.get_latest_candles(self.symbol, self.timeframe, count=100)
        
        if not window.empty:
            # Current time based on the latest candle in the window
            current_time = window.index.max()
            # current_time is already UTC-aware due to fix in backtester.py

            # Process Asian Session liquidity once per day
            if self.sniper.time_keeper.is_asian_session_active() and current_time.date() != self.asian_session_processed_date:
                # Convert current_time to broker's timezone for accurate hour check
                broker_current_time = current_time.tz_convert(self.sniper.time_keeper.broker_tz)
                
                # Calculate start and end of Asian session for the relevant period
                # Asian Session is 19:00 NY (prev day) to 02:00 NY (current day)
                
                # Determine the date component for Asian session start/end in NY time
                asian_end_ny_date = broker_current_time.date()
                if broker_current_time.hour < 2: # Before 2 AM NY, so it's the Asian session ending today
                    asian_start_ny_date = broker_current_time.date() - timedelta(days=1)
                else: # 2 AM NY or later, so it's the Asian session of previous day that is relevant
                    asian_start_ny_date = broker_current_time.date()

                asian_start_time_ny = self.sniper.time_keeper.broker_tz.localize(datetime.combine(asian_start_ny_date, time(19, 0)))
                asian_end_time_ny = self.sniper.time_keeper.broker_tz.localize(datetime.combine(asian_end_ny_date + timedelta(days=1), time(2, 0)))

                # Convert to UTC for filtering historical_data (which is UTC-indexed)
                asian_start_time_utc = asian_start_time_ny.astimezone(pytz.UTC)
                asian_end_time_utc = asian_end_time_ny.astimezone(pytz.UTC)
                
                asian_session_window = self.data_stream.historical_data.loc[asian_start_time_utc:asian_end_time_utc]
                
                print(f"[BOT DEBUG] Current Time (UTC): {current_time}")
                print(f"[BOT DEBUG] Current Time (NY): {broker_current_time}")
                print(f"[BOT DEBUG] Asian Session UTC Range: {asian_start_time_utc} to {asian_end_time_utc}")
                print(f"[BOT DEBUG] Asian Session Window Empty: {asian_session_window.empty}")
                if not asian_session_window.empty:
                    print(f"[BOT DEBUG] Asian Session Window Head:\n{asian_session_window.head(2)}")
                    print(f"[BOT DEBUG] Asian Session Window Tail:\n{asian_session_window.tail(2)}")
                    is_range_bound_result = self.sniper.scanner.is_range_bound(asian_session_window)
                    print(f"[BOT DEBUG] Is Asian Session Range Bound: {is_range_bound_result}")
                    if is_range_bound_result:
                        liquidity_pools = self.sniper.scanner.get_liquidity_pools(asian_session_window)
                        print(f"[BOT DEBUG] Asian Session Liquidity Pools: {liquidity_pools}")
                        if liquidity_pools["highs"]:
                            self.asian_session_high = max(liquidity_pools["highs"])
                        if liquidity_pools["lows"]:
                            self.asian_session_low = min(liquidity_pools["lows"])
                        self.asian_session_processed_date = current_time.date() # Mark as processed for this day (UTC day)
                        print(f"[BOT] Asian Session Liquidity: High={self.asian_session_high}, Low={self.asian_session_low} for {self.asian_session_processed_date}")

            # Update the IPDA state machine with the latest data
            self.ipda.update(window)

            # Run the sniper module's hunting logic
            trade = self.sniper.hunt(window, self.ipda.current_phase)
            return trade
        return None