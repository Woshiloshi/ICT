import MetaTrader5 as mt5
from typing import Optional

class RiskWarden:
    """
    Manages risk parameters, calculates position sizes, and enforces trading limits.
    """
    def __init__(
        self,
        account_balance: float,
        max_daily_loss_pct: float = 2.0,
        max_drawdown_pct: float = 10.0,
        default_risk_per_trade_pct: float = 1.0,
        mt5_connection_active: bool = False
    ):
        """
        Initializes the RiskWarden.

        Args:
            account_balance (float): The initial account balance.
            max_daily_loss_pct (float): Max % of balance allowed to be lost in a day.
            max_drawdown_pct (float): Max % of balance allowed for total drawdown.
            default_risk_per_trade_pct (float): The default % of balance to risk per trade.
            mt5_connection_active (bool): Flag indicating if there is an active MT5 connection.
        """
        self.initial_balance = account_balance
        self.current_balance = account_balance
        self.max_daily_loss = self.initial_balance * (max_daily_loss_pct / 100)
        self.max_drawdown = self.initial_balance * (max_drawdown_pct / 100)
        self.default_risk_per_trade_pct = default_risk_per_trade_pct
        
        self.today_pnl = 0.0
        self.high_water_mark = account_balance
        self.mt5_connection_active = mt5_connection_active

        print(f"RiskWarden Initialized. Balance: ${account_balance:,.2f}, Max Daily Loss: ${self.max_daily_loss:,.2f}")

    def can_trade(self) -> bool:
        """
        Checks if the system is allowed to place a new trade based on risk limits.
        """
        # Check daily loss limit
        if self.today_pnl <= -self.max_daily_loss:
            print(f"RiskWarden Alert: Daily loss limit of ${self.max_daily_loss:,.2f} reached. No more trading today.")
            return False
            
        # Check max drawdown limit
        drawdown = self.high_water_mark - self.current_balance
        if drawdown >= self.max_drawdown:
            print(f"RiskWarden Alert: Max drawdown limit of ${self.max_drawdown:,.2f} reached. Halting all trading.")
            return False
            
        return True

    def update_pnl(self, pnl: float):
        """Updates the PnL for the day and the current balance."""
        self.today_pnl += pnl
        self.current_balance += pnl
        if self.current_balance > self.high_water_mark:
            self.high_water_mark = self.current_balance
        print(f"RiskWarden: PnL updated by ${pnl:,.2f}. Today's PnL: ${self.today_pnl:,.2f}. New Balance: ${self.current_balance:,.2f}")


    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        risk_pct: Optional[float] = None
    ) -> Optional[float]:
        """
        Calculates the appropriate position size (volume/lot) for a trade.

        Args:
            symbol (str): The symbol for the trade (e.g., "EURUSD").
            entry_price (float): The intended entry price.
            stop_loss_price (float): The intended stop loss price.
            risk_pct (Optional[float]): The % of account balance to risk. 
                                         If None, uses the default.

        Returns:
            Optional[float]: The calculated position size, or None if it cannot be calculated.
        """
        if not self.mt5_connection_active:
            print("RiskWarden Error: Cannot calculate position size without an active MT5 connection.")
            return None
        
        if not self.can_trade():
             return None

        risk_to_use = risk_pct if risk_pct is not None else self.default_risk_per_trade_pct
        risk_amount = self.current_balance * (risk_to_use / 100)
        
        sl_pips = abs(entry_price - stop_loss_price)
        if sl_pips == 0:
            print("RiskWarden Error: Stop loss cannot be the same as entry price.")
            return None
            
        # Get symbol information from MT5
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"RiskWarden Error: Could not get info for symbol {symbol}. Is it enabled in Market Watch?")
            return None

        # Value of 1 lot movement by 1 point
        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        
        if tick_value == 0 or tick_size == 0:
            print(f"RiskWarden Error: Invalid tick value/size for {symbol}. Cannot calculate lot size.")
            return None

        # Total value of the stop loss per 1 lot
        sl_value_per_lot = (sl_pips / tick_size) * tick_value
        
        if sl_value_per_lot == 0:
            print("RiskWarden Error: SL value per lot is zero. Cannot calculate position size.")
            return None

        # Calculate the ideal lot size
        lot_size = risk_amount / sl_value_per_lot
        
        # Normalize the lot size according to the symbol's volume rules
        volume_step = symbol_info.volume_step
        min_volume = symbol_info.volume_min
        max_volume = symbol_info.volume_max

        # Round down to the nearest volume step
        lot_size = (lot_size // volume_step) * volume_step
        
        if lot_size < min_volume:
            print(f"RiskWarden Warning: Calculated lot size {lot_size} is below min volume {min_volume}. Cannot place trade.")
            return None
        if lot_size > max_volume:
            print(f"RiskWarden Warning: Calculated lot size {lot_size} exceeds max volume {max_volume}. Capping at max.")
            lot_size = max_volume

        print(f"RiskWarden: Calculated position size for {symbol}: {lot_size:.2f} lots (risking ${risk_amount:,.2f})")
        return round(lot_size, 2)


# Example Usage
if __name__ == "__main__":
    print("--- RiskWarden Example (Offline) ---")
    # Initializing without MT5 connection
    warden = RiskWarden(account_balance=100000, mt5_connection_active=False)
    
    # Try calculating position size (should fail gracefully)
    warden.calculate_position_size("EURUSD", 1.0800, 1.0780)

    # Simulate some trades
    print("\n--- Simulating PnL updates ---")
    warden.update_pnl(-1500) # Loss
    warden.update_pnl(2500)  # Win
    warden.update_pnl(-800)  # Loss
    
    # Check if trading is allowed
    print(f"\nIs trading allowed? {warden.can_trade()}")
    
    # Simulate hitting the daily loss limit
    warden.update_pnl(-2500)
    print(f"Is trading allowed? {warden.can_trade()}")
    
    # To test the live calculator, you would need to run this within a script
    # that has an active MT5 connection, like so:
    #
    # import MetaTrader5 as mt5
    # mt5.initialize()
    # warden_live = RiskWarden(account_balance=100000, mt5_connection_active=True)
    # lot_size = warden_live.calculate_position_size("EURUSD", 1.0800, 1.0780, risk_pct=0.5)
    # mt5.shutdown()
