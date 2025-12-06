from typing import Optional, Dict, Any
from datetime import datetime

class BacktestSniperModule:
    """
    A simulated version of the SniperModule for backtesting purposes.
    It does not connect to MT5 but simulates trade execution and tracks P/L.
    """
    def __init__(self, initial_balance: float):
        self.balance = initial_balance
        self.equity = initial_balance
        self.open_positions: Dict[int, Dict[str, Any]] = {}
        self._next_ticket = 1
        self.history = [] # To store closed trades
        print(f"BacktestSniperModule Initialized. Initial Balance: ${initial_balance:,.2f}")

    def open_trade(
        self,
        symbol: str,
        trade_type: str,
        lot_size: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        **kwargs # Ignore other live trading args
    ) -> Optional[Dict[str, Any]]:
        
        trade_details = {
            "ticket": self._next_ticket,
            "symbol": symbol,
            "type": trade_type,
            "entry_price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "volume": lot_size,
            "open_time": None, # Will be set by the backtester loop
            "pnl": 0.0,
        }
        self.open_positions[self._next_ticket] = trade_details
        print(f"Backtest: Opened {trade_type} trade {self._next_ticket} for {symbol} @ {price:.5f}")
        self._next_ticket += 1
        return {"retcode": 0, "ticket": trade_details["ticket"]}

    def close_trade(self, ticket_id: int, close_price: float, close_time: datetime):
        """
        Simulates closing a trade and calculates the P/L.
        """
        if ticket_id not in self.open_positions:
            return

        trade = self.open_positions.pop(ticket_id)
        
        pnl = 0
        pip_diff = 0
        if trade['type'] == 'buy':
            pip_diff = close_price - trade['entry_price']
        else: # sell
            pip_diff = trade['entry_price'] - close_price
            
        # This is a simplified P/L calculation assuming 1 lot = 100,000 units
        # and for XXX/USD pairs, 1 pip move = $10 per lot.
        # A proper implementation would use contract size and tick value.
        pnl = (pip_diff * 10000) * 10 * trade['volume']

        self.balance += pnl
        self.equity = self.balance # In this simple model, equity = balance when no trades are open
        trade['pnl'] = pnl
        trade['close_price'] = close_price
        trade['close_time'] = close_time
        self.history.append(trade)
        print(f"Backtest: Closed {trade['type']} trade {ticket_id} for {trade['symbol']} @ {close_price:.5f}. P/L: ${pnl:,.2f}")

    def update_and_check_positions(self, high: float, low: float, current_time: datetime):
        """
        The backtester loop calls this on each candle to check for SL/TP hits.
        """
        closed_tickets = []
        for ticket, trade in self.open_positions.items():
            if trade['open_time'] is None:
                trade['open_time'] = current_time

            if trade['type'] == 'buy':
                # Check for SL hit
                if low <= trade['sl']:
                    print(f"Backtest: Trade {ticket} SL hit.")
                    self.close_trade(ticket, trade['sl'], current_time)
                    closed_tickets.append(ticket)
                # Check for TP hit
                elif high >= trade['tp']:
                    print(f"Backtest: Trade {ticket} TP hit.")
                    self.close_trade(ticket, trade['tp'], current_time)
                    closed_tickets.append(ticket)
            
            elif trade['type'] == 'sell':
                # Check for SL hit
                if high >= trade['sl']:
                    print(f"Backtest: Trade {ticket} SL hit.")
                    self.close_trade(ticket, trade['sl'], current_time)
                    closed_tickets.append(ticket)
                # Check for TP hit
                elif low <= trade['tp']:
                    print(f"Backtest: Trade {ticket} TP hit.")
                    self.close_trade(ticket, trade['tp'], current_time)
                    closed_tickets.append(ticket)
        
        # Clean up closed trades from the open positions dict
        for ticket in closed_tickets:
            if ticket in self.open_positions:
                self.open_positions.pop(ticket)
