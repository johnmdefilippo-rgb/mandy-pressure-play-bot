# Changelog

## v1.1.0 (2026-05-06) - Debugged Release

### 🔧 Critical Fixes

1. **Bar ID Detection Improved**
   - Better timestamp column detection (timestamp, time, t, datetime, etc.)
   - Fallback to index if not RangeIndex
   - Last-resort OHLC hash to prevent bar ID locking

2. **Safe Field Access (`get_field` utility)**
   - Safely reads fields from objects OR dicts
   - Doesn't treat `0` as missing value
   - Multiple name variants for SDK compatibility

3. **Position Checking Robustness**
   - Contract ID matching
   - Symbol substring matching fallback
   - Handles different SDK position field names
   - Safe zero-value comparison

4. **PnL Handling**
   - Tries multiple PnL field names (daily_pnl, dailyPnl, realizedPnl, etc.)
   - Returns None if unavailable (doesn't crash)
   - Explicit warning when unavailable

5. **Safe Bracket Order Placement**
   - Inspects method signature before calling
   - Tries both snake_case and camelCase parameter names
   - Handles **kwargs gracefully
   - Better error messages

6. **DataFrame Indexing**
   - `latest()` and `previous()` still simple but documented
   - Used only after `enough_data()` checks
   - Safe because of 40-row minimum requirement

### 📝 Documentation

- Added comprehensive README.md
- Added setup/configuration guide
- Added troubleshooting section
- Added safety features documentation

### 🚀 Next Steps for Users

1. Clone/fork repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `.env` with Project X credentials
4. Run in paper mode (default)
5. Monitor 20+ signals before enabling live trading

---

## v1.0.0 (Original)

- Initial release
- Pressure Play setup logic
- Multi-timeframe analysis
- Basic risk management
