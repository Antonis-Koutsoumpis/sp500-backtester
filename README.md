# S&P 500 Backtester (and other indices)

Interactive Streamlit app to backtest investment strategies on major stock
market indices using monthly historical data that is **updated automatically
every day**.

This repository is linked to the Streamlit app [S&P 500 Backtester](https://sp500-backtester.streamlit.app/).

## What it does

- Choose an index (each one is explained in the app):
  S&P 500, S&P 500 Equal Weight, Nasdaq 100, Dow Jones Industrial Average,
  Total U.S. Stock Market, MSCI World, STOXX Europe 600, Euro Stoxx 50,
  FTSE 100, Nikkei 225, MSCI Emerging Markets
- Simulates lump sum, DCA (dollar-cost averaging), and escalated DCA strategies
- Users choose: initial capital, yearly contributions, contribution escalation (%),
  start date, and duration
- Runs the simulation in **nominal** or **inflation-adjusted** terms (user toggle)
- Outputs: final value, total invested, net gain, CAGR, IRR, max drawdown
- Plots equity curve and drawdown chart (linear or log Y-axis)
- Compares up to 3 scenarios side by side
- Exports results as CSV

## Important notes

- All results are **price return only, excludes dividends**.
- Returns are in each index's own currency (USD, EUR, GBP or JPY).
  Inflation adjustment uses the inflation of that currency area.
- MSCI World and MSCI Emerging Markets use the iShares ETFs (URTH from 2012,
  EEM from 2003) because the indices themselves are not freely available.

## Data

`data/index_prices.csv` holds one row per index per month (the last trading
day of the month), plus a row for the most recent trading day:

| column | meaning |
|---|---|
| `index` | index id (see `indices.py`) |
| `date` | trading day (YYYY-MM-DD) |
| `nominal` | closing level / price |
| `inflation_adjusted` | value in today's money (latest month = nominal) |

It is rebuilt every day by the GitHub Action
`.github/workflows/update-data.yml`, which runs `scripts/update_data.py`:

- **Prices:** Yahoo Finance daily closes (via `yfinance`).
- **Inflation:** US CPI-U (FRED `CPIAUCNS`), euro-area HICP (FRED / Eurostat),
  UK CPI (ONS / FRED), Japan CPI (FRED). CPI is published with a lag, so the
  most recent month(s) use the latest available figure.
- If a download fails, the previous data for that index is kept.
- `data/metadata.json` records the last update, which ticker and CPI series
  were used, and the data range of each index.

The workflow can also be started by hand from the **Actions** tab
(“Update index data” → “Run workflow”).

The original hand-made S&P 500 file `s&p500_19271231_20261014.csv`
(from https://www.macrotrends.net/2324/sp-500-historical-chart-data) is no
longer used by the app; the updater only uses it as a fallback for early
S&P 500 history if Yahoo's data were ever to start later than 1927.

## Files

- `sp500_simulator.py` — main Streamlit app
- `indices.py` — list of indices, their tickers and descriptions
- `scripts/update_data.py` — daily data updater
- `data/index_prices.csv`, `data/metadata.json` — generated data
- `.github/workflows/update-data.yml` — daily schedule
- `requirements.txt` — app dependencies; `scripts/requirements-update.txt` — updater dependencies

## Running locally

```bash
pip install -r requirements.txt
streamlit run sp500_simulator.py

# refresh the data yourself
pip install -r scripts/requirements-update.txt
python scripts/update_data.py
```
