import MetaTrader5 as mt5
from datetime import datetime, date
from typing import Optional, Dict

class RiskWarden:
    def __init__(self, account_balance: float, risk_per_trade: float = 0.5,
                 max_daily_loss_percent: float = 3.0, max_drawdown_percent: float = 10.0):
        self.initial_balance = account_balance
        self.current_balance = account_balance
        self.risk_per_trade = risk_per_trade / 100
        self.max_daily_loss = max_daily_loss_percent / 100
        self.max_drawdown = max_drawdown_percent / 100

        self.daily_start_balance = account_balance
        self.daily_pnl = 0.0
        self.peak_equity = account_balance
        self.trades_today = 0
        self.wins_today = 0

        self.trade_log = {}

        print(f"[WARDEN] RiskWarden activated | Risk/Trade: {risk_per_trade}%")
    def update_balance(self):
        account = mt5.account_info()
        if account:
            self.current_balance = account.balance
            self.daily_pnl = account.balance - self.daily_start_balance
            self.peak_equity = max(self.peak_equity, account.equity)

    def reset_daily(self):
        today = date.today()
        if not hasattr(self, '_last_reset') or self._last_reset != today:
            self.daily_start_balance = self.current_balance
            self.daily_pnl = 0.0
            self.trades_today = 0
            self.wins_today = 0
            self._last_reset = today
            print(f"[WARDEN] Daily reset | Starting balance: ${self.daily_start_balance:,.2f}")

    def is_daily_loss_breached(self) -> bool:
        self.update_balance()
        self.reset_daily()
        if self.daily_pnl <= -abs(self.daily_start_balance * self.max_daily_loss):
            print(f"[WARDEN] DAILY LOSS LIMIT BREACHED | PnL: ${self.daily_pnl:,.2f}")
            return True
        return False

    def is_max_drawdown_breached(self) -> bool:
        self.update_balance()
        current_dd = (self.peak_equity - self.current_balance) / self.peak_equity
        if current_dd >= self.max_drawdown:
            print(f"[WARDEN] MAX DRAWDOWN BREACHED | DD: {current_dd*100:.2f}%")
            return True
        return False

    def calculate_lot_size(self, symbol: str, sl_pips: float) -> float:
        """Calculate lot size based on risk % and SL distance"""
        if sl_pips <= 0:
            return 0.01

        account = mt5.account_info()
        if not account:
            return 0.01

        tick_value = mt5.symbol_info(symbol).trade_tick_value
        tick_size = mt5.symbol_info(symbol).trade_tick_size
        point = mt5.symbol_info(symbol).point

        risk_amount = account.balance * self.risk_per_trade
        pip_value = tick_value / tick_size * point * 10  # for 5-digit brokers
        lots = risk_amount / (sl_pips * pip_value)

        # Round to broker-allowed step
        min_lot = mt5.symbol_info(symbol).volume_min
        lot_step = mt5.symbol_info(symbol).volume_step
        lots = max(min_lot, round(lots / lot_step) * lot_step)

        print(f"[WARDEN] Risk: ${risk_amount:,.2f} | SL: {sl_pips} pips | Lot size: {lots:.2f}")
        return round(lots, 2)

    def log_trade(self, ticket: int, result: float):
        self.trades_today += 1
        if result > 0:
            self.wins_today += 1
        win_rate = (self.wins_today / self.trades_today * 100) if self.trades_today > 0 else 0
        print(f"[WARDEN] Trade logged | Win Rate Today: {win_rate:.1f}% ({self.wins_today}/{self.trades_today})")

    def allow_trade(self) -> bool:
        if self.is_daily_loss_breached() or self.is_max_drawdown_breached():
            print("[WARDEN] TRADING BLOCKED — Risk limits exceeded")
            return False
        return True