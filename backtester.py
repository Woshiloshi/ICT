import pandas as pd
import MetaTrader5 as mt5
from typing import Dict, Any, Optional
from datetime import datetime

from titan_engine.core.time_keeper import TimeKeeper
from titan_engine.core.ipda_state_machine import IPDAStateMachine, MarketPhase
from titan_engine.core.market_scanner import MarketScanner, FairValueGap, OrderBlock, BreakerBlock, MitigationBlock
from titan_engine.core.macro_filters import NewsFilter
from titan_engine.data.mt5_data_stream import MT5DataStream
from titan_engine.execution.backtest_sniper import BacktestSniperModule
from titan_engine.execution.risk_warden import RiskWarden

# This is a self-contained version of the Bot, adapted for backtesting
class BacktestBot:
    def __init__(self, symbol: str, timeframe: int, risk_per_trade: float, sniper):
        self.symbol = symbol
        self.timeframe = timeframe
        self.sniper = sniper
        self.relevant_currencies = [symbol[:3], symbol[3:]] if len(symbol) >= 6 else []
        self.asian_range = None
        self.active_trades = sniper.open_positions # The sniper manages the state
        
        self.time_keeper = TimeKeeper()
        self.ipda_sm = IPDAStateMachine()
        # The risk warden needs a balance, but since the sniper tracks it, we can link them
        self.warden = RiskWarden(account_balance=sniper.balance, mt5_connection_active=True)
        self.news_filter = NewsFilter()
        self.recently_traded_timestamps = set()

    def tick(self, ohlc_data: pd.DataFrame):
        current_time_utc = ohlc_data.index[-1]
        ny_time = self.time_keeper.get_current_ny_time(current_time_utc.to_pydatetime())
        print(f"\nBacktest Tick at: {current_time_utc}, NY Time: {ny_time.strftime('%H:%M:%S')}")

        # In backtesting, we update the warden's balance from the sniper's balance
        self.warden.current_balance = self.sniper.balance

        # The sniper's check for SL/TP happens outside in the backtester loop
        
        current_session = self.time_keeper.get_current_session(ny_time)
        if current_session == "asian":
            self.handle_asian_session(ohlc_data)
        elif current_session == "london":
            self.handle_london_session(ohlc_data, ny_time)
        elif current_session == "new_york":
            self.handle_new_york_session(ohlc_data, ny_time)
        else:
            if ny_time.hour > 17: self.asian_range = None
    
    # All handler, find_and_execute, and is_news_approaching methods are copied from the main.py Bot
    # (with minor changes to remove live-specific prints)
    def handle_asian_session(self, ohlc_data: pd.DataFrame):
        self.ipda_sm.transition_to(MarketPhase.CONSOLIDATION)
        asian_session_times = self.time_keeper.SESSIONS['asian']
        self.asian_range = MarketScanner.get_session_range(ohlc_data.tz_localize('UTC').tz_convert('America/New_York'), asian_session_times['start'], asian_session_times['end'])
        if self.asian_range: print(f"Asian Range identified: High={self.asian_range['high']:.5f}, Low={self.asian_range['low']:.5f}")

    def handle_london_session(self, ohlc_data: pd.DataFrame, ny_time: datetime):
        if not self.asian_range: return
        if not self.time_keeper.is_in_killzone(ny_time, "london_open_am"): return
        if self.is_news_approaching(): return
        
        judas_swing = MarketScanner.find_judas_swing(ohlc_data, self.asian_range['high'], self.asian_range['low'])
        if judas_swing:
            mss = MarketScanner.find_market_structure_shift(ohlc_data, MarketScanner.find_swing_points(ohlc_data))
            if (judas_swing['type'] == 'bearish' and mss and mss['type'] == 'bearish') or \
               (judas_swing['type'] == 'bullish' and mss and mss['type'] == 'bullish'):
                self.find_and_execute_trade(ohlc_data, judas_swing['type'])

    def handle_new_york_session(self, ohlc_data: pd.DataFrame, ny_time: datetime):
        if not self.time_keeper.is_in_killzone(ny_time): return
        if self.is_news_approaching(): return
        mss = MarketScanner.find_market_structure_shift(ohlc_data, MarketScanner.find_swing_points(ohlc_data))
        if mss: self.find_and_execute_trade(ohlc_data, mss['type'])

    def find_and_execute_trade(self, ohlc_data: pd.DataFrame, trade_direction: str):
        order_blocks = MarketScanner.find_order_blocks(ohlc_data)
        if not order_blocks: return
        latest_ob = order_blocks[-1]
        if (trade_direction == 'bullish' and not latest_ob.is_bullish) or (trade_direction == 'bearish' and latest_ob.is_bullish): return
        if latest_ob.timestamp in self.recently_traded_timestamps: return
        ote_zone = MarketScanner.find_optimal_trade_entry_zone(ohlc_data, MarketScanner.find_swing_points(ohlc_data))
        if not ote_zone or ote_zone['direction'] != trade_direction: return
        entry_price = latest_ob.high if latest_ob.is_bullish else latest_ob.low
        if not (ote_zone['bottom'] <= entry_price <= ote_zone['top']):
            self.recently_traded_timestamps.add(latest_ob.timestamp)
            return
        
        stop_loss = latest_ob.low if latest_ob.is_bullish else latest_ob.high
        take_profit = entry_price + 2 * (entry_price - stop_loss) if latest_ob.is_bullish else entry_price - 2 * (stop_loss - entry_price)
        lot_size = self.warden.calculate_position_size(symbol=self.symbol, entry_price=entry_price, stop_loss_price=stop_loss)
        if lot_size:
            self.sniper.open_trade(symbol=self.symbol, trade_type=trade_direction, lot_size=lot_size, price=entry_price, stop_loss=stop_loss, take_profit=take_profit)
        self.recently_traded_timestamps.add(latest_ob.timestamp)

    def is_news_approaching(self) -> bool:
        approaching_event = self.news_filter.is_high_impact_news_approaching(relevant_currencies=self.relevant_currencies)
        if approaching_event:
            print(f"[!] MACRO FILTER: Halting analysis due to approaching news: {approaching_event}")
            return True
        return False

class Backtester:
    def __init__(self, symbol: str, timeframe: int, risk_per_trade: float, initial_balance: float):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data_stream = MT5DataStream()
        if not self.data_stream.is_connected: raise ConnectionError("Backtester requires MT5 connection.")
        self.backtest_sniper = BacktestSniperModule(initial_balance)
        self.bot = BacktestBot(symbol, timeframe, risk_per_trade, self.backtest_sniper)

    def run(self, num_candles: int):
        print(f"\n--- Starting Backtest for {self.symbol} over {num_candles} candles ---")
        historical_data = self.data_stream.get_bars(self.symbol, self.timeframe, num_candles)
        if historical_data is None or historical_data.empty:
            print("Could not fetch historical data. Aborting.")
            return
        
        for i in range(20, len(historical_data)): # Start with enough data for indicators
            current_view = historical_data.iloc[:i]
            current_candle = historical_data.iloc[i]
            self.backtest_sniper.update_and_check_positions(current_candle['high'], current_candle['low'], current_candle.name)
            self.bot.tick(ohlc_data=current_view)
        
        print("\n--- Backtest Finished ---")
        self.report()

    def report(self):
        print("\n--- Backtest Performance Report ---")
        history = self.backtest_sniper.history
        if not history:
            print("No trades were executed.")
            return
        total_trades, winning_trades = len(history), len([t for t in history if t['pnl'] > 0])
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in history)
        gains, losses = abs(sum(t['pnl'] for t in history if t['pnl'] > 0)), abs(sum(t['pnl'] for t in history if t['pnl'] < 0))
        profit_factor = gains / losses if losses > 0 else float('inf')
        print(f"Total Trades: {total_trades}, Wins: {winning_trades}, Losses: {total_trades - winning_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total P/L: ${total_pnl:,.2f} | Profit Factor: {profit_factor:.2f}")
        print(f"Final Balance: ${self.backtest_sniper.balance:,.2f}")

if __name__ == "__main__":
    try:
        backtester = Backtester("EURUSD", mt5.TIMEFRAME_M5, risk_per_trade=0.5, initial_balance=100000)
        backtester.run(num_candles=13000)
    except Exception as e:
        print(f"An error occurred during backtest: {e}")
    finally:
        mt5.shutdown()
        print("Backtester finished and MT5 connection shut down.")
