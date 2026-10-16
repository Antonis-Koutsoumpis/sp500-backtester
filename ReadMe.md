# S&P 500 Backtester

Interactive Streamlit app to backtest S&P 500 investment strategies against
historical monthly data from 1927 to today.

## What it does

- Simulates lump sum, DCA (dollar-cost averaging), and escalated DCA strategies
- Users choose: initial capital, yearly contributions, contribution escalation (%),
  start date, and duration
- Runs the simulation in **nominal** or **inflation-adjusted** terms (user toggle)
- Outputs: final value, total invested, net gain, CAGR, IRR, max drawdown
- Plots equity curve and drawdown chart (linear or log Y-axis)
- Compares up to 3 scenarios side by side
- Exports results as CSV

## Important note

All results are **price return only, excludes dividends**.

## Data source

Historical S&P 500 values obtained from:
https://www.macrotrends.net/2324/sp-500-historical-chart-data

## Files

- `sp500_simulator.py` — main Streamlit app
- `s&p500_19271231_20261014.csv` — monthly index data (nominal + inflation-adjusted)
- `requirements.txt` — Python dependencies

## Running locally

```bash
pip install -r requirements.txt
streamlit run sp500_simulator.py