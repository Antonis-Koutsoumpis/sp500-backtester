"""Daily updater for data/index_prices.csv.

For every index in indices.py it downloads daily closing prices from Yahoo
Finance, keeps one row per month (the last trading day of that month) plus the
most recent trading day for the current month, and computes an
inflation-adjusted series with the CPI of the index's currency area.

Inflation-adjusted values are expressed in today's money: for the latest month
they equal the nominal value, earlier months are scaled up by
CPI(latest) / CPI(that month). Months after the latest published CPI use the
last available CPI (CPI is released with a lag of 2-6 weeks).

If an index or CPI download fails, the rows already in the CSV for that index
are kept, so a temporary outage never wipes data.

Run from the repository root:  python scripts/update_data.py
"""

import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from indices import INDICES, CPI_NAMES  # noqa: E402

DATA_DIR = ROOT / "data"
OUT_CSV = DATA_DIR / "index_prices.csv"
META_JSON = DATA_DIR / "metadata.json"
SP500_SEED = ROOT / "s&p500_19271231_20261014.csv"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/csv,application/json,text/plain,*/*",
}

# CPI sources per currency area, in order of preference. All candidates that
# download successfully are chain-linked, so a long but discontinued series can
# supply history while a current one supplies the latest months.
# Sources: BLS (via DBnomics), BIS long CPI series, Eurostat, UK ONS, FRED.
# FRED often times out from cloud runners, so it is only one option among
# several and gets a short timeout.
CPI_SOURCES = {
    "US": [("dbnomics", "BLS/cu/CUUR0000SA0"), ("bis", "US"),
           ("fred", "CPIAUCNS")],
    "EA": [("eurostat", "M.I15.CP00.EA"), ("eurostat", "M.I25.CP00.EA"),
           ("dbnomics", "Eurostat/prc_hicp_midx/M.I15.CP00.EA"), ("bis", "XM"),
           ("fred", "CP0000EZ19M086NEST")],
    "UK": [("ons", "d7bt/mm23"), ("bis", "GB"), ("fred", "GBRCPIALLMINMEI")],
    "JP": [("bis", "JP"), ("dbnomics", "OECD/DSD_PRICES@DF_PRICES_ALL/JPN.M.N.CPI.IX._T.N._Z"),
           ("fred", "JPNCPIALLMINMEI")],
}


def log(msg):
    print(msg, flush=True)


def http_get(url, tries=2, timeout=30):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


# ---------------------------------------------------------------------------
# CPI
# ---------------------------------------------------------------------------
def cpi_fred(series_id):
    txt = http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                   tries=1, timeout=20)
    df = pd.read_csv(io.StringIO(txt))
    date_col = df.columns[0]
    s = pd.to_numeric(df[series_id], errors="coerce")
    s.index = pd.to_datetime(df[date_col]).dt.to_period("M")
    return s.dropna()


def cpi_eurostat(key):
    url = (
        "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/"
        f"prc_hicp_midx/{key}?format=SDMX-CSV"
    )
    df = pd.read_csv(io.StringIO(http_get(url)))
    s = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    s.index = pd.PeriodIndex(df["TIME_PERIOD"], freq="M")
    return s.dropna().sort_index()


def cpi_dbnomics(series_code):
    url = (f"https://api.db.nomics.world/v22/series/{series_code}"
           "?observations=1&format=json")
    doc = json.loads(http_get(url, timeout=60))["series"]["docs"][0]
    s = pd.Series(pd.to_numeric(pd.Series(doc["value"]), errors="coerce").to_numpy(),
                  index=pd.PeriodIndex(doc["period"], freq="M"))
    return s.dropna().sort_index()


def _sdmx_csv_series(txt):
    df = pd.read_csv(io.StringIO(txt))
    cols = {c.upper().split(":")[0]: c for c in df.columns}
    s = pd.to_numeric(df[cols["OBS_VALUE"]], errors="coerce")
    s.index = pd.PeriodIndex(df[cols["TIME_PERIOD"]].astype(str), freq="M")
    return s.dropna().sort_index()


def cpi_bis(country):
    """BIS long consumer price series (index, 2010 = 100)."""
    urls = [
        f"https://stats.bis.org/api/v1/data/WS_LONG_CPI/M.{country}.628/all?format=csv",
        "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/"
        f"M.{country}.628?format=csv",
    ]
    last = None
    for url in urls:
        try:
            return _sdmx_csv_series(http_get(url, timeout=60))
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def cpi_ons(path):
    url = (
        "https://www.ons.gov.uk/generator?format=csv&uri=/economy/"
        f"inflationandpriceindices/timeseries/{path}"
    )
    rows = []
    for line in http_get(url).splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2 and re.fullmatch(r"\d{4} [A-Z]{3}", parts[0]):
            rows.append((pd.Period(datetime.strptime(parts[0], "%Y %b"), "M"),
                         float(parts[1])))
    if not rows:
        raise ValueError("no monthly rows found")
    return pd.Series(dict(rows)).sort_index()


def chain_link(series_list):
    """Combine several CPI series: the one with the most recent data is the
    base; the others extend it backwards (and forwards) by ratio-linking."""
    series_list = sorted(series_list, key=lambda s: s.index.max(), reverse=True)
    base = series_list[0].copy()
    for other in series_list[1:]:
        overlap = base.index.intersection(other.index)
        if len(overlap) == 0:
            continue
        first, last = overlap.min(), overlap.max()
        earlier = other[other.index < base.index.min()]
        if len(earlier):
            base = pd.concat([earlier * base[first] / other[first], base])
        later = other[other.index > base.index.max()]
        if len(later):
            base = pd.concat([base, later * base[last] / other[last]])
    return base.sort_index()


def load_cpi(area):
    fetchers = {"fred": cpi_fred, "eurostat": cpi_eurostat, "ons": cpi_ons,
                "dbnomics": cpi_dbnomics, "bis": cpi_bis}
    got, used = [], []
    for kind, key in CPI_SOURCES[area]:
        try:
            s = fetchers[kind](key)
            log(f"  CPI {area}: {kind}:{key} ok, {s.index.min()} -> {s.index.max()}")
            got.append(s)
            used.append(f"{kind}:{key}")
        except Exception as e:  # noqa: BLE001
            log(f"  CPI {area}: {kind}:{key} failed ({e})")
    if not got:
        return None, []
    return chain_link(got), used


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
def fetch_daily_close(ticker):
    last = None
    for i in range(3):
        try:
            h = yf.Ticker(ticker).history(period="max", interval="1d",
                                          auto_adjust=False, actions=False)
            s = h["Close"].dropna()
            if s.empty:
                raise ValueError("empty history")
            idx = s.index
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_localize(None)
            s.index = idx.normalize()
            return s[s > 0].sort_index()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise last


def to_monthly(daily):
    """Last trading day of each month (the current month's row is the latest
    trading day so far)."""
    df = daily.to_frame("nominal")
    df["ym"] = df.index.to_period("M")
    m = df.groupby("ym").tail(1)
    m.index.name = "date"
    return m.reset_index()[["date", "nominal"]]


def load_sp500_seed():
    df = pd.read_csv(SP500_SEED, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y")
    return df[["date", "nominal"]].dropna()


def build_index(idx_id, cfg, cpi_cache):
    # Use the candidate ticker with the longest history.
    daily, ticker_used = None, None
    for t in cfg["tickers"]:
        try:
            s = fetch_daily_close(t)
            log(f"  {t}: {len(s)} days, {s.index.min().date()} -> "
                f"{s.index.max().date()}")
            if daily is None or s.index.min() < daily.index.min():
                daily, ticker_used = s, t
        except Exception as e:  # noqa: BLE001
            log(f"  {t}: failed ({e})")
    if daily is None:
        return None, None
    log(f"  using {ticker_used}")

    monthly = to_monthly(daily)

    # S&P 500: if Yahoo's history starts later than the original hand-made
    # file, use that file for the missing early months.
    if idx_id == "sp500" and SP500_SEED.exists():
        seed = load_sp500_seed()
        first_month = monthly["date"].min().to_period("M")
        early = seed[seed["date"].dt.to_period("M") < first_month]
        if len(early):
            log(f"  prepending {len(early)} months from the original S&P 500 file")
            monthly = pd.concat([early, monthly], ignore_index=True)

    area = cfg["cpi"]
    if area not in cpi_cache:
        cpi_cache[area] = load_cpi(area)
    cpi, cpi_used = cpi_cache[area]
    monthly.insert(0, "index", idx_id)
    if cpi is None:
        log("  no CPI available -> nominal only")
        monthly["inflation_adjusted"] = float("nan")
        return monthly, {
            "ticker": ticker_used,
            "first_date": str(monthly["date"].min().date()),
            "last_date": str(monthly["date"].max().date()),
            "first_real_date": None, "cpi": CPI_NAMES[area],
            "cpi_sources": [], "cpi_last_month": None,
        }

    months = monthly["date"].dt.to_period("M")
    full_range = pd.period_range(min(cpi.index.min(), months.min()),
                                 max(cpi.index.max(), months.max()), freq="M")
    cpi_full = cpi.reindex(full_range).ffill()  # carry last CPI forward
    cpi_at = cpi_full.reindex(months).to_numpy()
    ref = cpi_full[months.max()]
    monthly["inflation_adjusted"] = monthly["nominal"] * ref / cpi_at

    meta = {
        "ticker": ticker_used,
        "first_date": str(monthly["date"].min().date()),
        "last_date": str(monthly["date"].max().date()),
        "first_real_date": str(
            monthly.loc[monthly["inflation_adjusted"].notna(), "date"].min().date()),
        "cpi": CPI_NAMES[area],
        "cpi_sources": cpi_used,
        "cpi_last_month": str(cpi.index.max()),
    }
    return monthly, meta


def main():
    DATA_DIR.mkdir(exist_ok=True)
    old = pd.read_csv(OUT_CSV, parse_dates=["date"]) if OUT_CSV.exists() else None
    old_meta = json.loads(META_JSON.read_text()) if META_JSON.exists() else {}

    frames, meta, failed = [], {}, []
    cpi_cache = {}
    for idx_id, cfg in INDICES.items():
        log(f"{idx_id} ({cfg['name']})")
        df, m = build_index(idx_id, cfg, cpi_cache)
        if df is None:
            failed.append(idx_id)
            if old is not None and (old["index"] == idx_id).any():
                log("  -> keeping previous data")
                frames.append(old[old["index"] == idx_id])
                meta[idx_id] = old_meta.get("indices", {}).get(idx_id, {})
            continue
        frames.append(df)
        meta[idx_id] = m

    if not frames:
        log("No data at all — leaving files untouched.")
        sys.exit(1)

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["nominal"] = out["nominal"].round(4)
    out["inflation_adjusted"] = out["inflation_adjusted"].round(4)
    out.to_csv(OUT_CSV, index=False)

    META_JSON.write_text(json.dumps({
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "failed_last_run": failed,
        "indices": meta,
    }, indent=2) + "\n")
    log(f"Wrote {len(out)} rows for {out['index'].nunique()} indices. "
        f"Failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
