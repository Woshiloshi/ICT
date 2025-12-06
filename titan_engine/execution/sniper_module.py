import MetaTrader5 as mt5
from typing import Optional, Dict, Any

class SniperModule:
    """
    Handles the execution of trades (order placement, modification, closure)
    via the MetaTrader 5 terminal.
    """
    def __init__(self, mt5_connection_active: bool, demo_mode: bool = True):
        """
        Initializes the SniperModule.

        Args:
            mt5_connection_active (bool): Flag indicating if there is an active MT5 connection.
            demo_mode (bool): If True, will only print trade actions instead of executing them.
        """
        self.mt5_connection_active = mt5_connection_active
        self.demo_mode = demo_mode
        self.open_positions: Dict[int, Dict[str, Any]] = {} # {ticket_id: {...trade_details...}}
        self._next_mock_ticket = 1000 # For demo mode mock ticket generation
        print(f"SniperModule Initialized. Demo Mode: {'ON' if self.demo_mode else 'OFF'}")

    def get_open_positions(self) -> Dict[int, Dict[str, Any]]:
        """Returns a dictionary of currently tracked open positions."""
        return self.open_positions
        
    def open_trade(
        self,
        symbol: str,
        trade_type: str, # "buy" or "sell"
        lot_size: float,
        price: Optional[float] = None, # For market orders, this is None
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        slippage: int = 5,
        magic_number: int = 2025
    ) -> Optional[Dict[str, Any]]:
        """
        Places a new trade.

        Args:
            symbol (str): The symbol to trade.
            trade_type (str): "buy" or "sell".
            lot_size (float): The volume of the trade.
            price (Optional[float]): The entry price for pending orders. Market if None.
            stop_loss (Optional[float]): The stop loss price.
            take_profit (Optional[float]): The take profit price.
            slippage (int): Allowed deviation from the price for market orders.
            magic_number (int): A unique identifier for trades placed by this EA.

        Returns:
            A dictionary containing the result of the trade execution, or None if failed.
        """
        if not self.mt5_connection_active:
            print("SniperModule Error: Cannot open trade without an active MT5 connection.")
            return None

        # Determine trade type
        if trade_type.lower() == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            entry_price = mt5.symbol_info_tick(symbol).ask if price is None else price
        elif trade_type.lower() == "sell":
            order_type = mt5.ORDER_TYPE_SELL
            entry_price = mt5.symbol_info_tick(symbol).bid if price is None else price
        else:
            print(f"SniperModule Error: Invalid trade_type '{trade_type}'. Use 'buy' or 'sell'.")
            return None
        
        # Build the request dictionary
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": entry_price,
            "sl": stop_loss if stop_loss is not None else 0.0,
            "tp": take_profit if take_profit is not None else 0.0,
            "deviation": slippage,
            "magic": magic_number,
            "comment": "Project-TITAN-v1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC, # Immediate or Cancel
        }
        
        print("\n--- SniperModule: Preparing Trade ---")
        print(f"Symbol: {symbol}, Type: {trade_type}, Lot Size: {lot_size}")
        print(f"Entry: {entry_price}, SL: {stop_loss}, TP: {take_profit}")

        trade_details = {
            "ticket": None, # Will be set after execution
            "symbol": symbol,
            "type": order_type,
            "entry_price": entry_price,
            "sl": stop_loss,
            "tp": take_profit,
            "volume": lot_size, # Initial volume
            "volume_remaining": lot_size,
            "open_time": datetime.datetime.now()
        }

        if self.demo_mode:
            print("DEMO MODE: Trade request would be sent now, but execution is skipped.")
            trade_details["ticket"] = self._next_mock_ticket
            self._next_mock_ticket += 1
            self.open_positions[trade_details["ticket"]] = trade_details
            print(f"DEMO MODE: Tracked open position with mock ticket {trade_details['ticket']}")
            # Simulate a successful result for demonstration purposes
            return {"retcode": 0, "comment": "Executed in demo mode", "request": request, "ticket": trade_details["ticket"]}

        # --- LIVE EXECUTION ---
        print("LIVE MODE: Sending trade request...")
        try:
            result = mt5.order_send(request)
            if result is None:
                print(f"SniperModule Error: order_send failed, error code: {mt5.last_error()}")
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"SniperModule Warning: Order Send failed. retcode={result.retcode}, comment: {result.comment}")
            else:
                print(f"SniperModule Success: Order executed successfully. Deal: {result.deal}, Order: {result.order}")
                # Track the live position
                trade_details["ticket"] = result.order
                self.open_positions[trade_details["ticket"]] = trade_details
                print(f"LIVE MODE: Tracked open position with ticket {trade_details['ticket']}")
            
            return result._asdict()

        except Exception as e:
            print(f"An exception occurred during order execution: {e}")
            return None

    def close_partial_trade(self, ticket_id: int, volume_to_close: float) -> bool:
        """
        Closes a specified volume of an open position.

        Args:
            ticket_id (int): The ticket ID of the position to partially close.
            volume_to_close (float): The volume to close from the position.

        Returns:
            bool: True if the partial closure was successful (or simulated), False otherwise.
        """
        if ticket_id not in self.open_positions:
            print(f"SniperModule Error: Position with ticket ID {ticket_id} not found.")
            return False

        position = self.open_positions[ticket_id]

        if volume_to_close <= 0 or volume_to_close > position["volume_remaining"]:
            print(f"SniperModule Error: Invalid volume {volume_to_close} to close for position {ticket_id}.")
            return False

        print(f"\n--- SniperModule: Preparing Partial Close for Ticket {ticket_id} ---")
        print(f"Symbol: {position['symbol']}, Volume to Close: {volume_to_close}")

        if self.demo_mode:
            print("DEMO MODE: Partial close request would be sent now, but execution is skipped.")
            position["volume_remaining"] -= volume_to_close
            if position["volume_remaining"] <= 0:
                del self.open_positions[ticket_id]
                print(f"DEMO MODE: Position {ticket_id} fully closed.")
            else:
                print(f"DEMO MODE: Position {ticket_id} partially closed. Remaining volume: {position['volume_remaining']}")
            return True

        # --- LIVE PARTIAL CLOSURE (Simplified) ---
        # A real implementation would involve constructing a partial close request
        # using mt5.TRADE_ACTION_DEAL and specifying the position ticket.
        print("LIVE MODE: Sending partial close request...")
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket_id,
            "volume": volume_to_close,
            "symbol": position["symbol"],
            "type": mt5.ORDER_TYPE_SELL if position["type"] == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "deviation": 5, # Slippage
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        try:
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"SniperModule Warning: Partial close failed for {ticket_id}. retcode={result.retcode}, comment: {result.comment}")
                return False
            else:
                position["volume_remaining"] -= volume_to_close
                if position["volume_remaining"] <= 0:
                    del self.open_positions[ticket_id]
                    print(f"LIVE MODE: Position {ticket_id} fully closed.")
                else:
                    print(f"LIVE MODE: Position {ticket_id} partially closed. Remaining volume: {position['volume_remaining']}")
                return True
        except Exception as e:
            print(f"An exception occurred during partial close: {e}")
            return False

    def modify_trade_sl(self, ticket_id: int, new_stop_loss: float) -> bool:
        """
        Modifies the stop loss for an open position.

        Args:
            ticket_id (int): The ticket ID of the position to modify.
            new_stop_loss (float): The new stop loss price.

        Returns:
            bool: True if the modification was successful (or simulated), False otherwise.
        """
        if ticket_id not in self.open_positions:
            print(f"SniperModule Error: Position with ticket ID {ticket_id} not found.")
            return False

        position = self.open_positions[ticket_id]

        print(f"\n--- SniperModule: Preparing SL Modification for Ticket {ticket_id} ---")
        print(f"Symbol: {position['symbol']}, New SL: {new_stop_loss:.5f}")

        if self.demo_mode:
            print("DEMO MODE: SL modification request would be sent now, but execution is skipped.")
            position['sl'] = new_stop_loss
            return True

        # --- LIVE SL MODIFICATION ---
        print("LIVE MODE: Sending SL modification request...")
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket_id,
            "sl": new_stop_loss,
            "tp": position['tp'], # TP must be specified, so we use the existing one
        }
        try:
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"SniperModule Warning: SL modification failed for {ticket_id}. retcode={result.retcode}, comment: {result.comment}")
                return False
            else:
                position['sl'] = new_stop_loss
                print(f"LIVE MODE: Position {ticket_id} SL successfully modified.")
                return True
        except Exception as e:
            print(f"An exception occurred during SL modification: {e}")
            return False




# Example Usage
if __name__ == "__main__":
    print("--- SniperModule Example (Offline) ---")
    
    # Initialize without MT5 connection, in demo mode
    sniper = SniperModule(mt5_connection_active=False, demo_mode=True)
    
    # Try to open a trade (should fail gracefully)
    sniper.open_trade(
        symbol="EURUSD",
        trade_type="buy",
        lot_size=0.1,
        price=1.0800,
        stop_loss=1.0780,
        take_profit=1.0850
    )
    
    # To test the live execution, you would need to run this within a script
    # that has an active MT5 connection, like so:
    #
    # import MetaTrader5 as mt5
    # mt5.initialize(account=..., password=..., server=...)
    # sniper_live = SniperModule(mt5_connection_active=True, demo_mode=False)
    # result = sniper_live.open_trade(...)
    # mt5.shutdown()
