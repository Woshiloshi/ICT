import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from typing import Optional, Dict

# Import your live engine (same code as real trading!)
from main import Bot
from titan_engine.data.backtest_data_stream import BacktestDataStream
from titan_engine.execution.backtest_sniper import BacktestSniperModule


class Backtester:
    def __init__(self, symbol: str = "EURUSD", timeframe=mt5.TIMEFRAME_M5):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data = pd.DataFrame()

    def fetch_mt5_history(self):
        # Calculate dates for the last 3 months
        self.to_date = datetime.now()
        self.from_date = self.to_date - pd.Timedelta(days=90)
        
        print(f"[BACKTEST] Fetching {self.symbol} {self.timeframe} from {self.from_date.date()} → {self.to_date.date()}...")
        if not mt5.initialize():
            raise ConnectionError("MT5 not connected")

        rates = mt5.copy_rates_range(
            self.symbol,
            self.timeframe,
            self.from_date,
            self.to_date
        )
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            raise ValueError("No data returned from MT5")

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        self.data = df
        print(f"[BACKTEST] Loaded {len(df)} bars | {df.index[0].date()} → {df.index[-1].date()}")

    def run(self, initial_balance: float = 10000.0):
        if self.data.empty:
            self.fetch_mt5_history()

        # Use backtesting components
        backtest_stream = BacktestDataStream(self.data)
        backtest_sniper = BacktestSniperModule(initial_balance=initial_balance)
        
        bot = Bot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            risk_per_trade=0.5,
            data_stream=backtest_stream,
            sniper=backtest_sniper,  # Use the backtest sniper
            is_backtest=True
        )

        equity_curve = [initial_balance]

        print("[BACKTEST] Starting bar-by-bar replay...")
        # Main backtesting loop
        for i in range(1, len(self.data)):
            # Slice the data to simulate a real-time feed
            current_candle_df = self.data.iloc[i-1:i]
            
            # Extract the timestamp for the current candle
            current_timestamp = pd.to_datetime(current_candle_df.index[0])

            # Pass the historical candle and its timestamp to the bot
            bot.run(candle=current_candle_df, timestamp=current_timestamp)

            # Update portfolio (e.g., check for stop loss/take profit hits)
            backtest_sniper.update_and_check_positions(
                high=current_candle_df['high'].iloc[0],
                low=current_candle_df['low'].iloc[0],
                current_time=current_timestamp
            )
            
            equity_curve.append(backtest_sniper.equity)


        self.plot_results(equity_curve, initial_balance)

    def plot_results(self, equity_curve, initial_balance):
        plt.figure(figsize=(14, 7))
        plt.plot(equity_curve, label="Equity Curve", color="#00ff88", linewidth=2)
        plt.title(f"TITAN Backtest — {self.symbol} M5", fontsize=16)
        plt.xlabel("Bars")
        plt.ylabel("Account Balance ($)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.show()

        total_return = (equity_curve[-1] / initial_balance - 1) * 100
        max_dd = self.calculate_max_dd(equity_curve) * 100

        print(f"\nBACKTEST COMPLETE")
        print(f"   Final Equity: ${equity_curve[-1]:,.2f}")
        print(f"   Total Return: {total_return:+.2f}%")
        print(f"   Max Drawdown: {max_dd:.2f}%")

    def calculate_max_dd(self, equity_curve):
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / peak
        return drawdown.max()


# RUN IT
if __name__ == "__main__":
    tester = Backtester(
        symbol="EURUSD",
        timeframe=mt5.TIMEFRAME_M5,
    )
    tester.run(initial_balance=10000)