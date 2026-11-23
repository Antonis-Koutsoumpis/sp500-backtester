# S&P 500 Backtester (and other indices)

Interactive Streamlit app to backtest investment strategies on major stock
market indices using monthly historical data that is **updated automatically
every day**.

This repository is linked to two versions of the app, with the same calculations and data:

- **Web app (works on phones and desktop):** [S&P 500 Backtester (GitHub Pages)](https://antonis-koutsoumpis.github.io/sp500-backtester/). It can be installed on a phone's home screen (iPhone: *Share → Add to Home Screen*; Android: menu ⋮ → *Install app*) and works offline with the last data it loaded.
- **Streamlit app:** [S&P 500 Backtester](https://sp500-backtester.streamlit.app/).

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
- Opens on the full historical chart of the selected index (S&P 500 by default)
- Time window chosen on the chart: fixed lengths of 5–50 years, full history or
  any custom start and end. The main chart shows only the selected window; a
  thin full-history strip below it shows where the window lies — drag or tap
  there to move it, drag across the main chart to zoom in, or use the slider
  and ±1 year buttons. Shows the window's total growth and CAGR
- Optional comparisons for every scenario, using the same deposits: a fixed
  annual return (positive or negative), and cash savings at 0% interest that
  lose value to the inflation of the index's currency area
- Optional trend line on the historical chart: linear, polynomial (degree 2–5),
  logarithmic or exponential, fitted over the full history or the selected
  window, with its formula and R²
- Plots equity curve and yearly-returns chart (linear or log Y-axis)
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
- `docs/` — web app for GitHub Pages (HTML, CSS, JavaScript, Plotly); same calculations as the Streamlit app
- `scripts/export_web.py` — copies the data to `docs/data/` (run by the daily workflow after the update)
- `indices.py` — list of indices, their tickers and descriptions
- `scripts/update_data.py` — daily data updater
- `data/index_prices.csv`, `data/metadata.json` — generated data
- `.github/workflows/update-data.yml` — daily schedule
- `requirements.txt` — app dependencies; `scripts/requirements-update.txt` — updater dependencies

## Web app (GitHub Pages)

The web app in `docs/` runs entirely in the browser. The daily workflow copies the
data to `docs/data/` (with `scripts/export_web.py`), so both apps always use the same data.

To publish it: in the repository on GitHub go to **Settings → Pages**, choose
**Deploy from a branch**, branch **main**, folder **/docs**, and save.
To try it locally: `cd docs && python -m http.server`, then open http://localhost:8000.

## Running locally

```bash
pip install -r requirements.txt
streamlit run sp500_simulator.py

# refresh the data yourself
pip install -r scripts/requirements-update.txt
python scripts/update_data.py
```

## License

Free for personal and other noncommercial use under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use is not allowed without permission. Market and inflation data come from Yahoo Finance, FRED, Eurostat and ONS and remain under their own terms.
