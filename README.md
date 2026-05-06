# Mandy's Pressure Play Bot 🚀

Intraday futures scalping bot for **NQ, ES, MGC, SIL, MNQ, MES** using Multi-Timeframe Pressure Play setups.

## Features

✅ **Multi-Timeframe Analysis**
- Execution: 3min or 5min
- Confirmation: 1min
- Higher Timeframe Bias: 15min

✅ **Risk Management**
- Daily loss limits
- Max trades per day
- Risk/Reward ratio enforcement (1.5:1)
- Intelligent stop loss placement

✅ **Safety Features**
- Paper trading mode by default
- Position validation before order placement
- Bar-level throttling prevents duplicate signals
- Safe object/dict field access across SDK versions

✅ **Debug Capabilities**
- Order signature inspection
- Detailed logging
- PnL tracking

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Project X credentials
```

### 3. Run in Paper Mode (Default)

```bash
python mandy_bot_debugged.py
```

This will:
- Start the bot in signal-only mode
- Print detected signals to console
- NOT place actual orders

### 4. Enable Live Trading

**⚠️ AFTER paper testing with 20+ signals:**

Edit `mandy_bot_debugged.py`:

```python
CFG = Config()
CFG.trade_enabled = True  # Set to True
```

Then restart:

```bash
python mandy_bot_debugged.py
```

## Configuration

Edit the `Config` class in `mandy_bot_debugged.py`:

```python
@dataclass
class Config:
    symbol: str = "MNQ"              # Change to ES, NQ, etc.
    exec_tf: str = "5min"           # Execution timeframe
    confirm_tf: str = "1min"        # Confirmation timeframe
    htf_tf: str = "15min"           # Higher timeframe bias
    
    contracts: int = 1              # Position size
    max_trades_per_day: int = 3     # Daily trade limit
    max_daily_loss: float = 250.00  # Daily stop-out loss
    
    stop_buffer_points: float = 2.0 # Stop loss buffer
    target_rr: float = 1.5          # Risk/reward ratio
    
    tick_size: float = 0.25         # Price rounding
    trade_enabled: bool = False     # KEEP FALSE FOR TESTING
```

## How It Works

### Pressure Play Setup

1. **HTF Bias Check**: 15min candle confirms direction (EMA > MA21)
2. **Not Spaghetti**: MA cluster is tight (< 8 points)
3. **Structure Hold**: Price pulled into MAs but bounced
4. **EMA Cross**: EMA5 crosses above/below MA7
5. **Lower TF Confirm**: 1min confirms alignment (close > EMA5 > MA7)

### Entry Rules

**LONG:**
- HTF Bias = BULLISH
- EMA5 crosses above MA7 on execution timeframe
- Lower timeframe confirms (close > EMA5 > MA7)

**SHORT:**
- HTF Bias = BEARISH
- EMA5 crosses below MA7 on execution timeframe
- Lower timeframe confirms (close < EMA5 < MA7)

### Stop/Target Calculation

- **Stop**: Min(MA7, recent 8-bar low) ± buffer
- **Risk**: Entry - Stop
- **Target**: Entry ± (Risk × 1.5)

## Debugging

### View Order Method Signature

The bot prints the expected order method signature on startup:

```
place_bracket_order signature: (contract_id, side, size, entry_price, stop_loss_price, take_profit_price)
```

This helps verify SDK compatibility.

### Check Daily Counters

The bot logs:
- Signals detected (with reason)
- Position status
- Daily PnL
- Trades today
- Risk validations

### Paper Mode Testing

Always start here:

```bash
# Keep trade_enabled = False
python mandy_bot_debugged.py

# Monitor console output for:
# - Signal generation
# - Entry/Stop/Target levels
# - Risk checks
```

Aim for **20+ paper signals** before going live.

## Safety Checks

✅ **Position Validation**: Checks current position before order
✅ **Risk Limits**: Rejects trades outside min/max risk range
✅ **Daily Loss Stop**: Prevents trading after max daily loss
✅ **Time Filter**: Optional trading hours restriction
✅ **Max Trades**: Daily trade limit enforcement
✅ **Bar Throttle**: Prevents duplicate signals on same bar

## Troubleshooting

### "PASS: Could not retrieve positions"
- SDK connection issue
- Check Project X credentials in `.env`
- Verify API key has permissions

### "WARN: Daily PnL unavailable"
- Some SDK versions don't expose PnL
- Bot will still work (max daily loss check skipped)
- Not critical in paper mode

### No signals generated
- Verify data is loading (check API)
- Confirm symbol is tradeable
- Check HTF bias (may be neutral)
- Verify moving averages are aligned

## Support

For issues or questions:
1. Check console output for error messages
2. Verify `.env` credentials
3. Test with `debug_order_signature = True`
4. Run in paper mode first

---

**Happy trading! 📈**
