import pandas as pd
import MetaTrader5 as mt5
from typing import Optional, Dict, Any, List
from titan_engine.core.ipda_state_machine import MarketPhase
from titan_engine.core.market_scanner import MarketScanner

class SniperModule:
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.scanner = MarketScanner(lookback=100)
        self.last_entry_time = 0
        self.cooldown = 300  # 5 min between trades

        print(f"[SNIPER] Loaded | Demo Mode: {demo_mode}")

    def is_ote_zone(self, entry_price: float, ob_price: float, direction: str) -> bool:
        """Check if price is in 62–79% Optimal Trade Entry zone"""
        if direction == "bullish":
            low, high = ob_price, entry_price
        else:
            low, high = entry_price, ob_price

        fib_62 = low + (high - low) * 0.62
        fib_79 = low + (high - low) * 0.79

        current = mt5.symbol_info_tick("EURUSD").bid if direction == "bearish" else mt5.symbol_info_tick("EURUSD").ask

        return fib_62 <= current <= fib_79

    def send_order(self, symbol: str, volume: float, direction: str, sl: float, tp: float, comment: str = "TITAN"):
        if self.demo_mode:
            print(f"[DEMO] {direction.upper()} {volume} {symbol} | Entry ~{mt5.symbol_info_tick(symbol).ask:.5f} | SL {sl:.5f} | TP {tp:.5f} | {comment}")
            return True

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL,
            "price": mt5.symbol_info_tick(symbol).ask if direction == "bullish" else mt5.symbol_info_tick(symbol).bid,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 20231207,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[!] Order failed: {result.retcode}")
            return False
        print(f"[LIVE] {direction.upper()} EXECUTED | Ticket: {result.order}")
        return True

    def hunt(self, df: pd.DataFrame, current_phase: MarketPhase):
        if current_phase != MarketPhase.RETRACEMENT:
            return  # Only trade in retracement

        if time.time() - self.last_entry_time < self.cooldown:
            return  # Anti-overtrade

        self.scanner.scan(df)
        fvgs = self.scanner.get_active_fvgs()
        obs = self.scanner.get_active_obs()

        for fvg in fvgs[:3]:  # Check last 3 FVGs
            for ob in obs:
                if abs(fvg.index - ob.index) > 10:
                    continue  # Too far apart

                direction = fvg.direction
                entry_price = mt5.symbol_info_tick("EURUSD").ask if direction == "bullish" else mt5.symbol_info_tick("EURUSD").bid

                if not self.is_ote_zone(entry_price, ob.price, direction):
                    continue

                sl = ob.price - 0.0010 if direction == "bullish" else ob.price + 0.0010
                tp = entry_price + (entry_price - sl) * 3  # 1:3 RR

                print(f"[SNIPER] CONFLUENCE FOUND → {direction.upper()} at OTE")
                self.send_order("EURUSD", 0.1, direction, sl, tp, "TITAN_FVG_OB")
                self.last_entry_time = time.time()
                return