"""
C79 Sniper Enhanced Daily Profit Manager
Version: 3.0.0
Purpose: Intelligent daily profit tracking with adaptive pacing and NET profit calculation
UPDATED: All hardcoded values moved to config.json
"""

import MetaTrader5 as mt5
from datetime import datetime, time, timedelta
import logging
import json
from pathlib import Path
from typing import Dict, Tuple, Optional

class DailyProfitManager:
    """
    Manages daily profit targets with intelligent features:
    - Dynamic broker fee calculation (configurable per full lot)
    - NET profit tracking (gross - fees)
    - Adaptive trade pacing (gentle/aggressive based on volatility)
    - Friday trading window handling
    - Midnight auto-reset
    - Progress reporting for Telegram
    """
    
    def __init__(self, config: dict, magic_number: int, symbol: str, logger: logging.Logger):
        """
        Initialize the Daily Profit Manager
        
        Args:
            config: Bot configuration dictionary
            magic_number: MT5 magic number for trade filtering
            symbol: Trading symbol (e.g., "XAUUSD")
            logger: Logger instance
        """
        self.config = config
        self.magic_number = magic_number
        self.symbol = symbol
        self.logger = logger
        
        # Load profit manager config
        profit_config = config.get('PROFIT_MANAGER', {})
        
        # Core settings from config
        self.daily_target_gross = config.get('TRADING', {}).get('daily_profit_target', 175.0)
        self.broker_fee_per_lot = profit_config.get('broker_fee_per_full_lot', 5.51)
        self.enable_pacing = profit_config.get('enable_trade_pacing', True)
        self.pacing_mode = profit_config.get('pacing_mode', 'adaptive')
        
        # State tracking
        self.daily_target_reached = False
        self.last_reset_date = datetime.now().date()
        self.trades_today = 0
        self.total_fees_today = 0.0
        self.gross_profit_today = 0.0
        self.net_profit_today = 0.0
        
        # Pacing settings from config (NO HARDCODED VALUES)
        self.min_trade_interval_normal = profit_config.get('min_trade_interval_normal', 180)
        self.min_trade_interval_aggressive = profit_config.get('min_trade_interval_aggressive', 60)
        self.last_trade_time = None
        
        # Friday settings from config
        self.friday_close_hour = profit_config.get('friday_close_hour', 22)
        
        # Adaptive pacing threshold from config
        self.adaptive_threshold = profit_config.get('adaptive_pacing_threshold', 0.7)
        
        # ETA calculation from config
        self.estimated_minutes_per_trade = profit_config.get('estimated_minutes_per_trade', 30)
        
        # State file path from config
        self.state_file = profit_config.get('daily_profit_state_file', 'logs/daily_profit_state.json')
        
        self.logger.info("[OK] DailyProfitManager initialized")
        self.logger.info(f"   Target: £{self.daily_target_gross:.2f} gross")
        self.logger.info(f"   Fee: £{self.broker_fee_per_lot:.2f} per full lot")
        self.logger.info(f"   Pacing: {self.pacing_mode} ({self.enable_pacing})")
        self.logger.info(f"   Normal interval: {self.min_trade_interval_normal}s")
        self.logger.info(f"   Aggressive interval: {self.min_trade_interval_aggressive}s")
        self.logger.info(f"   Adaptive threshold: {self.adaptive_threshold:.1%}")
    
    def calculate_trade_fee(self, lot_size: float) -> float:
        """
        Calculate broker fee for a trade dynamically based on lot size
        
        Args:
            lot_size: Trade lot size (e.g., 0.70)
            
        Returns:
            Fee amount in account currency
        """
        fee = lot_size * self.broker_fee_per_lot
        return round(fee, 2)
    
    def get_daily_stats(self) -> Dict:
        """
        Query MT5 for today's trading statistics
        
        Returns:
            Dictionary with:
            - trades_count: Number of trades today
            - gross_profit: Total gross profit/loss
            - total_fees: Estimated total fees
            - net_profit: Gross profit minus fees
            - target_percentage: Progress towards target (0-100+)
        """
        try:
            # Get today's date range
            today = datetime.now().date()
            today_start = datetime.combine(today, time.min)
            today_end = datetime.combine(today, time.max)
            
            # Query MT5 history for today's deals
            deals = mt5.history_deals_get(today_start, today_end)
            
            if deals is None or len(deals) == 0:
                return {
                    'trades_count': 0,
                    'gross_profit': 0.0,
                    'total_fees': 0.0,
                    'net_profit': 0.0,
                    'target_percentage': 0.0,
                    'average_profit_per_trade': 0.0,
                    'estimated_target_eta': None
                }
            
            # Filter by magic number and symbol
            relevant_deals = [
                d for d in deals 
                if d.magic == self.magic_number and d.symbol == self.symbol and d.entry == 1  # entry=1 means OUT (close)
            ]
            
            if not relevant_deals:
                return {
                    'trades_count': 0,
                    'gross_profit': 0.0,
                    'total_fees': 0.0,
                    'net_profit': 0.0,
                    'target_percentage': 0.0,
                    'average_profit_per_trade': 0.0,
                    'estimated_target_eta': None
                }
            
            # Calculate statistics
            trades_count = len(relevant_deals)
            gross_profit = sum(d.profit for d in relevant_deals)
            
            # Calculate total fees (estimate from lot sizes)
            total_fees = sum(self.calculate_trade_fee(d.volume) for d in relevant_deals)
            
            # Calculate NET profit
            net_profit = gross_profit - total_fees
            
            # Calculate progress percentage
            target_percentage = (gross_profit / self.daily_target_gross) * 100 if self.daily_target_gross > 0 else 0
            
            # Calculate average profit per trade
            avg_profit = gross_profit / trades_count if trades_count > 0 else 0
            
            # Estimate time to reach target (if positive trend) - USING CONFIG VALUE
            estimated_eta = None
            if avg_profit > 0 and gross_profit < self.daily_target_gross:
                remaining_profit = self.daily_target_gross - gross_profit
                trades_needed = remaining_profit / avg_profit
                minutes_needed = trades_needed * self.estimated_minutes_per_trade  # FROM CONFIG
                estimated_eta = datetime.now() + timedelta(minutes=minutes_needed)
            
            # Update internal state
            self.trades_today = trades_count
            self.gross_profit_today = gross_profit
            self.total_fees_today = total_fees
            self.net_profit_today = net_profit
            
            return {
                'trades_count': trades_count,
                'gross_profit': round(gross_profit, 2),
                'total_fees': round(total_fees, 2),
                'net_profit': round(net_profit, 2),
                'target_percentage': round(target_percentage, 1),
                'average_profit_per_trade': round(avg_profit, 2),
                'estimated_target_eta': estimated_eta
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error calculating daily stats: {e}")
            return {
                'trades_count': 0,
                'gross_profit': 0.0,
                'total_fees': 0.0,
                'net_profit': 0.0,
                'target_percentage': 0.0,
                'average_profit_per_trade': 0.0,
                'estimated_target_eta': None
            }
    
    def check_target_reached(self) -> Tuple[bool, Dict]:
        """
        Check if daily profit target has been reached
        
        Returns:
            Tuple of (target_reached: bool, stats: dict)
        """
        stats = self.get_daily_stats()
        
        # Check if gross profit meets or exceeds target
        target_reached = stats['gross_profit'] >= self.daily_target_gross
        
        if target_reached and not self.daily_target_reached:
            self.logger.info(f"[TARGET] DAILY TARGET REACHED!")
            self.logger.info(f"   Gross: £{stats['gross_profit']:.2f}")
            self.logger.info(f"   Fees: £{stats['total_fees']:.2f}")
            self.logger.info(f"   NET: £{stats['net_profit']:.2f}")
            self.daily_target_reached = True
        
        return target_reached, stats
    
    def should_allow_trading(self) -> Tuple[bool, str]:
        """
        Determine if trading should be allowed based on:
        - Daily target status
        - Time of day (Friday special handling)
        - Pacing requirements
        
        Returns:
            Tuple of (allow_trading: bool, reason: str)
        """
        now = datetime.now()
        
        # Check midnight reset
        if now.date() > self.last_reset_date:
            self.reset_daily_state()
        
        # Check if target already reached
        if self.daily_target_reached:
            return False, f"Daily target reached (£{self.gross_profit_today:.2f}). Paused until midnight."
        
        # Check Friday closing time (FROM CONFIG)
        if now.weekday() == 4 and now.hour >= self.friday_close_hour:
            return False, f"Friday market closes at {self.friday_close_hour}:00. No new trades."
        
        # Check trade pacing
        if self.enable_pacing and self.last_trade_time is not None:
            time_since_last = (now - self.last_trade_time).total_seconds()
            
            # Determine required interval based on pacing mode
            required_interval = self.min_trade_interval_normal
            
            if self.pacing_mode == 'aggressive':
                required_interval = self.min_trade_interval_aggressive
            elif self.pacing_mode == 'gentle':
                required_interval = self.min_trade_interval_normal
            elif self.pacing_mode == 'adaptive':
                # Adaptive: Check market volatility or time pressure
                stats = self.get_daily_stats()
                hours_elapsed = now.hour + (now.minute / 60.0)
                
                # If behind schedule, be more aggressive
                expected_progress = (hours_elapsed / 24.0) * 100
                actual_progress = stats['target_percentage']
                
                # USING CONFIG THRESHOLD
                if actual_progress < expected_progress * self.adaptive_threshold:
                    required_interval = self.min_trade_interval_aggressive
                else:
                    required_interval = self.min_trade_interval_normal
            
            if time_since_last < required_interval:
                wait_time = int(required_interval - time_since_last)
                return False, f"Trade pacing: Wait {wait_time}s before next trade ({self.pacing_mode} mode)"
        
        return True, "Trading allowed"
    
    def get_friday_trading_hours_remaining(self) -> Optional[float]:
        """
        Calculate remaining trading hours on Friday
        
        Returns:
            Hours remaining until Friday close, or None if not Friday
        """
        now = datetime.now()
        
        if now.weekday() != 4:  # Not Friday
            return None
        
        friday_close = now.replace(hour=self.friday_close_hour, minute=0, second=0, microsecond=0)
        
        if now >= friday_close:
            return 0.0
        
        hours_remaining = (friday_close - now).total_seconds() / 3600.0
        return round(hours_remaining, 1)
    
    def record_trade(self, lot_size: float, profit: float):
        """
        Record a trade execution for pacing tracking
        
        Args:
            lot_size: Trade lot size
            profit: Trade profit/loss
        """
        self.last_trade_time = datetime.now()
        self.trades_today += 1
        
        # Update running totals
        fee = self.calculate_trade_fee(lot_size)
        self.gross_profit_today += profit
        self.total_fees_today += fee
        self.net_profit_today = self.gross_profit_today - self.total_fees_today
        
        self.logger.info(f"📝 Trade recorded: Profit={profit:.2f}, Fee={fee:.2f}, NET={self.net_profit_today:.2f}")
    
    def reset_daily_state(self):
        """
        Reset daily tracking at midnight
        """
        self.logger.info("[RESET] Midnight reset - New trading day")
        self.daily_target_reached = False
        self.last_reset_date = datetime.now().date()
        self.trades_today = 0
        self.total_fees_today = 0.0
        self.gross_profit_today = 0.0
        self.net_profit_today = 0.0
        self.last_trade_time = None
    
    def get_progress_report(self) -> str:
        """
        Generate a formatted progress report for Telegram
        
        Returns:
            Formatted string with progress details
        """
        stats = self.get_daily_stats()
        now = datetime.now()
        
        # Calculate time elapsed today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed = now - today_start
        hours_elapsed = int(elapsed.total_seconds() // 3600)
        minutes_elapsed = int((elapsed.total_seconds() % 3600) // 60)
        
        # Build report
        report = f"[STATS] **Daily Progress Report**\n"
        report += f"━━━━━━━━━━━━━━━━━━━━\n"
        report += f"[PROFIT] **Gross Profit:** £{stats['gross_profit']:.2f}\n"
        report += f"💸 **Estimated Fees:** £{stats['total_fees']:.2f} ({stats['trades_count']} trades)\n"
        report += f"💵 **NET Profit:** £{stats['net_profit']:.2f} / £{self.daily_target_gross:.2f}\n"
        report += f"📈 **Progress:** {stats['target_percentage']:.1f}%\n"
        report += f"⏰ **Time:** {now.strftime('%H:%M')} ({hours_elapsed}h {minutes_elapsed}m elapsed)\n"
        
        # Add pace assessment (USING CONFIG THRESHOLD)
        if stats['trades_count'] > 0:
            expected_progress = (hours_elapsed / 24.0) * 100
            if stats['target_percentage'] >= expected_progress:
                pace = "[OK] On track"
            elif stats['target_percentage'] >= expected_progress * self.adaptive_threshold:
                pace = "[WARN] Slightly behind"
            else:
                pace = "🔴 Behind schedule"
            report += f"⏱️ **Pace:** {pace}\n"
        
        # Add Friday info if applicable
        friday_hours = self.get_friday_trading_hours_remaining()
        if friday_hours is not None:
            report += f"📅 **Friday:** {friday_hours:.1f}h until {self.friday_close_hour}:00 close\n"
        
        # Add ETA if available
        if stats['estimated_target_eta']:
            eta_time = stats['estimated_target_eta'].strftime('%H:%M')
            report += f"[TARGET] **Estimated Target:** {eta_time}\n"
        
        report += f"━━━━━━━━━━━━━━━━━━━━"
        
        return report
    
    def get_compact_progress(self) -> str:
        """
        Generate a compact one-line progress update
        
        Returns:
            Compact progress string
        """
        stats = self.get_daily_stats()
        return f"💵 NET: £{stats['net_profit']:.2f} / £{self.daily_target_gross:.2f} ({stats['target_percentage']:.1f}%)"
    
    def save_state(self):
        """
        Save current state to file for recovery
        UPDATED: Uses state file path from config
        """
        try:
            state = {
                'date': self.last_reset_date.isoformat(),
                'target_reached': self.daily_target_reached,
                'trades_today': self.trades_today,
                'gross_profit': self.gross_profit_today,
                'total_fees': self.total_fees_today,
                'net_profit': self.net_profit_today,
                'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None
            }
            
            # Use configured state file path
            state_path = Path(self.state_file)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(state_path, 'w') as f:
                json.dump(state, f, indent=2)
                
            self.logger.debug(f"💾 State saved to {self.state_file}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving state: {e}")
    
    def load_state(self):
        """
        Load state from file if available
        UPDATED: Uses state file path from config
        """
        try:
            state_path = Path(self.state_file)
            
            if not state_path.exists():
                self.logger.debug("No saved state found")
                return
            
            with open(state_path, 'r') as f:
                state = json.load(f)
            
            # Only load if same date
            saved_date = datetime.fromisoformat(state['date']).date()
            if saved_date == datetime.now().date():
                self.daily_target_reached = state.get('target_reached', False)
                self.trades_today = state.get('trades_today', 0)
                self.gross_profit_today = state.get('gross_profit', 0.0)
                self.total_fees_today = state.get('total_fees', 0.0)
                self.net_profit_today = state.get('net_profit', 0.0)
                
                last_trade = state.get('last_trade_time')
                if last_trade:
                    self.last_trade_time = datetime.fromisoformat(last_trade)
                
                self.logger.info(f"💾 State loaded: NET £{self.net_profit_today:.2f}, {self.trades_today} trades")
            else:
                self.logger.info("Saved state is from different date, starting fresh")
                
        except Exception as e:
            self.logger.error(f"❌ Error loading state: {e}")
    
    def should_pause_trading(self) -> bool:
        """
        Check if trading should be paused (for compatibility with main_bot.py)
        
        Returns:
            bool: True if should pause, False otherwise
        """
        target_reached, _ = self.check_target_reached()
        return target_reached
    
    def update(self):
        """
        Update profit manager state (called from main bot loop)
        """
        # Check for midnight reset
        if datetime.now().date() > self.last_reset_date:
            self.reset_daily_state()
        
        # Save state periodically
        if self.trades_today > 0:
            self.save_state()
    
    def track_trade_open(self, ticket: int, direction: str, lot_size: float):
        """
        Track when a trade is opened (for future enhancements)
        
        Args:
            ticket: Trade ticket number
            direction: BUY or SELL
            lot_size: Position size
        """
        self.logger.debug(f"Trade opened: #{ticket}, {direction}, {lot_size} lots")
    
    def track_trade_close(self, ticket: int, profit: float, direction: str, lot_size: float, 
                          entry_price: float, exit_price: float, reason: str):
        """
        Track when a trade is closed
        
        Args:
            ticket: Trade ticket number
            profit: Profit/loss amount
            direction: BUY or SELL
            lot_size: Position size
            entry_price: Entry price
            exit_price: Exit price
            reason: Close reason
        """
        self.record_trade(lot_size, profit)
        self.logger.info(f"Trade closed: #{ticket}, {direction}, P/L: £{profit:.2f}")


if __name__ == "__main__":
    print("Daily Profit Manager Module - UPDATED!")
    print("All 6 hardcoded values moved to config.json:")
    print("  1. min_trade_interval_normal (was 180)")
    print("  2. min_trade_interval_aggressive (was 60)")
    print("  3. friday_close_hour (was 22)")
    print("  4. estimated_minutes_per_trade (was 30)")
    print("  5. adaptive_pacing_threshold (was 0.7)")
    print("  6. daily_profit_state_file (was 'logs/daily_profit_state.json')")
