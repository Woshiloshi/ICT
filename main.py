import time
from typing import Dict, Any, Optional
import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

# Core
from titan_engine.core.time_keeper import TimeKeeper
from titan_engine.core.ipda_state_machine import IPDAStateMachine, MarketPhase
from titan_engine.core.macro_filters import NewsFilter
from titan_engine.core.market_scanner import MarketScanner

# Data
from titan_engine.data.mt5_data_stream import MT5DataStream
from titan_engine.data.backtest_data_stream import BacktestDataStream

# Execution
from titan_engine.execution.risk_warden import RiskWarden
from titan_engine.execution.sniper_module import SniperModule


class Bot:
    def __init__(self, symbol: str, timeframe: int, risk_per_trade: float, data_stream, sniper, is_backtest: bool = False):
        self.symbol = symbol
        self.timeframe = timeframe
        self.risk_per_trade = risk_per_trade
        self.active_trades: Dict[int, Dict[str, Any]] = {}
        self.is_backtest = is_backtest

        print("[+] Initializing TITAN components...")
        self.data_stream = data_stream
        self.sniper = sniper

        # Differentiate between live and backtest
        if self.is_backtest:
            # Backtesting mode, no MT5 connection
            balance = self.sniper.balance
            print("[+] TITAN initialized in Backtest Mode.")
        else:
            # Live trading mode
            if not self.data_stream.is_connected:
                raise ConnectionError("MT5 connection failed")
            account = mt5.account_info()
            if not account:
                raise ConnectionError("Cannot read account info")
            balance = account.balance
            print(f"[+] TITAN initialized in Live Mode. Balance: ${balance:,.2f}")

        self.time_keeper = TimeKeeper(broker_timezone_str="Europe/Helsinki")
        self.ipda = IPDAStateMachine()
        self.market_scanner = MarketScanner()
        self.warden = RiskWarden(account_balance=balance)
        self.news_filter = NewsFilter()

    def run(self, interval: int = 60, candle: Optional[pd.DataFrame] = None, timestamp: Optional[datetime] = None):
        """
        Main bot loop. Handles both live trading and backtesting.
        """
        if self.is_backtest:
            if candle is None:
                raise ValueError("Candle data must be provided for backtesting.")
            # The backtester will feed data one candle at a time
            self._process_candles(candle, timestamp)
        else:
            # Live trading loop
            while True:
                df = self.data_stream.get_latest_candles(self.symbol, self.timeframe, 100)
                self._process_candles(df, datetime.utcnow())
                time.sleep(interval)
    
    def _process_candles(self, df: pd.DataFrame, timestamp: Optional[datetime] = None):
        """Shared logic for processing a dataframe of candles."""
        # 1. Update IPDA State Machine
        self.ipda.update(df, timestamp=timestamp)
        phase = self.ipda.current_phase.value
        print(f"[IPDA] Current Phase → {phase}")

        # 2. Scan for PD Arrays
        self.market_scanner.scan(df)
        fvgs = self.market_scanner.get_active_fvgs()
        obs = self.market_scanner.get_active_obs()
        
        pd_arrays = []
        for fvg in fvgs:
            pd_arrays.append({
                'type': 'fair_value_gap',
                'direction': fvg.direction,
                'price_level': (fvg.low + fvg.high) / 2 # Midpoint for display
            })
        for ob in obs:
            pd_arrays.append({
                'type': 'order_block',
                'direction': ob.direction,
                'price_level': ob.price
            })

        # 3. Execute Trades based on Confluence
        if self.ipda.current_phase == MarketPhase.RETRACEMENT and pd_arrays:
            # Simple cooldown to avoid over-trading
            if time.time() - self.sniper.last_entry_time < self.sniper.cooldown:
                return

            fvgs_for_trade = [pda for pda in pd_arrays if pda['type'] == 'fair_value_gap']
            obs_for_trade = [pda for pda in pd_arrays if pda['type'] == 'order_block']

            if fvgs_for_trade and obs_for_trade:
                # Simple confluence: use the most recent FVG and OB
                fvg = fvgs_for_trade[0]
                ob = obs_for_trade[0]
                
                # Ensure they are for the same direction
                if fvg['direction'] == ob['direction']:
                    direction = fvg['direction']
                    entry_price = fvg['price_level']
                    sl_price = ob['price_level']
                    
                    # Define SL and TP (e.g., SL at OB price, TP at 1:2 RR)
                    if direction == 'bullish':
                        stop_loss = sl_price - 0.00050 # A small buffer
                        take_profit = entry_price + (entry_price - stop_loss) * 2
                    else: # Bearish
                        stop_loss = sl_price + 0.00050 # A small buffer
                        take_profit = entry_price - (stop_loss - entry_price) * 2

                    print(f"[SNIPER] Confluence Found: {direction.upper()} FVG + OB. Evaluating entry...")
                    
                    self.sniper.execute_trade(
                        symbol=self.symbol,
                        direction=direction,
                        volume=0.1, # Example lot size
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
                    self.sniper.last_entry_time = time.time()



def main():
    print("=" * 70)
    print("          PROJECT TITAN — ICT NARRATIVE ENGINE")
    print("                  LIVE TRADING MODE v1.0")
    print("=" * 70)

    data_stream = None
    try:
        data_stream = MT5DataStream()
        sniper = SniperModule(demo_mode=True)

        bot = Bot(
            symbol="EURUSD",
            timeframe=mt5.TIMEFRAME_M5,
            risk_per_trade=0.5,
            data_stream=data_stream,
            sniper=sniper,
            is_backtest=False
        )
        bot.run(interval=10)

    except Exception as e:
        print(f"FATAL: {e}")
    finally:
        if data_stream and data_stream.is_connected:
            print("\nShutting down MT5...")
            data_stream.shutdown()
            mt5.shutdown()
        print("TITAN offline.")



if __name__ == "__main__":
    main()