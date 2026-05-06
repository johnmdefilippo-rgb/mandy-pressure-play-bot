"""
Mandy's Pressure Play Bot
Clean Version — Safety Corrected / No Daily Levels

Markets: NQ, ES, MGC, SIL, MNQ, MES
Style: Intraday Futures Scalping
Timeframes:
    Execution: 3min or 5min
    Confirmation: 1min
    Higher Timeframe: 15min

Install:
    pip install project-x-py pandas python-dotenv

.env:
    PROJECT_X_USERNAME=your_username
    PROJECT_X_API_KEY=your_api_key

Notes:
    - Starts in paper/signal-only mode by default.
    - Set CFG.trade_enabled = True only after confirming order method compatibility.
    - Uses closed-bar/new-bar style throttling to avoid repeat signals on the same bar.
"""

import asyncio
import inspect
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional, Tuple

import pandas as pd
from project_x_py import TradingSuite


# =========================
# CONFIG
# =========================

@dataclass
class Config:
    symbol: str = "MNQ"
    exec_tf: str = "5min"
    confirm_tf: str = "1min"
    htf_tf: str = "15min"

    contracts: int = 1

    max_trades_per_day: int = 3
    max_daily_loss: float = 250.00

    stop_buffer_points: float = 2.0
    target_rr: float = 1.5

    max_ma_cluster_width_points: float = 8.0

    # Risk sanity limits in points.
    min_risk_points: float = 2.0
    max_risk_points: float = 40.0

    # Optional time filter using local machine time.
    use_time_filter: bool = False
    trade_start_time: time = time(9, 35)
    trade_end_time: time = time(11, 30)

    # Set True only after paper testing.
    trade_enabled: bool = False

    poll_seconds: int = 5

    # Price rounding. MNQ/NQ/ES/MES commonly trade in 0.25 increments.
    tick_size: float = 0.25

    # If True, print SDK order method signature on startup.
    debug_order_signature: bool = True


CFG = Config()


# =========================
# UTILITIES
# =========================

def round_to_tick(price: float, tick_size: float = CFG.tick_size) -> float:
    if tick_size <= 0:
        return float(price)
    return round(round(price / tick_size) * tick_size, 10)


def latest(df: pd.DataFrame) -> pd.Series:
    return df.iloc[-1]


def previous(df: pd.DataFrame) -> pd.Series:
    return df.iloc[-2]


def normalize_dataframe(df) -> Optional[pd.DataFrame]:
    """Convert SDK dataframe-like objects to pandas and normalize column names."""
    if df is None:
        return None

    if hasattr(df, "to_pandas"):
        df = df.to_pandas()

    if not isinstance(df, pd.DataFrame):
        return None

    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]

    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        print(f"PASS: Missing required columns: {missing}")
        return None

    # Ensure numeric OHLCV values.
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])
    return df


def enough_data(*dfs: pd.DataFrame, min_len: int = 40) -> bool:
    return all(df is not None and len(df) >= min_len for df in dfs)


def in_trade_window() -> bool:
    if not CFG.use_time_filter:
        return True

    now = datetime.now().time()
    return CFG.trade_start_time <= now <= CFG.trade_end_time


def get_field(obj, *names, default=None):
    """Safely read a field from either an object or dict without treating 0 as missing."""
    if obj is None:
        return default

    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)

    return default


# =========================
# INDICATORS
# =========================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ema5"] = df["close"].ewm(span=5, adjust=False).mean()
    df["ma7"] = df["close"].rolling(7).mean()
    df["ma14"] = df["close"].rolling(14).mean()
    df["ma21"] = df["close"].rolling(21).mean()
    df["ma35"] = df["close"].rolling(35).mean()

    if "volume" in df.columns and df["volume"].fillna(0).sum() > 0:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        cumulative_volume = df["volume"].replace(0, pd.NA).cumsum()
        df["vwap"] = (typical * df["volume"]).cumsum() / cumulative_volume
        df["vwap"] = df["vwap"].ffill().fillna(df["close"])
    else:
        df["vwap"] = df["close"]

    return df.dropna().copy()


# =========================
# MARKET STATE
# =========================

def ma_cluster_width(row: pd.Series) -> float:
    mas = [row["ma14"], row["ma21"], row["ma35"]]
    return float(max(mas) - min(mas))


def is_spaghetti(df: pd.DataFrame) -> bool:
    row = latest(df)
    prev = previous(df)

    cluster_tight = ma_cluster_width(row) <= CFG.max_ma_cluster_width_points
    ema_flat = abs(float(row["ema5"]) - float(prev["ema5"])) < 1.0

    return cluster_tight and ema_flat


def htf_bias(htf_df: pd.DataFrame) -> Optional[str]:
    row = latest(htf_df)

    if row["close"] > row["ema5"] > row["ma21"]:
        return "BULLISH"

    if row["close"] < row["ema5"] < row["ma21"]:
        return "BEARISH"

    return None


# =========================
# CROSS LOGIC
# =========================

def crossed_above(df: pd.DataFrame, fast: str, slow: str) -> bool:
    return previous(df)[fast] <= previous(df)[slow] and latest(df)[fast] > latest(df)[slow]


def crossed_below(df: pd.DataFrame, fast: str, slow: str) -> bool:
    return previous(df)[fast] >= previous(df)[slow] and latest(df)[fast] < latest(df)[slow]


# =========================
# STRUCTURE HOLD
# =========================

def structure_held_bullish(df: pd.DataFrame) -> bool:
    row = latest(df)

    cluster_low = min(row["ma14"], row["ma21"], row["ma35"])
    cluster_high = max(row["ma14"], row["ma21"], row["ma35"])

    pulled_into_structure = row["low"] <= cluster_high
    closed_above_structure = row["close"] > cluster_low

    return bool(pulled_into_structure and closed_above_structure)


def structure_held_bearish(df: pd.DataFrame) -> bool:
    row = latest(df)

    cluster_low = min(row["ma14"], row["ma21"], row["ma35"])
    cluster_high = max(row["ma14"], row["ma21"], row["ma35"])

    pulled_into_structure = row["high"] >= cluster_low
    closed_below_structure = row["close"] < cluster_high

    return bool(pulled_into_structure and closed_below_structure)


# =========================
# LOWER-TIMEFRAME CONFIRMATION
# =========================

def confirm_bullish(confirm_df: pd.DataFrame) -> bool:
    row = latest(confirm_df)
    return bool(row["close"] > row["ema5"] > row["ma7"])


def confirm_bearish(confirm_df: pd.DataFrame) -> bool:
    row = latest(confirm_df)
    return bool(row["close"] < row["ema5"] < row["ma7"])


# =========================
# PRESSURE PLAY SETUPS
# =========================

def bullish_pressure_play(exec_df: pd.DataFrame, confirm_df: pd.DataFrame, htf_df: pd.DataFrame) -> bool:
    if htf_bias(htf_df) != "BULLISH":
        return False

    if is_spaghetti(exec_df):
        return False

    if not structure_held_bullish(exec_df):
        return False

    if not crossed_above(exec_df, "ema5", "ma7"):
        return False

    if latest(exec_df)["close"] <= latest(exec_df)["ema5"]:
        return False

    if not confirm_bullish(confirm_df):
        return False

    return True


def bearish_pressure_play(exec_df: pd.DataFrame, confirm_df: pd.DataFrame, htf_df: pd.DataFrame) -> bool:
    if htf_bias(htf_df) != "BEARISH":
        return False

    if is_spaghetti(exec_df):
        return False

    if not structure_held_bearish(exec_df):
        return False

    if not crossed_below(exec_df, "ema5", "ma7"):
        return False

    if latest(exec_df)["close"] >= latest(exec_df)["ema5"]:
        return False

    if not confirm_bearish(confirm_df):
        return False

    return True


def get_signal(exec_df: pd.DataFrame, confirm_df: pd.DataFrame, htf_df: pd.DataFrame) -> Optional[str]:
    if bullish_pressure_play(exec_df, confirm_df, htf_df):
        return "BUY"

    if bearish_pressure_play(exec_df, confirm_df, htf_df):
        return "SELL"

    return None


# =========================
# STOP / TARGET LOGIC
# =========================

def recent_pivot_low(df: pd.DataFrame, lookback: int = 8) -> float:
    return float(df["low"].tail(lookback).min())


def recent_pivot_high(df: pd.DataFrame, lookback: int = 8) -> float:
    return float(df["high"].tail(lookback).max())


def build_trade_plan(signal: str, df: pd.DataFrame) -> Tuple[float, float, float, float]:
    row = latest(df)
    entry = round_to_tick(float(row["close"]))

    if signal == "BUY":
        raw_stop = min(float(row["ma7"]), recent_pivot_low(df)) - CFG.stop_buffer_points
        stop = round_to_tick(raw_stop)
        risk = entry - stop
        target = round_to_tick(entry + risk * CFG.target_rr)
    else:
        raw_stop = max(float(row["ma7"]), recent_pivot_high(df)) + CFG.stop_buffer_points
        stop = round_to_tick(raw_stop)
        risk = stop - entry
        target = round_to_tick(entry - risk * CFG.target_rr)

    return entry, stop, target, float(risk)


def valid_trade_plan(signal: str, entry: float, stop: float, target: float, risk: float) -> bool:
    if risk <= 0:
        print("PASS: Invalid risk <= 0.")
        return False

    if risk < CFG.min_risk_points:
        print(f"PASS: Risk too small: {risk} points.")
        return False

    if risk > CFG.max_risk_points:
        print(f"PASS: Risk too large: {risk} points.")
        return False

    if signal == "BUY" and not (stop < entry < target):
        print("PASS: Invalid BUY bracket.")
        return False

    if signal == "SELL" and not (target < entry < stop):
        print("PASS: Invalid SELL bracket.")
        return False

    return True


# =========================
# INVALIDATION
# =========================

def invalidated_long(df: pd.DataFrame) -> bool:
    row = latest(df)

    cluster_low = min(row["ma14"], row["ma21"], row["ma35"])

    structure_break = row["close"] < cluster_low
    control_flip = crossed_below(df, "ema5", "ma7")
    momentum_loss = row["close"] < row["ema5"]

    return bool(structure_break or control_flip or momentum_loss)


def invalidated_short(df: pd.DataFrame) -> bool:
    row = latest(df)

    cluster_high = max(row["ma14"], row["ma21"], row["ma35"])

    structure_break = row["close"] > cluster_high
    control_flip = crossed_above(df, "ema5", "ma7")
    momentum_loss = row["close"] > row["ema5"]

    return bool(structure_break or control_flip or momentum_loss)


# =========================
# BOT
# =========================

class MandyPressureBot:
    def __init__(self):
        self.trades_today = 0
        self.trade_date = date.today()
        self.last_exec_bar_id = None
        self.starting_daily_pnl = 0.0

    def reset_daily_counters_if_needed(self):
        today = date.today()
        if today != self.trade_date:
            self.trade_date = today
            self.trades_today = 0
            self.starting_daily_pnl = 0.0
            self.last_exec_bar_id = None
            print("Daily counters reset.")

    def is_new_exec_bar(self, exec_df: pd.DataFrame) -> bool:
        """
        Prevents duplicate signals on the same execution bar.

        Prefer a timestamp column. If the dataframe has a RangeIndex, do not use
        the index value because the final row index is often constant in rolling
        SDK dataframes.
        """
        if exec_df is None or exec_df.empty:
            return False

        timestamp_columns = [
            "timestamp", "time", "t", "datetime", "date", "bar_time", "starttime", "start_time"
        ]

        bar_id = None
        for col in timestamp_columns:
            if col in exec_df.columns:
                bar_id = str(exec_df[col].iloc[-1])
                break

        if bar_id is None and not isinstance(exec_df.index, pd.RangeIndex):
            bar_id = str(exec_df.index[-1])

        if bar_id is None:
            # Last-resort fallback. This may still evaluate intrabar updates, but
            # it avoids permanently locking the bot after the first loop.
            row = latest(exec_df)
            bar_id = f"{len(exec_df)}-{row['open']}-{row['high']}-{row['low']}-{row['close']}"

        if bar_id == self.last_exec_bar_id:
            return False

        self.last_exec_bar_id = bar_id
        return True

    async def get_symbol_flat_status(self, suite) -> bool:
        """Returns True when there is no open position for this instrument."""
        try:
            positions = await suite.positions.get_all_positions()
        except Exception as exc:
            print(f"PASS: Could not retrieve positions: {exc}")
            return False

        if not positions:
            return True

        instrument_id = getattr(suite, "instrument_id", None)
        instrument_symbol = CFG.symbol.upper()

        for pos in positions:
            contract_id = get_field(pos, "contract_id", "contractId", "contractID")
            symbol = str(get_field(pos, "symbol", "instrument", "name", default="")).upper()
            size = get_field(pos, "size", "positionSize", "netQuantity", "quantity", default=0)

            try:
                size_value = float(size if size is not None else 0)
            except Exception:
                size_value = 0.0

            same_contract = contract_id is not None and instrument_id is not None and str(contract_id) == str(instrument_id)
            same_symbol = bool(symbol) and instrument_symbol in symbol

            if size_value != 0 and (same_contract or same_symbol):
                return False

        return True

    async def get_daily_pnl(self, suite) -> Optional[float]:
        """
        Best-effort PnL hook.
        Different SDK versions expose account/PnL differently, so this returns None if unavailable.
        The max daily loss protection will not block trading unless a usable PnL value is found.
        """
        try:
            if hasattr(suite, "accounts") and hasattr(suite.accounts, "get_account"):
                account = await suite.accounts.get_account()
                for key in ["daily_pnl", "dailyPnl", "realizedPnl", "realized_pnl"]:
                    if hasattr(account, key):
                        return float(getattr(account, key))
                    if isinstance(account, dict) and key in account:
                        return float(account[key])
        except Exception as exc:
            print(f"WARN: Daily PnL unavailable: {exc}")

        return None

    async def risk_ok(self, suite) -> bool:
        self.reset_daily_counters_if_needed()

        if self.trades_today >= CFG.max_trades_per_day:
            print("PASS: Max trades reached.")
            return False

        daily_pnl = await self.get_daily_pnl(suite)
        if daily_pnl is not None and daily_pnl <= -abs(CFG.max_daily_loss):
            print(f"PASS: Max daily loss reached. Daily PnL: {daily_pnl}")
            return False

        if not in_trade_window():
            print("PASS: Outside trading window.")
            return False

        return True

    async def maybe_print_order_signature(self, suite):
        if not CFG.debug_order_signature:
            return

        try:
            if hasattr(suite, "orders") and hasattr(suite.orders, "place_bracket_order"):
                sig = inspect.signature(suite.orders.place_bracket_order)
                print(f"place_bracket_order signature: {sig}")
            else:
                print("WARN: suite.orders.place_bracket_order not found.")
        except Exception as exc:
            print(f"WARN: Could not inspect order signature: {exc}")

    async def place_bracket_order_safe(self, suite, signal: str, entry: float, stop: float, target: float):
        """
        Sends a bracket order using the installed SDK's supported keyword names.
        This avoids crashing when a SDK version has a narrower method signature.
        """
        if not hasattr(suite, "orders") or not hasattr(suite.orders, "place_bracket_order"):
            raise AttributeError("suite.orders.place_bracket_order was not found")

        side = 0 if signal == "BUY" else 1
        method = suite.orders.place_bracket_order

        desired_kwargs = {
            "contract_id": getattr(suite, "instrument_id", None),
            "contractId": getattr(suite, "instrument_id", None),
            "side": side,
            "size": CFG.contracts,
            "quantity": CFG.contracts,
            "entry_price": entry,
            "entryPrice": entry,
            "stop_loss_price": stop,
            "stopLossPrice": stop,
            "take_profit_price": target,
            "takeProfitPrice": target,
        }

        sig = inspect.signature(method)
        accepted = set(sig.parameters.keys())

        # If the method accepts **kwargs, send the snake_case version.
        accepts_var_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )

        if accepts_var_kwargs:
            kwargs = {
                "contract_id": getattr(suite, "instrument_id", None),
                "side": side,
                "size": CFG.contracts,
                "entry_price": entry,
                "stop_loss_price": stop,
                "take_profit_price": target,
            }
        else:
            kwargs = {k: v for k, v in desired_kwargs.items() if k in accepted and v is not None}

        if "contract_id" not in kwargs and "contractId" not in kwargs:
            kwargs["contract_id"] = getattr(suite, "instrument_id", None)

        return await method(**kwargs)

    async def run(self):
        suite = await TradingSuite.create(
            instrument=CFG.symbol,
            timeframes=[CFG.confirm_tf, CFG.exec_tf, CFG.htf_tf],
        )

        print("===================================")
        print("Mandy's Pressure Play Bot Started")
        print(f"Symbol: {CFG.symbol}")
        print(f"Execution TF: {CFG.exec_tf}")
        print(f"Confirmation TF: {CFG.confirm_tf}")
        print(f"HTF: {CFG.htf_tf}")
        print(f"Contracts: {CFG.contracts}")
        print(f"Trade enabled: {CFG.trade_enabled}")
        print(f"Tick size: {CFG.tick_size}")
        print("===================================")

        await self.maybe_print_order_signature(suite)

        try:
            while True:
                self.reset_daily_counters_if_needed()

                raw_exec_df = await suite.data.get_data(CFG.exec_tf)
                raw_confirm_df = await suite.data.get_data(CFG.confirm_tf)
                raw_htf_df = await suite.data.get_data(CFG.htf_tf)

                exec_df = normalize_dataframe(raw_exec_df)
                confirm_df = normalize_dataframe(raw_confirm_df)
                htf_df = normalize_dataframe(raw_htf_df)

                if not enough_data(exec_df, confirm_df, htf_df, min_len=40):
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                exec_df = add_indicators(exec_df)
                confirm_df = add_indicators(confirm_df)
                htf_df = add_indicators(htf_df)

                if not enough_data(exec_df, confirm_df, htf_df, min_len=40):
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                # Only evaluate once per new execution bar.
                if not self.is_new_exec_bar(exec_df):
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                is_flat = await self.get_symbol_flat_status(suite)
                signal = get_signal(exec_df, confirm_df, htf_df)
                price = float(latest(exec_df)["close"])
                bias = htf_bias(htf_df)

                print(
                    f"{datetime.now()} | "
                    f"{CFG.symbol} | "
                    f"Price: {price} | "
                    f"HTF Bias: {bias} | "
                    f"Signal: {signal} | "
                    f"Flat: {is_flat} | "
                    f"Trades: {self.trades_today}"
                )

                if not signal:
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                if not is_flat:
                    print("PASS: Existing position detected for this instrument.")
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                if not await self.risk_ok(suite):
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                entry, stop, target, risk = build_trade_plan(signal, exec_df)

                if not valid_trade_plan(signal, entry, stop, target, risk):
                    await asyncio.sleep(CFG.poll_seconds)
                    continue

                print("===================================")
                print(f"MANDY PRESSURE PLAY SIGNAL: {signal}")
                print(f"Entry:  {entry}")
                print(f"Stop:   {stop}")
                print(f"Target: {target}")
                print(f"Risk:   {risk} points")
                print("===================================")

                if CFG.trade_enabled:
                    try:
                        order = await self.place_bracket_order_safe(
                            suite=suite,
                            signal=signal,
                            entry=entry,
                            stop=stop,
                            target=target,
                        )

                        print(f"Order sent: {order}")
                        self.trades_today += 1

                    except Exception as exc:
                        print(f"ORDER ERROR: {exc}")

                else:
                    print("PAPER MODE: Signal detected, no order sent.")
                    self.trades_today += 1

                await asyncio.sleep(CFG.poll_seconds)

        finally:
            await suite.disconnect()
            print("Bot disconnected.")


if __name__ == "__main__":
    bot = MandyPressureBot()
    asyncio.run(bot.run())
