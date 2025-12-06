import time
import datetime
import pandas as pd
import MetaTrader5 as mt5

# Core engine components
from titan_engine.core.time_keeper import TimeKeeper
from titan_engine.core.ipda_state_machine import IPDAStateMachine, MarketPhase
from titan_engine.core.market_scanner import MarketScanner, FairValueGap, OrderBlock, BreakerBlock, MitigationBlock
from titan_engine.core.macro_filters import NewsFilter

# Data layer
from titan_engine.data.mt5_data_stream import MT5DataStream

# Execution layer
from titan_engine.execution.risk_warden import RiskWarden
from titan_engine.execution.sniper_module import SniperModule

class Bot:
    """
    The main class for the TITAN trading bot.
    Manages all components and contains the main event loop.
    """
    def __init__(self, symbol: str, timeframe: int, risk_per_trade: float, data_stream, sniper):
        self.symbol = symbol
        self.timeframe = timeframe
        self.risk_per_trade = risk_per_trade
        self.relevant_currencies = [symbol[:3], symbol[3:]] if len(symbol) >= 6 else []
        self.asian_range = None
        self.active_trades: Dict[int, Dict[str, Any]] = {}

        print("Initializing bot components...")
        self.data_stream = data_stream
        self.sniper = sniper
        
        if not self.data_stream.is_connected:
            raise ConnectionError("Data stream is not connected. Cannot start the bot.")

        account_info = mt5.account_info()
        if not account_info:
            raise ConnectionError("Failed to get MT5 account info.")
            
        self.time_keeper = TimeKeeper(broker_timezone_str="Europe/Helsinki")
        self.ipda_sm = IPDAStateMachine()
        self.warden = RiskWarden(account_balance=account_info.balance, mt5_connection_active=True)
        self.news_filter = NewsFilter()
        
        self.recently_traded_timestamps = set()

    def run(self, tick_interval_seconds: int = 10):
# ... (rest of the Bot class is the same) ...

def main():
    """
    Main entry point for Project TITAN live trading mode.
    """
    print("=" * 50)
    print("Project TITAN: ICT Narrative Engine - Live Loop Initializing...")
    print("Press Ctrl+C to stop the bot.")
    print("=" * 50)

    data_stream = None
    try:
        data_stream = MT5DataStream()
        sniper = SniperModule(mt5_connection_active=data_stream.is_connected, demo_mode=True)
        
        bot = Bot(
            symbol="EURUSD",
            timeframe=mt5.TIMEFRAME_M5,
            risk_per_trade=0.5,
            data_stream=data_stream,
            sniper=sniper
        )
        bot.run()
    except ConnectionError as e:
        print(f"\nFATAL: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        if data_stream and data_stream.is_connected:
            print("\nShutting down MT5 connection from main.")
            data_stream.shutdown()
