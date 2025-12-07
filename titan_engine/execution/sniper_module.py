import pandas as pd
import MetaTrader5 as mt5
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from titan_engine.core.ipda_state_machine import MarketPhase
from titan_engine.core.market_scanner import MarketScanner
from titan_engine.core.time_keeper import TimeKeeper # Import TimeKeeper

class SniperModule:
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.scanner = MarketScanner(lookback=100)
        self.last_entry_time = None # Initialize as None
        self.cooldown = timedelta(minutes=5)  # 5 min between trades
        self.time_keeper = TimeKeeper() # Instantiate TimeKeeper

        print(f"[SNIPER] Loaded | Demo Mode: {demo_mode}")

    def is_ote_zone(self, entry_price: float, ob_price: float, direction: str, current_price: float) -> bool:
        """Check if price is in 62–79% Optimal Trade Entry zone"""
        if direction == "bullish":
            low, high = ob_price, entry_price
        else:
            low, high = entry_price, ob_price

        fib_62 = low + (high - low) * 0.62
        fib_79 = low + (high - low) * 0.79

        return fib_62 <= current_price <= fib_79

    def execute_trade(self, symbol: str, volume: float, direction: str, sl: float, tp: float, limit_price: float, comment: str = "TITAN", **kwargs) -> Optional[Dict[str, Any]]:
        if self.demo_mode:
            trade = {
                "action": direction,
                "symbol": symbol,
                "volume": volume,
                "entry_price": limit_price, # Use limit_price as entry price
                "sl": sl,
                "tp": tp,
                "comment": comment,
                "timestamp": datetime.utcnow() # This will be overwritten by backtester's current_time
            }
            # print(f"[DEMO] {direction.upper()} {volume} {symbol} | Entry {limit_price:.5f} | SL {sl:.5f} | TP {tp:.5f} | {comment}")
            return trade

        # Existing live trade execution logic (no change)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL,
            "price": limit_price, # Use limit_price for live orders
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
            return None
        print(f"[LIVE] {direction.upper()} EXECUTED | Ticket: {result.order}")
        return {"ticket": result.order} # Return a minimal dict for live trades

    def hunt(self, df: pd.DataFrame, current_phase: MarketPhase) -> Optional[Dict[str, Any]]:
        current_time = df.index.max()
        current_price = df['close'].iloc[-1] # Use the latest close price for decisions

        self.time_keeper.update_current_time(current_time.to_pydatetime()) # Update TimeKeeper with current backtest time
        if not self.time_keeper.should_trade():
            print(f"[SNIPER] Outside trading hours ({self.time_keeper.get_current_session()}). Skipping hunt.")
            return None

        # Debugging: Check cooldown
        if self.last_entry_time is not None and current_time - self.last_entry_time < self.cooldown:
            return None # Anti-overtrade

        self.scanner.scan(df)
        fvgs = self.scanner.get_active_fvgs()
        obs = self.scanner.get_active_obs()
        
        # Check for Displacement
        if not self.scanner.detect_displacement(df):
            print("[SNIPER] No significant displacement detected. Skipping hunt.")
            return None

        # Check for Market Structure Shift
        mss_direction = self.scanner.detect_market_structure_shift(df)
        if mss_direction is None:
            print("[SNIPER] No Market Structure Shift detected. Skipping hunt.")
            return None

        # Check for Judas Swing during Manipulation phase and relevant killzones
        if current_phase == MarketPhase.MANIPULATION:
            if self.time_keeper.is_london_open() or self.time_keeper.is_newyork_am():
                judas_swing_direction = self.scanner.detect_judas_swing(df)
                if judas_swing_direction is None:
                    print("[SNIPER] No Judas Swing detected during Manipulation phase. Skipping hunt.")
                    return None
                # Optionally, ensure mss_direction aligns with judas_swing_direction
                # if mss_direction != judas_swing_direction:
                #     print("[SNIPER] MSS direction and Judas Swing direction do not align. Skipping hunt.")
                #     return None
            else:
                print(f"[SNIPER] Not in London Open or NY AM killzone during Manipulation phase. Skipping hunt.")
                return None
        else: # If not in Manipulation phase, we are not looking for Judas Swing
            print(f"[SNIPER] Not in Manipulation phase ({current_phase.value}). Skipping hunt.")
            return None

        # Debugging: Check if FVGs or OBs are found
        if not fvgs or not obs:
            print("[SNIPER] No active FVGs or OBs found. Skipping hunt.")
            return None
        
        for fvg in fvgs[:3]:  # Check last 3 FVGs
            for ob in obs:
                # Debugging: Check proximity
                if abs(fvg.index - ob.index) > timedelta(minutes=10 * 5):
                    continue  # Too far apart

                direction = fvg.direction
                limit_price = 0.0 # Initialize limit price

                if direction == "bullish":
                    # Entry: Limit Order placed at the Open of the FVG or the High of the Bullish Order Block.
                    # For a bullish setup, an FVG is typically a low to high gap. We want to enter at the low of this gap.
                    # An OB would be a high of the bearish candle before the up move.
                    if fvg and (not ob or fvg.low < ob.price): # Prioritize FVG if it's lower (for bullish)
                        limit_price = fvg.low
                    elif ob:
                        limit_price = ob.price # Assuming OB.price is the high of the bullish OB
                    else:
                        continue # Should not happen if fvgs or obs are not empty

                else: # bearish
                    # Entry: Limit Order placed at the Open of the FVG or the Low of the Bearish Order Block.
                    # For a bearish setup, an FVG is typically a high to low gap. We want to enter at the high of this gap.
                    # An OB would be a low of the bullish candle before the down move.
                    if fvg and (not ob or fvg.high > ob.price): # Prioritize FVG if it's higher (for bearish)
                        limit_price = fvg.high
                    elif ob:
                        limit_price = ob.price # Assuming OB.price is the low of the bearish OB
                    else:
                        continue # Should not happen if fvgs or obs are not empty

                # Debugging: Check OTE zone
                if not self.is_ote_zone(limit_price, ob.price, direction, current_price): # Note: OTE check uses current_price
                    continue

                # Stop Loss and Take Profit calculations (dynamic SL based on swing points)
                swing_points = self.scanner.get_last_swing_high_low(df)
                buffer = 0.0001 # 1 pip buffer

                if direction == "bullish":
                    if swing_points["low"] is None:
                        print("[SNIPER] No valid swing low found for bullish trade. Skipping hunt.")
                        continue
                    sl = swing_points["low"] - buffer
                    if sl >= limit_price: # Ensure SL is below entry for bullish trade
                        print("[SNIPER] Calculated SL is above entry for bullish trade. Skipping hunt.")
                        continue
                    tp = limit_price + abs(limit_price - sl) # 1:1 Risk/Reward
                else: # bearish
                    if swing_points["high"] is None:
                        print("[SNIPER] No valid swing high found for bearish trade. Skipping hunt.")
                        continue
                    sl = swing_points["high"] + buffer
                    if sl <= limit_price: # Ensure SL is above entry for bearish trade
                        print("[SNIPER] Calculated SL is below entry for bearish trade. Skipping hunt.")
                        continue
                    tp = limit_price - abs(limit_price - sl) # 1:1 Risk/Reward

                print(f"[SNIPER] CONFLUENCE FOUND → {direction.upper()} at OTE")
                trade = self.execute_trade("EURUSD", 0.1, direction, sl, tp, limit_price, "TITAN_FVG_OB")
                if trade:
                    self.last_entry_time = current_time
                    trade["timestamp"] = current_time # Set the timestamp of the trade
                    return trade # Return the trade dictionary
                return None