# C79 Sniper Bot

Automated XAUUSD trading bot for MetaTrader 5, written in Python.  
The bot runs on Windows, connects directly to MT5, applies a configurable technical strategy, manages risk, filters high impact economic news and sends rich Telegram notifications and health updates.

> **Important**  
> The bot is driven by a `config.json` file that contains broker credentials and other sensitive data.  
> Do **not** commit your real config file to GitHub. Use the example in this README instead and keep your live one private.

---

## Features

- Fully automated trading for **XAUUSD (Gold)** on MetaTrader 5  
- Config driven behaviour. most settings live in `config.json`  
- Technical strategy module with independent BUY and SELL conditions  
- ATR based stops, smart breakeven and trailing stop management  
- Daily profit target and daily loss limit, with the ability to pause trading when hit  
- Centralised risk management and position sizing  
- High impact economic news filter using ForexFactory XML feed with caching. including **Holiday** events  
- Trade statistics tracking to JSON, including win rate and best or worst trades  
- Telegram notification module for all key bot events  
- Telegram command handler service for remote control and health checks  
- Watchdog monitor that keeps the bot running and cleans up stale cache  
- Structured logging and status files for external monitoring tools  

---

## Repository structure

The core of the project is the main trading bot, supported by strategy and risk modules, Telegram services and some legacy components.

```text
c79_sniper_bot/
  main_bot.py
  config.json

  modules/
    __init__.py
    strategy.py
    risk_manager.py
    news_filter.py
    telegram_notifier.py
    trade_statistics.py

  services/
    telegram_command_handler.py
    watchdog_monitor.py

  legacy/
    daily_profit_manager.py
    mt5_connector.py
```

- `main_bot.py` . main C79 Sniper trading bot  
- `config.json` . local configuration file containing credentials, risk settings and behaviour flags  
- `modules/` . core functional modules used by the main bot  
  - `strategy.py` . `C79Strategy` technical rules and signal generation  
  - `risk_manager.py` . `RiskManager` for position sizing and risk limits  
  - `news_filter.py` . `EconomicNewsFilter` for calendar based trading blocks  
  - `telegram_notifier.py` . `TelegramNotifier` for sending messages  
  - `trade_statistics.py` . `TradeStatistics` for performance tracking  
- `services/` . supporting long running services  
  - `telegram_command_handler.py` . `TelegramCommandHandler` for remote control  
  - `watchdog_monitor.py` . `WatchdogMonitor` to keep the bot healthy  
- `legacy/` . older components retained for reference. not used in the main flow  
  - `daily_profit_manager.py`  
  - `mt5_connector.py`  

---

## Main components

### `main_bot.py` . C79SniperBot

Main entry point and orchestration layer.

- Connects to MetaTrader 5 via the `MetaTrader5` Python package  
- Loads and validates `config.json`  
- Sets up logging and writes a status file at `logs/bot_status.json`  
- Instantiates:
  - `C79Strategy` from `modules/strategy.py`  
  - `RiskManager` from `modules/risk_manager.py`  
  - `EconomicNewsFilter` from `modules/news_filter.py`  
  - `TradeStatistics` from `modules/trade_statistics.py`  
  - `TelegramNotifier` from `modules/telegram_notifier.py`  
- Core responsibilities:
  - Pulls price data from MT5  
  - Builds pandas DataFrames for the strategy  
  - Evaluates BUY and SELL conditions independently  
  - Opens and manages positions subject to risk rules  
  - Applies ATR based stops, smart breakeven and trailing stop logic  
  - Enforces daily profit targets and daily loss limits  
  - Respects news and holiday blackout windows from `EconomicNewsFilter`  
  - Updates trade statistics and sends Telegram updates for key events  

### `modules/strategy.py` . C79Strategy

Technical analysis strategy module.

- Uses the `ta` library for indicators:
  - EMA crossovers (fast, slow, trend EMAs)  
  - RSI  
  - Stochastic Oscillator  
  - ADX  
- Evaluates BUY and SELL blocks separately and returns:
  - Signal direction (buy or sell or flat)  
  - Condition counts  
  - Textual reasoning details for logging or Telegram  
- Key configuration via `config["STRATEGY"]`:
  - `min_conditions_required`  
  - EMA periods  
  - RSI overbought or oversold thresholds  
  - Stochastic and ADX thresholds  
  - Bollinger Band settings where applicable  

### `modules/risk_manager.py` . RiskManager

Risk and money management module.

- Uses MT5 account information to enforce:
  - Maximum open positions per bot  
  - Maximum total volume or exposure per symbol  
  - Maximum daily loss in currency terms  
  - Maximum drawdown percentage based on equity or balance  
- Validates potential trades before entry:
  - Position sizing rules  
  - Stop loss and take profit sanity checks relative to entry price  
- Reads configuration from `config["RISK"]` and supporting values from `config["TRADING"]`  

### `modules/news_filter.py` . EconomicNewsFilter

High impact economic news and holiday filter, designed to avoid trading during volatile periods and certain calendar events.

- Fetches news from a ForexFactory XML feed defined in `config["NEWS_FILTER"]`  
- Filters by:
  - Currency list, typically `["USD"]` for XAUUSD  
  - Impact levels, for example `["High", "Holiday"]`  
  - Future time window around each event  
- Caches events to `cache/news_events.json` and reuses them when possible  
- Provides:
  - Methods to check if trading is allowed at the current time  
  - A list of upcoming events and holidays within a chosen horizon for display in Telegram  

### `modules/trade_statistics.py` . TradeStatistics

Tracks and persists historical performance to JSON.

- Stores per trade information such as:
  - Profit or loss  
  - Exit reason  
  - Order type  
  - Size  
- Maintains aggregate statistics including:
  - Total trades  
  - Win and loss counts and win rate  
  - Total profit and loss  
  - Best and worst trade  
  - Streaks and exit reason breakdowns  
- The statistics file path and history length are read from the relevant section in `config.json`  

### `modules/telegram_notifier.py` . TelegramNotifier

Thin wrapper around the Telegram Bot HTTP API using `requests`.

- Sends HTML formatted messages to a configured chat  
- Used by `main_bot.py` to send:
  - Startup and shutdown notifications  
  - New trade opened and closed  
  - Daily summaries  
  - Error messages or warnings  
- Configuration comes from `config["TELEGRAM"]`:
  - `bot_token`  
  - `chat_id`  
  - `enabled`  

### `services/telegram_command_handler.py` . TelegramCommandHandler

Separate long running process that polls Telegram for commands and interacts with the bot.

- Reads the same `config.json` as the main bot  
- Uses:
  - `config["BROKER"]` for symbol and magic number  
  - `config["TELEGRAM"]` for API credentials and authorised user IDs  
  - `config["TELEGRAM_HANDLER"]` for handler specific settings  
- Core functionality:
  - Long polls the Telegram Bot API for updates  
  - Restricts access to `authorized_user_ids`  
  - Provides the following commands:
    - `/start` . start the trading bot  
    - `/stop` . stop the trading bot  
    - `/news` . show upcoming news and holiday events  
    - `/status` . show current bot status and basic account information  
    - `/positions` . list current open positions relevant to the bot  
    - `/daily` . show daily performance summary and key statistics  
    - `/health` . show a combined health view, including last heartbeat, margin levels and watchdog status  
  - Reads `logs/bot_status.json` and other files to determine the current bot state  
  - Can start or stop the main bot process using Windows commands  
- Intended to run alongside the bot on the same machine  

### `services/watchdog_monitor.py` . WatchdogMonitor

Lightweight watchdog process that ensures the main bot stays healthy.

- Reads its settings from `config["WATCHDOG"]` and `config["SYSTEM"]`  
- Regularly checks:
  - Whether the main bot process is running, using the PID from `logs/bot_status.json`  
  - Whether the current time is within configured trading hours  
- If the bot is not running during trading hours and no manual stop flag is present:
  - Automatically restarts the bot using `subprocess`  
- Cleans up old cache files such as stale news events  
- Windows specific. uses `tasklist` and `subprocess.CREATE_NO_WINDOW`  

### `legacy/` components

The `legacy` folder contains older, now superseded modules.  
They are retained for reference and are **not** part of the normal run pipeline.

- `legacy/daily_profit_manager.py` . earlier implementation of daily profit logic  
- `legacy/mt5_connector.py` . earlier connector abstraction around MetaTrader 5  

---

## Requirements

- **Operating system**: Windows. the MetaTrader 5 Python API and system commands expect Windows  
- **Python**: 3.9 or later recommended  
- **MetaTrader 5** desktop terminal installed and logged in on the same machine  
- Python packages:
  - `MetaTrader5`  
  - `numpy`  
  - `pandas`  
  - `ta`  (technical analysis indicators)  
  - `requests`  

Install dependencies:

```bash
pip install MetaTrader5 numpy pandas ta requests
```

You may also want to create a virtual environment:

```bash
python -m venv .venv
.\.venv\Scriptsctivate
pip install -r requirements.txt  # if you add one
```

---

## Configuration . `config.json`

The project relies on a `config.json` file placed alongside `main_bot.py` in the `c79_sniper_bot` folder.  
This file is **not** committed to the repository because it contains live account details.

Add `config.json` to your `.gitignore`:

```gitignore
config.json
logs/
cache/
```

### Example structure

The exact fields available are extensive. below is a trimmed example that shows the key sections and common options.  
Adjust the values to suit your broker, risk tolerance and strategy.

```json
{
  "BROKER": {
    "symbol": "XAUUSD",
    "magic_number": 79001,
    "account": "1234567",
    "password": "YOUR_MT5_PASSWORD",
    "server": "YourBroker-Server",
    "broker_timezone_offset": 0
  },

  "TRADING": {
    "timeframe": "M5",
    "lot_size": 0.01,

    "daily_profit_target": 50.0,

    "use_smart_breakeven": true,
    "breakeven_profit_multiple": 1.2,
    "breakeven_lock_profit_multiple": 0.5,

    "use_trailing_stop": true,
    "trailing_stop_atr_multiple": 2.0,
    "min_profit_for_trail_activation": 1.5,

    "volatility_detection": {
      "enabled": true,
      "atr_period": 14,
      "atr_scapl_threshold": 2.0,
      "scalp_profit_target_gbp": 2.28,
      "scalp_cooldown_seconds": 30,
      "normal_cooldown_seconds": 60
    }
  },

  "RISK": {
    "max_positions_per_bot": 1,
    "max_daily_loss": 100.0,
    "max_daily_loss_currency": "GBP",
    "max_drawdown_percent": 10.0
  },

  "STRATEGY": {
    "min_conditions_required": 3,

    "ema_fast_period": 21,
    "ema_slow_period": 50,
    "ema_trend_period": 200,

    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,

    "stoch_k_period": 14,
    "stoch_d_period": 3,
    "stoch_oversold": 20,
    "stoch_overbought": 80,

    "adx_period": 14,
    "adx_threshold": 20,

    "bollinger_period": 20,
    "bollinger_std": 2
  },

  "TELEGRAM": {
    "enabled": true,
    "bot_token": "123456789:ABCDEF...",
    "chat_id": "123456789",
    "api_timeout": 10,
    "authorized_user_ids": [123456789]
  },

  "TELEGRAM_HANDLER": {
    "long_poll_timeout": 30,
    "long_poll_request_timeout": 35,
    "log_active_threshold_minutes": 5,
    "log_warning_threshold_minutes": 60,
    "margin_safe_level": 500,
    "margin_warning_level": 200,
    "news_forecast_hours": 24,
    "max_news_events_display": 5,
    "bot_status_file": "logs/bot_status.json",
    "manual_stop_flag_file": "logs/manual_stop.flag",
    "paths": {
      "trade_statistics_file": "logs/trade_statistics_{symbol}.json",
      "news_events_file": "cache/news_events.json"
    }
  },

  "NEWS_FILTER": {
    "enabled": true,
    "ff_calendar_url": "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
    "relevant_currencies": ["USD"],
    "impact_levels": ["High", "Holiday"],
    "cache_directory": "cache"
  },

  "WATCHDOG": {
    "check_interval_seconds": 300,
    "trading_hours": {
      "saturday_closed": true,
      "sunday_closed": false,
      "sunday_open_hour": 22,
      "monday_open_hour": 0,
      "friday_close_hour": 22
    }
  },

  "SYSTEM": {
    "log_directory": "logs",
    "bot_status_file": "logs/bot_status.json"
  }
}
```

Treat this as a starting point. your live configuration may include extra fields that match the latest code.

---

## Running the bot

### 1. Prepare MetaTrader 5

- Install the MT5 desktop terminal from your broker  
- Log in with the account that will be used by the bot  
- Ensure algorithmic trading is allowed and that XAUUSD is available in the Market Watch  

### 2. Create `config.json`

- Copy the example above into `config.json` in the `c79_sniper_bot` folder  
- Fill in your real account number, password and server name  
- Adjust risk and strategy settings for your own preferences  

### 3. Start the main bot

From a terminal in the `c79_sniper_bot` directory:

```bash
python main_bot.py config.json
```

The bot will:

- Connect to MetaTrader 5  
- Validate the configuration  
- Start its trading loop  
- Write a status file to `logs/bot_status.json`  
- Create or update log files under `logs/`  

### 4. Optional . start the watchdog

To keep the bot running and automatically restart it during trading hours:

```bash
python services/watchdog_monitor.py config.json
```

This is intended to run in a separate console, a background task or a Windows service.

### 5. Optional . start the Telegram command handler

To enable remote control and health monitoring via Telegram:

```bash
python services/telegram_command_handler.py
```

This script reads `config.json` automatically.  
Ensure that:

- The Telegram bot token and chat ID are correct  
- Your user ID is included in `authorized_user_ids`  

---

## Logging and monitoring

- **Logs directory**. typically `logs/`  
  - Main bot log. for example `logs/c79_sniper_{symbol}.log` (file name depends on your config and logging setup)  
  - Telegram command handler log  
  - Watchdog log if configured that way  
- **Status file**. `logs/bot_status.json`  
  - Contains at least the bot PID and other runtime details used by `services/watchdog_monitor.py` and `services/telegram_command_handler.py`  
- **Statistics file**. for example `logs/trade_statistics_XAUUSD.json`  
  - Contains historical trade statistics generated by `TradeStatistics`  
- **Cache directory**. `cache/`  
  - Stores `news_events.json` and other transient data from `EconomicNewsFilter` and the watchdog  

You can feed these logs and status files into external monitoring tools such as Uptime Kuma or Windows services, depending on your setup.

---

## Safety and disclaimer

Trading leveraged instruments such as CFDs or spot gold carries a high level of risk.  
This project is provided for **educational purposes only**. There is no guarantee that the strategy will be profitable.  

You are fully responsible for:

- Testing the bot on demo accounts before going live  
- Ensuring that your configuration and risk settings are appropriate  
- Complying with all regulations that apply in your jurisdiction  

The authors and maintainers accept no liability for financial losses or issues caused by use of this software.

---

## Licence

Add your preferred licence here. for example MIT:

```text
MIT Licence
```

Or include a standard `LICENCE` file in the repository root.

---
