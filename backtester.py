import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from typing import Dict, Any

# Import your live engine
from main import Bot
from titan_engine.data.mt5_data_stream import MT5DataStream
from titan_engine.data.backtest_data_stream import BacktestDataStream # Import BacktestDataStream
from titan_engine.execution.sniper_module import SniperModule


class Backtester:
    def __init__(self, symbol: str = "EURUSD", timeframe=mt5.TIMEFRAME_M1, days: int = 1, initial_balance: float = 10000.0, max_daily_loss_percent: float = 2.0, max_drawdown_percent: float = 5.0):
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.data = pd.DataFrame()
        self.open_trades = []
        self.closed_trades = []
        self.current_balance = initial_balance
        self.equity_curve = [initial_balance] # Initialize with initial balance

        # Risk Management attributes
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_drawdown_percent = max_drawdown_percent
        self.daily_high_equity = initial_balance
        self.start_of_day_balance = initial_balance
        self.trading_halted_for_day = False

    def fetch_data(self):
        # Explicitly set from_date and to_date for 2025-12-05 to ensure data availability
        from_date = datetime(2025, 12, 5, 0, 0, 0)
        to_date = datetime(2025, 12, 5, 23, 59, 59)

        print(f"[BACKTEST] Fetching {self.symbol} M1 from {from_date.date()} → {to_date.date()}...")
        if not mt5.initialize():
            raise ConnectionError("MT5 failed")

        rates = mt5.copy_rates_range(self.symbol, self.timeframe, from_date, to_date)
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            raise ValueError("No data")

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        # Make the index timezone-aware (UTC)
        df.index = df.index.tz_localize('UTC')
        self.data = df
        print(f"[BACKTEST] Loaded {len(df)} bars")

    def _calculate_pnl(self, trade: Dict[str, Any], current_price: float) -> float:
        """Calculates PnL for a single trade."""
        if trade["action"] == "bullish": # Buy trade
            pips = (current_price - trade["entry_price"]) / 0.0001
        else: # Sell trade
            pips = (trade["entry_price"] - current_price) / 0.0001
        
        # Assuming 1 pip = $10 for 0.1 lot for simplicity (need proper contract size/pip value for actual)
        return pips * 10 * (trade["volume"] / 0.1) 

    def run(self): # Removed initial_balance parameter
        if self.data.empty:
            self.fetch_data()

        # Initialize BacktestDataStream
        backtest_stream = BacktestDataStream(self.data)
        sniper = SniperModule(demo_mode=True)

        bot = Bot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            risk_per_trade=0.5,
            # Pass the backtest_stream instead of MT5DataStream
            data_stream=backtest_stream, 
            sniper=sniper
        )

        print("[BACKTEST] Starting bar-by-bar replay...")
        print(f"[BACKTEST] Total historical data bars: {len(self.data)}")

        # Initialize daily risk tracking (for single day backtest, this is global)
        self.start_of_day_balance = self.current_balance
        self.daily_high_equity = self.current_balance
        self.trading_halted_for_day = False

        # Loop through the backtest data
        while not backtest_stream.is_finished():
            if self.trading_halted_for_day:
                print(f"[RISK] Trading halted for the day due to risk limits at {window.index.max()}.")
                break
            
            window = backtest_stream.get_latest_candles(self.symbol, self.timeframe, count=100) # Get a window of 100 bars

            if not window.empty:
                current_time = window.index.max()
                current_price = window['close'].iloc[-1]

                # Mitigate FVGs and OBs based on current price
                for fvg in bot.sniper.scanner.fvgs:
                    fvg.is_mitigated(current_price)
                for ob in bot.sniper.scanner.order_blocks:
                    ob.is_mitigated(current_price)

                # Feed data to bot and get potential trade signal
                trade_signal = bot.run(interval=0)

                # Process new trade signal
                if trade_signal:
                    trade_signal["entry_time"] = current_time
                    trade_signal["pnl"] = 0.0 # Initialize PnL
                    self.open_trades.append(trade_signal)
                    print(f"[BACKTEST] New Trade Opened: {trade_signal['action']} at {trade_signal['entry_price']:.5f} at {current_time}")

                # Manage existing open trades
                floating_pnl = 0.0
                trades_to_close = []
                for trade in self.open_trades:
                    pnl = self._calculate_pnl(trade, current_price)
                    trade["pnl"] = pnl # Update floating PnL for the trade
                    floating_pnl += pnl

                    # Check for SL/TP
                    if trade["action"] == "bullish": # Buy trade
                        if current_price <= trade["sl"] or current_price >= trade["tp"]:
                            trades_to_close.append(trade)
                    else: # Sell trade
                        if current_price >= trade["sl"] or current_price <= trade["tp"]:
                            trades_to_close.append(trade)
                
                # Close trades that hit SL/TP
                for trade in trades_to_close:
                    self.open_trades.remove(trade)
                    trade["exit_time"] = current_time
                    self.current_balance += trade["pnl"] # Add final PnL to balance
                    self.closed_trades.append(trade)
                    print(f"[BACKTEST] Trade Closed: {trade['action']} PnL: {trade['pnl']:.2f} at {current_time}")

                # Record equity (balance + floating PnL)
                current_equity = self.current_balance + floating_pnl
                self.equity_curve.append(current_equity)

                # Update daily high equity for drawdown calculation
                self.daily_high_equity = max(self.daily_high_equity, current_equity)

                # Check for Max Daily Loss
                daily_loss = ((self.start_of_day_balance - current_equity) / self.start_of_day_balance) * 100
                if daily_loss > self.max_daily_loss_percent:
                    self.trading_halted_for_day = True
                    print(f"[RISK] Max Daily Loss ({self.max_daily_loss_percent:.2f}%) breached: {daily_loss:.2f}% at {current_time}.")
                
                # Check for Max Drawdown
                drawdown = ((self.daily_high_equity - current_equity) / self.daily_high_equity) * 100
                if drawdown > self.max_drawdown_percent:
                    self.trading_halted_for_day = True
                    print(f"[RISK] Max Drawdown ({self.max_drawdown_percent:.2f}%) breached: {drawdown:.2f}% at {current_time}.")
            
            backtest_stream.advance() # Advance the stream by one candle
        self.plot_results()

    def plot_results(self):
        plt.figure(figsize=(15, 8))
        plt.plot(self.equity_curve, label="Equity Curve", color="#00ff88", linewidth=2.5)
        plt.title(f"TITAN Backtest — {self.symbol} M1 | {self.days} Days", fontsize=18)
        plt.xlabel("Bars")
        plt.ylabel("Balance ($)")
        plt.legend(fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

        total_return = (self.equity_curve[-1] / self.equity_curve[0] - 1) * 100 # Use initial equity from curve
        max_dd = self.calculate_max_dd() * 100

        print(f"\nTITAN BACKTEST COMPLETE")
        print(f"   Final Balance: ${self.equity_curve[-1]:,.2f}")
        print(f"   Total Return:  {total_return:+.2f}%")
        print(f"   Max Drawdown:  {max_dd:.2f}%")
        print(f"   Total Trades:  {len(self.closed_trades)}")

    def calculate_max_dd(self):
        peak = np.maximum.accumulate(self.equity_curve)
        drawdown = (peak - self.equity_curve) / peak
        return drawdown.max()


if __name__ == "__main__":
    tester = Backtester(symbol="EURUSD", days=1, initial_balance=10000.0)
    tester.run()