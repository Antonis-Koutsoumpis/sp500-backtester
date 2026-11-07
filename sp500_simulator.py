import json
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

from indices import INDICES, CURRENCY_SYMBOL

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Index Backtester",
    page_icon="📈",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
DATA_FILE = Path(__file__).parent / "data" / "index_prices.csv"
META_FILE = Path(__file__).parent / "data" / "metadata.json"


@st.cache_data(ttl=3600)
def load_all(path, mtime):
    """Load the long-format CSV (index, date, nominal, inflation_adjusted).
    `mtime` is only part of the cache key, so a new daily file is picked up."""
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values(["index", "date"]).reset_index(drop=True)


@st.cache_data(ttl=3600)
def load_meta(path, mtime):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


ALL = load_all(str(DATA_FILE), DATA_FILE.stat().st_mtime)
META = load_meta(str(META_FILE), META_FILE.stat().st_mtime if META_FILE.exists() else 0)
AVAILABLE = [k for k in INDICES if (ALL["index"] == k).any()]


def index_frame(index_id, mode):
    """Monthly series for one index, restricted to rows that have a value
    for the chosen mode, with monthly returns."""
    col = "nominal" if mode == "Nominal" else "inflation_adjusted"
    d = ALL[ALL["index"] == index_id].dropna(subset=[col]).copy()
    d = d.reset_index(drop=True)
    d["ret_nom"] = d["nominal"].pct_change()
    d["ret_real"] = d["inflation_adjusted"].pct_change()
    return d


# ---------------------------------------------------------------------------
# Sidebar — index and global settings
# ---------------------------------------------------------------------------
st.sidebar.header("Index")

index_id = st.sidebar.selectbox(
    "Choose an index",
    options=AVAILABLE,
    index=AVAILABLE.index("sp500") if "sp500" in AVAILABLE else 0,
    format_func=lambda k: INDICES[k]["name"],
    help="\n\n".join(f"**{INDICES[k]['name']}** — {INDICES[k]['short']}"
                     for k in AVAILABLE),
)
IDX = INDICES[index_id]
IDX_META = META.get("indices", {}).get(index_id, {})
CUR = CURRENCY_SYMBOL.get(IDX["currency"], "")

st.title(f"📈 {IDX['name']} Backtester")

# ---------------------------------------------------------------------------
# Collapsible instructions
# ---------------------------------------------------------------------------
with st.expander("ℹ️ What this app does — click to expand", expanded=False):
    st.markdown(
        """
**What this app does**

This tool lets you simulate how a hypothetical investment in a stock market
index would have performed if you had started at any month in its history —
from the S&P 500 (back to 1927) to the Nikkei 225, European and emerging-market
indices. You can model a single lump sum, regular contributions, or a mix of
both — and compare up to three scenarios side by side. The data is refreshed
automatically every day.

**How to use it**

1. In the sidebar, **choose an index** — a short description of each is shown
   on the page — and whether you want results in *Nominal* or
   *Inflation-adjusted* terms.
2. Set up one or more scenarios:
   - **Lump sum** — invest once at the start, nothing after.
   - **DCA** (Dollar-Cost Averaging) — invest the same amount on a regular schedule.
   - **Escalated DCA** — invest on a regular schedule, increasing the amount
     each year by your escalation percentage.
   - **Custom** — set initial capital, contributions, and escalation freely.
3. Pick the **time window** on the historical chart: choose a length
   (5–30 years, full history or custom), then drag on the chart or use the
   slider and ◀ ▶ buttons to move it. The window's total growth and CAGR are
   shown right below the chart. (Untick *Use the time window from the chart*
   in a scenario to type its own start date and duration instead.)
4. Choose the **contribution frequency**: yearly, quarterly, or monthly.
5. The app shows the **final portfolio value**, the **total amount invested**,
   the **net gain**, the annualized return (CAGR and/or IRR), and the
   **maximum drawdown** — plus a return chart, a yearly-returns bar chart,
   and a results table.
6. Download any scenario's monthly data as a CSV if you want to explore further.

**What the outputs mean**

- **Final value** — portfolio value at the end of the chosen period.
- **Invested** — total capital you put in (initial + all contributions).
- **Net gain** — final value minus invested.
- **CAGR** — compound annual growth rate (only shown for pure lump sum).
- **IRR** — internal rate of return; the fair annualized return when
  contributions exist. Accounts for the timing of each cash flow.
- **Max drawdown** — the largest peak-to-trough decline during the period.

**Important**

All results are **price return only and exclude dividends**. Returns are in
each index's own currency (e.g. yen for the Nikkei 225, euros for the Euro
Stoxx 50); inflation adjustment uses the inflation of that currency area.
Each index has its own data range, shown in the index description.
        """
    )

# ---------------------------------------------------------------------------
# Sidebar — global settings
# ---------------------------------------------------------------------------
st.sidebar.header("Global settings")

value_mode = st.sidebar.radio(
    "Value mode",
    options=["Nominal", "Inflation-adjusted"],
    index=0,
    help=(
        "**Nominal** — actual currency amounts of the day.\n\n"
        "**Inflation-adjusted** — expresses past values in start-of-period "
        "purchasing power, i.e. it assumes inflation didn't exist, so you can "
        "compare returns across different eras in 'real' terms. Uses the "
        "inflation of the index's currency area."
    ),
)

log_scale = st.sidebar.radio(
    "Y-axis scale (charts)",
    options=["Linear", "Log"],
    index=0,
    help="Log scale makes equal percentage moves look equally large — "
         "useful for long histories.",
)

df = index_frame(index_id, value_mode)
if len(df) < 2:
    st.warning(
        f"No {value_mode.lower()} data is available for {IDX['name']} at the "
        "moment. Please choose *Nominal* or another index."
    )
    st.stop()
MIN_DATE = df["date"].min()
MAX_DATE = df["date"].max()

# ---------------------------------------------------------------------------
# Historical chart and time window
# ---------------------------------------------------------------------------
# The window is kept in st.session_state as two month strings ("YYYY-MM"):
# win_start and win_end. It changes through the window-length buttons, the
# slider, the ◀ ▶ buttons, a click on the chart (moves the window there) or a
# horizontal drag across the chart (sets a custom start and end).
ss = st.session_state
VALUE_COL = "nominal" if value_mode == "Nominal" else "inflation_adjusted"
MONTHS = df["date"].dt.to_period("M").astype(str).tolist()
N_MONTHS = len(MONTHS)
PRESET_YEARS = [5, 10, 15, 20, 25, 30]
PRESETS = [f"{n} years" for n in PRESET_YEARS if 12 * n <= N_MONTHS]
WINDOW_OPTIONS = PRESETS + ["Full history", "Custom"]


def month_label(m):
    return pd.Period(m, "M").strftime("%b %Y")


def preset_months(choice):
    return 12 * int(choice.split()[0]) if choice in PRESETS else None


def month_index(ts):
    """Position in MONTHS of the month containing ts (clamped to the data)."""
    m = str(pd.Timestamp(ts).to_period("M"))
    if m <= MONTHS[0]:
        return 0
    if m >= MONTHS[-1]:
        return N_MONTHS - 1
    return next(i for i, x in enumerate(MONTHS) if x >= m)


def to_timestamp(x):
    if isinstance(x, (int, float)):
        return pd.Timestamp(x, unit="ms")
    return pd.Timestamp(x)


if ss.get("win_len") not in WINDOW_OPTIONS:
    ss.win_len = "20 years" if "20 years" in PRESETS else "Full history"
if ss.get("win_start") not in MONTHS or ss.get("win_end") not in MONTHS:
    _L = preset_months(ss.win_len) or N_MONTHS
    ss.win_start, ss.win_end = MONTHS[N_MONTHS - _L], MONTHS[-1]
ss.setdefault("chart_nonce", 0)

# Apply a click or drag made on the chart in the previous interaction.
_chart_key = f"hist_chart_{ss.chart_nonce}"
try:
    _sel = ss[_chart_key]["selection"] if _chart_key in ss else None
except Exception:
    _sel = None
if _sel:
    _boxes = _sel.get("box") or []
    _points = _sel.get("points") or []
    _si, _ei = MONTHS.index(ss.win_start), MONTHS.index(ss.win_end)
    _applied = False
    if _boxes and _boxes[-1].get("x"):
        _xs = [to_timestamp(x) for x in _boxes[-1]["x"]]
        _a, _b = month_index(min(_xs)), month_index(max(_xs))
        if ss.win_len in PRESETS:
            # Fixed length: the drag says where the window should start.
            _len = preset_months(ss.win_len) - 1
            _a = min(_a, N_MONTHS - 1 - _len)
            ss.win_start, ss.win_end = MONTHS[_a], MONTHS[_a + _len]
        else:
            # Custom / full history: the drag sets both start and end.
            if _b <= _a:
                _b = min(_a + 1, N_MONTHS - 1)
                _a = _b - 1
            ss.win_len = "Custom"
            ss.win_start, ss.win_end = MONTHS[_a], MONTHS[_b]
        _applied = True
    elif _points and _points[0].get("x") is not None:
        _a = month_index(to_timestamp(_points[0]["x"]))
        if ss.win_len == "Full history":
            ss.win_len = "Custom"
            ss.win_start, ss.win_end = MONTHS[min(_a, N_MONTHS - 2)], MONTHS[-1]
        else:
            _len = preset_months(ss.win_len) - 1 if ss.win_len in PRESETS else _ei - _si
            _a = min(_a, N_MONTHS - 1 - _len)
            ss.win_start, ss.win_end = MONTHS[_a], MONTHS[_a + _len]
        _applied = True
    if _applied:
        ss.chart_nonce += 1  # a fresh chart widget clears the old selection
        _chart_key = f"hist_chart_{ss.chart_nonce}"


def _slider_fixed_changed():
    v = ss.get("win_slider_fixed")
    if isinstance(v, str) and v in MONTHS:
        ss.win_start = v


def _shift_window(months):
    si_, ei_ = MONTHS.index(ss.win_start), MONTHS.index(ss.win_end)
    months = max(-si_, min(months, N_MONTHS - 1 - ei_))
    ss.win_start, ss.win_end = MONTHS[si_ + months], MONTHS[ei_ + months]


st.subheader(f"Historical chart — {IDX['name']}")

st.radio(
    "Time window",
    options=WINDOW_OPTIONS,
    key="win_len",
    horizontal=True,
    help=(
        "**Fixed length (5–30 years):** drag on the chart starting where you "
        "want the window to begin — it moves there and keeps its length. "
        "Fine-tune with the slider or the ◀ ▶ buttons.\n\n"
        "**Custom:** drag across the chart from the start to the end date you "
        "want, or use the two-handle slider.\n\n"
        "The scenarios in the sidebar use this window unless you untick "
        "*Use the time window from the chart*."
    ),
)

# Resolve the window for the chosen length.
si, ei = MONTHS.index(ss.win_start), MONTHS.index(ss.win_end)
WIN_MONTHS = preset_months(ss.win_len)
if WIN_MONTHS:
    si = min(si, N_MONTHS - WIN_MONTHS)
    ei = si + WIN_MONTHS - 1
elif ss.win_len == "Full history":
    si, ei = 0, N_MONTHS - 1
elif ei <= si:
    ei = min(si + 1, N_MONTHS - 1)
    si = ei - 1
ss.win_start, ss.win_end = MONTHS[si], MONTHS[ei]

slider_col, back_col, fwd_col = st.columns([8, 1, 1], vertical_alignment="bottom")
with slider_col:
    if WIN_MONTHS:
        ss.win_slider_fixed = ss.win_start
        st.select_slider(
            "Window start",
            options=MONTHS[: N_MONTHS - WIN_MONTHS + 1],
            key="win_slider_fixed",
            format_func=month_label,
            on_change=_slider_fixed_changed,
        )
    elif ss.win_len == "Custom":
        # Two-handle sliders take their shape from `value`, so the window is
        # passed in directly; the key changes whenever the window is changed
        # elsewhere (chart, buttons) so the slider follows it.
        _rng = st.select_slider(
            "Window start and end",
            options=MONTHS,
            value=(ss.win_start, ss.win_end),
            key=f"win_slider_range_{ss.win_start}_{ss.win_end}",
            format_func=month_label,
        )
        if tuple(_rng) != (ss.win_start, ss.win_end) and _rng[0] != _rng[1]:
            ss.win_start, ss.win_end = _rng
            si, ei = MONTHS.index(_rng[0]), MONTHS.index(_rng[1])
    else:
        st.caption("Showing the full history. Choose a window length, or drag "
                   "across the chart to select a period.")
if ss.win_len != "Full history":
    back_col.button("◀ 1 yr", on_click=_shift_window, args=(-12,),
                    disabled=si == 0, width="stretch",
                    help="Move the window one year earlier")
    fwd_col.button("1 yr ▶", on_click=_shift_window, args=(12,),
                   disabled=ei == N_MONTHS - 1, width="stretch",
                   help="Move the window one year later")

WIN_START = pd.Period(ss.win_start, "M").start_time
WIN_END = pd.Period(ss.win_end, "M").end_time.normalize()

in_win = df.iloc[si: ei + 1]
# Index growth is measured from the close of the month before the window
# (when available), matching how the scenarios invest.
base_win = df.iloc[max(si - 1, 0): ei + 1]
fig_hist = go.Figure()
fig_hist.add_trace(go.Scatter(
    x=df["date"], y=df[VALUE_COL], name=IDX["name"],
    mode="lines+markers",
    # Invisible markers make every month clickable and selectable.
    marker=dict(size=8, opacity=0),
    selected=dict(marker=dict(opacity=0)),
    unselected=dict(marker=dict(opacity=0)),
    line=dict(color="rgba(120, 130, 145, 0.9)", width=1.5),
    hovertemplate="%{x|%b %Y}: %{y:,.2f}<extra></extra>",
))
fig_hist.add_trace(go.Scatter(
    x=base_win["date"], y=base_win[VALUE_COL], name="Selected window",
    mode="lines", line=dict(color="#1f77b4", width=2.5), hoverinfo="skip",
))
fig_hist.add_vrect(x0=WIN_START, x1=WIN_END, fillcolor="#1f77b4",
                   opacity=0.12, line_width=0, layer="below")
fig_hist.update_layout(
    dragmode="select",
    selectdirection="h",
    clickmode="event+select",  # a click selects the month under the cursor
    hovermode="x",
    showlegend=False,
    height=380,
    margin=dict(t=10, b=10),
    yaxis_title=(f"Index level ({IDX['currency']})" if value_mode == "Nominal"
                 else f"Index level (today's {IDX['currency']})"),
    yaxis_type="log" if log_scale == "Log" else "linear",
)
st.plotly_chart(
    fig_hist,
    key=_chart_key,
    on_select="rerun",
    selection_mode=("points", "box"),
    width="stretch",
    config={"displaylogo": False},
)

_v0, _v1 = base_win[VALUE_COL].iloc[0], base_win[VALUE_COL].iloc[-1]
_wyears = (base_win["date"].iloc[-1] - base_win["date"].iloc[0]).days / 365.25
_wgrowth = _v1 / _v0 - 1
_wcagr = (_v1 / _v0) ** (1 / _wyears) - 1 if _wyears > 0 else None
st.markdown(f"**Selected window:** {month_label(ss.win_start)} – "
            f"{month_label(ss.win_end)} ({_wyears:.1f} years)")
w2, w3, w4 = st.columns(3)
w2.metric("Index level", f"{_v0:,.0f} → {_v1:,.0f}")
w3.metric("Index total growth", f"{_wgrowth * 100:+,.1f}%",
          help="Change in the index level over the window (price only, "
               "no dividends).")
w4.metric("Index CAGR", f"{_wcagr * 100:,.2f}%" if _wcagr is not None else "—",
          help="Average yearly growth of the index over the window.")
if WIN_MONTHS:
    _tip = ("drag on the chart from the point where the window should start — "
            "it keeps its length. Choose *Custom* to pick both start and end.")
else:
    _tip = "drag across the chart from the start date to the end date you want."
st.caption(f"Tip: {_tip} The scenarios below are calculated over this window.")


# ---------------------------------------------------------------------------
# About the selected index
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown(f"#### {IDX['name']}")
    st.markdown(IDX["description"])
    facts = [
        f"**Region:** {IDX['region']}",
        f"**Currency:** {IDX['currency']}",
        f"**Data:** {MIN_DATE:%d %b %Y} – {MAX_DATE:%d %b %Y}",
        f"**Source:** Yahoo Finance `{IDX_META.get('ticker', IDX['tickers'][0])}`",
    ]
    if value_mode == "Inflation-adjusted" and IDX_META.get("cpi"):
        facts.append(
            f"**Inflation:** {IDX_META['cpi']} (published up to "
            f"{IDX_META.get('cpi_last_month', '?')}; later months use the last "
            "available figure)"
        )
    st.caption("  ·  ".join(facts))

with st.expander("📚 Compare all available indices", expanded=False):
    guide = []
    for k in AVAILABLE:
        m = META.get("indices", {}).get(k, {})
        guide.append({
            "Index": INDICES[k]["name"],
            "What it is": INDICES[k]["short"],
            "Region": INDICES[k]["region"],
            "Currency": INDICES[k]["currency"],
            "Data from": m.get("first_date", "—"),
            "Source": m.get("ticker", INDICES[k]["tickers"][0]),
        })
    st.dataframe(pd.DataFrame(guide), width="stretch", hide_index=True)
    if META.get("updated_utc"):
        st.caption(f"Data last updated: {META['updated_utc']}.")

# ---------------------------------------------------------------------------
# IRR helper
# ---------------------------------------------------------------------------
def irr_monthly(cashflows, tol=1e-7, max_iter=200):
    def npv(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))

    # Monthly rates between -20% and +20% (about -93% to +790% a year) keep
    # (1 + rate) ** t finite even over 100 years of monthly periods.
    lo, hi = -0.2, 0.2
    if npv(lo) * npv(hi) > 0:
        return None

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        val = npv(mid)
        if abs(val) < tol:
            return mid
        if npv(lo) * val < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def irr_annual(cashflows):
    m = irr_monthly(cashflows)
    return None if m is None else (1 + m) ** 12 - 1


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------
def simulate(df, start_date, years, initial, contribution, escalation,
             frequency, mode="Nominal", end_date=None):
    ret_col = "ret_nom" if mode == "Nominal" else "ret_real"

    start_date = pd.Timestamp(start_date).replace(day=1)

    # Last day of the final month, so that month's end-of-month row is included.
    if end_date is None:
        end_target = start_date + pd.DateOffset(years=int(years)) - pd.DateOffset(days=1)
    else:
        end_target = pd.Timestamp(end_date)
    end_date = min(end_target, MAX_DATE)

    window = df[(df["date"] >= start_date) & (df["date"] <= end_date)].reset_index(drop=True)
    if window.empty:
        return None, None

    # Money is invested at the close of the month *before* the start month
    # (when that month exists in the data), so the first month's return is
    # included and an N-year window covers exactly N years.
    prev = df[df["date"] < start_date]
    has_base = not prev.empty and pd.notna(window[ret_col].iloc[0])
    base_date = prev["date"].iloc[-1] if has_base else window["date"].iloc[0]

    portfolio = 0.0
    invested = 0.0
    peak = 0.0
    rows = []
    cashflows = []

    start_year = window["date"].iloc[0].year
    start_month = window["date"].iloc[0].month

    if frequency == "Yearly":
        contrib_months = {start_month}
    elif frequency == "Quarterly":
        contrib_months = {(start_month - 1 + 3 * k) % 12 + 1 for k in range(4)}
    else:
        contrib_months = set(range(1, 13))

    for i, row in window.iterrows():
        contrib = 0.0

        if i == 0:
            contrib += float(initial)

        if contribution > 0:
            year_index = row["date"].year - start_year
            escalated = float(contribution) * (1 + escalation) ** year_index

            if frequency == "Yearly":
                if row["date"].month == start_month and (i > 0 or initial == 0):
                    contrib += escalated
                elif i == 0:
                    contrib += escalated
            else:
                if row["date"].month in contrib_months:
                    if i == 0 and initial > 0:
                        pass
                    else:
                        contrib += escalated

        portfolio += contrib
        invested += contrib

        # One cash flow per month (0 when nothing is invested), so the IRR
        # sees the real timing of every contribution.
        cashflows.append(-contrib)

        if i == 0 and has_base:
            # Starting point: the first contribution at the previous close.
            peak = portfolio
            rows.append({
                "date": base_date,
                "contribution": contrib,
                "portfolio": portfolio,
                "invested": invested,
                "drawdown": 0.0,
            })
            contrib = 0.0  # already recorded on the starting row

        if i > 0 or has_base:
            r = row[ret_col]
            if pd.notna(r):
                portfolio *= (1 + r)

        peak = max(peak, portfolio)
        drawdown = (portfolio / peak - 1) if peak > 0 else 0.0

        rows.append({
            "date": row["date"],
            "contribution": contrib,
            "portfolio": portfolio,
            "invested": invested,
            "drawdown": drawdown,
        })

    result = pd.DataFrame(rows)
    if has_base:
        cashflows.append(result["portfolio"].iloc[-1])  # end of the last month
    else:
        cashflows[-1] += result["portfolio"].iloc[-1]

    final_value = result["portfolio"].iloc[-1]
    net_gain = final_value - invested
    net_gain_pct = net_gain / invested if invested > 0 else 0.0
    years_actual = (result["date"].iloc[-1] - result["date"].iloc[0]).days / 365.25

    if initial > 0 and contribution == 0:
        cagr = (final_value / initial) ** (1 / years_actual) - 1 if years_actual > 0 else 0.0
    else:
        cagr = None

    try:
        irr = irr_annual(cashflows) if contribution > 0 or initial > 0 else None
    except Exception:
        irr = None

    max_dd = result["drawdown"].min()

    metrics = {
        "start": start_date,
        "end": result["date"].iloc[-1],
        "years": years_actual,
        "invested": invested,
        "final": final_value,
        "net_gain": net_gain,
        "net_gain_pct": net_gain_pct,
        "cagr": cagr,
        "irr": irr,
        "max_dd": max_dd,
    }

    return result, metrics


# ---------------------------------------------------------------------------
# Scenario builder (sidebar)
# ---------------------------------------------------------------------------
st.sidebar.header("Scenarios")

if "scenarios" not in st.session_state:
    st.session_state.scenarios = [
        {"name": "Lump sum", "type": "Lump sum"},
    ]


def scenario_defaults(kind):
    if kind == "Lump sum":
        return dict(initial=10000.0, contribution=0.0, escalation=0.0,
                    frequency="Yearly")
    if kind == "DCA":
        return dict(initial=0.0, contribution=5000.0, escalation=0.0,
                    frequency="Yearly")
    if kind == "Escalated DCA":
        return dict(initial=0.0, contribution=5000.0, escalation=0.02,
                    frequency="Yearly")
    return dict(initial=10000.0, contribution=5000.0, escalation=0.02,
                frequency="Yearly")


TYPE_HELP = (
    "**Lump sum** — invest a single amount once at the start, nothing after.\n\n"
    "**DCA** (Dollar-Cost Averaging) — invest the same amount on a regular schedule.\n\n"
    "**Escalated DCA** — invest on a regular schedule, increasing the amount each "
    "year by the escalation percentage (e.g. to track salary growth).\n\n"
    "**Custom** — set initial capital, contributions, and escalation freely."
)

FREQ_HELP = (
    "How often the recurring contribution is made.\n\n"
    "**Yearly** — once a year, in the start month.\n"
    "**Quarterly** — four times a year, every three months from the start month.\n"
    "**Monthly** — once a month."
)

def _fill_type_defaults(idx):
    """When a scenario's Type changes, load that type's amounts into the
    inputs (recent Streamlit versions keep a keyed input's old value even
    when its default changes)."""
    kind = st.session_state[f"type_{idx}"]
    if kind == "Custom":
        return
    d = scenario_defaults(kind)
    st.session_state[f"initial_{idx}"] = float(d["initial"])
    st.session_state[f"contrib_{idx}"] = float(d["contribution"])
    st.session_state[f"esc_{idx}"] = float(d["escalation"]) * 100
    st.session_state[f"freq_{idx}"] = d["frequency"]


def _remove_scenario(idx):
    """Remove a scenario and shift the following scenarios' inputs down one
    slot (runs as a callback, before the widgets are drawn)."""
    n = len(st.session_state.scenarios)
    for pre in ("type_", "initial_", "contrib_", "esc_", "freq_",
                "usewin_", "start_str_", "years_"):
        for j in range(idx, n - 1):
            if f"{pre}{j + 1}" in st.session_state:
                st.session_state[f"{pre}{j}"] = st.session_state[f"{pre}{j + 1}"]
            else:
                st.session_state.pop(f"{pre}{j}", None)
        st.session_state.pop(f"{pre}{n - 1}", None)
    st.session_state.scenarios.pop(idx)


for idx, sc in enumerate(st.session_state.scenarios):
    with st.sidebar.expander(f"Scenario {idx+1}: {sc['name']}", expanded=(idx == 0)):
        st.session_state.setdefault(f"type_{idx}", sc["type"])
        kind = st.selectbox(
            "Type",
            options=["Lump sum", "DCA", "Escalated DCA", "Custom"],
            key=f"type_{idx}",
            help=TYPE_HELP,
            on_change=_fill_type_defaults,
            args=(idx,),
        )

        defaults = scenario_defaults(kind) if kind != "Custom" else dict(
            initial=sc.get("initial", 10000.0),
            contribution=sc.get("contribution", 5000.0),
            escalation=sc.get("escalation", 0.02),
            frequency=sc.get("frequency", "Yearly"),
        )
        st.session_state.setdefault(f"initial_{idx}", float(defaults["initial"]))
        st.session_state.setdefault(f"contrib_{idx}", float(defaults["contribution"]))
        st.session_state.setdefault(f"esc_{idx}", float(defaults["escalation"]) * 100)
        st.session_state.setdefault(f"freq_{idx}", defaults["frequency"])

        st.session_state.setdefault(f"usewin_{idx}", sc.get("use_window", True))
        use_window = st.checkbox(
            "Use the time window from the chart",
            key=f"usewin_{idx}",
            help="Untick to give this scenario its own start date and duration.",
        )

        default_start = sc.get("start_date", max(date(1999, 1, 1), MIN_DATE.date()))
        if use_window:
            st.caption(f"📅 {month_label(ss.win_start)} – {month_label(ss.win_end)} "
                       "(set on the chart)")
            start_date_parsed = WIN_START.date()
            years = sc.get("years", 10)
        else:
            st.session_state.setdefault(
                f"start_str_{idx}",
                default_start.strftime("%Y-%m-%d")
                if isinstance(default_start, date) else str(default_start),
            )
            start_str = st.text_input(
                "Start date (YYYY-MM-DD)",
                key=f"start_str_{idx}",
                help=f"Any date between {MIN_DATE.date()} and {MAX_DATE.date()}. "
                     "The simulation starts from the first day of that month.",
            )
            try:
                start_date_parsed = pd.to_datetime(start_str).date()
            except Exception:
                st.error(f"Scenario {idx+1}: invalid date format. Use YYYY-MM-DD.")
                start_date_parsed = default_start

            if start_date_parsed < MIN_DATE.date():
                st.warning(f"Scenario {idx+1}: start before {MIN_DATE.date()} — clamped.")
                start_date_parsed = MIN_DATE.date()
            if start_date_parsed > MAX_DATE.date():
                st.warning(f"Scenario {idx+1}: start after {MAX_DATE.date()} — clamped.")
                start_date_parsed = MAX_DATE.date()

            st.session_state.setdefault(f"years_{idx}", int(sc.get("years", 10)))
            years = st.number_input(
                "Duration (years)",
                min_value=1, max_value=100,
                key=f"years_{idx}",
            )
        initial = st.number_input(
            f"Initial capital ({CUR})",
            min_value=0.0, step=1000.0,
            key=f"initial_{idx}",
        )
        contribution = st.number_input(
            f"Recurring contribution ({CUR})",
            min_value=0.0, step=500.0,
            key=f"contrib_{idx}",
        )
        frequency = st.selectbox(
            "Contribution frequency",
            options=["Yearly", "Quarterly", "Monthly"],
            key=f"freq_{idx}",
            help=FREQ_HELP,
        )
        escalation = st.number_input(
            "Contribution escalation (% per year)",
            min_value=0.0, max_value=20.0, step=0.5,
            key=f"esc_{idx}",
        ) / 100.0

        sc.update({
            "type": kind,
            "start_date": start_date_parsed,
            "years": int(years),
            "use_window": use_window,
            "initial": initial,
            "contribution": contribution,
            "frequency": frequency,
            "escalation": escalation,
        })

        if len(st.session_state.scenarios) > 1:
            st.button(f"🗑️ Remove scenario {idx+1}", key=f"remove_{idx}",
                      on_click=_remove_scenario, args=(idx,))


if len(st.session_state.scenarios) < 3:
    if st.sidebar.button("➕ Add scenario"):
        st.session_state.scenarios.append(
            {"name": f"Scenario {len(st.session_state.scenarios)+1}", "type": "DCA"}
        )
        st.rerun()


# ---------------------------------------------------------------------------
# Run simulations
# ---------------------------------------------------------------------------
runs = []
for idx, sc in enumerate(st.session_state.scenarios):
    if sc.get("initial", 0) == 0 and sc.get("contribution", 0) == 0:
        st.warning(f"Scenario {idx+1} has no contributions — skipped.")
        continue

    result, metrics = simulate(
        df,
        start_date=sc["start_date"],
        years=sc["years"],
        initial=sc["initial"],
        contribution=sc["contribution"],
        escalation=sc["escalation"],
        frequency=sc["frequency"],
        mode=value_mode,
        end_date=WIN_END if sc.get("use_window") else None,
    )
    if result is None:
        st.warning(f"Scenario {idx+1}: no data in chosen window — skipped.")
        continue

    requested_end = pd.Timestamp(sc["start_date"]).replace(day=1) + \
        pd.DateOffset(years=sc["years"]) - pd.DateOffset(days=1)
    if not sc.get("use_window") and requested_end > MAX_DATE:
        st.info(
            f"Scenario {idx+1}: requested end {requested_end:%b %Y} "
            f"beyond available data — capped at {MAX_DATE:%b %Y}."
        )

    runs.append({
        "name": f"Scenario {idx+1} ({sc['type']})",
        "result": result,
        "metrics": metrics,
        "params": sc,
    })

if not runs:
    st.stop()

# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------
def add_years_since_start(result):
    res = result.copy()
    res["years_since_start"] = (
        (res["date"] - res["date"].iloc[0]).dt.days / 365.25
    )
    return res


def compute_yearly_returns(result):
    """Calendar-year change of the portfolio value.

    Each year runs from the previous year's last value (or the starting value)
    to that year's last value. Contributions made during the year are NOT
    subtracted, so this is a 'gross' year-on-year view of the portfolio.
    A year that only holds the starting point is skipped.
    """
    res = result.copy()
    res["year"] = res["date"].dt.year

    yearly = []
    prev_val = None
    for year, grp in res.groupby("year"):
        last_val = grp["portfolio"].iloc[-1]
        if prev_val is None:
            if len(grp) == 1 and len(res) > 1:
                prev_val = last_val  # only the starting point lies in this year
                continue
            prev_val = grp["portfolio"].iloc[0]
        ret = (last_val / prev_val) - 1 if prev_val > 0 else 0.0
        yearly.append({"year": year, "return": ret})
        prev_val = last_val
    return pd.DataFrame(yearly)


# ---------------------------------------------------------------------------
# RETURN chart
# ---------------------------------------------------------------------------
st.subheader("Return")

for r in runs:
    m = r["metrics"]
    st.markdown(f"**{r['name']}** · {m['start']:%b %Y} – {m['end']:%b %Y}")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Final value", f"{CUR}{m['final']:,.0f}")
    k2.metric("Total growth", f"{m['net_gain_pct'] * 100:+,.1f}%",
              help="Final value compared with everything you invested: "
                   "final ÷ invested − 1.")
    if m["cagr"] is not None:
        k3.metric("CAGR", f"{m['cagr'] * 100:,.2f}%",
                  help="Average yearly growth of a single lump sum.")
    else:
        k3.metric("IRR", f"{m['irr'] * 100:,.2f}%" if m["irr"] is not None else "—",
                  help="Average yearly return, taking the timing of each "
                       "contribution into account.")
    k4.metric("Invested", f"{CUR}{m['invested']:,.0f}")

fig_eq = go.Figure()
for r in runs:
    res = add_years_since_start(r["result"])
    fig_eq.add_trace(go.Scatter(
        x=res["years_since_start"], y=res["portfolio"],
        mode="lines", name=r["name"],
    ))

fig_eq.update_layout(
    xaxis_title="Years since start",
    yaxis_title="Portfolio value",
    yaxis_type="log" if log_scale == "Log" else "linear",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_eq, width="stretch")

# ---------------------------------------------------------------------------
# YEARLY RETURNS bar chart
# ---------------------------------------------------------------------------
st.subheader("Yearly returns")

st.caption(
    "Each bar shows the portfolio's change over one calendar year. "
    "**Green = a positive year, red = a negative year.** "
    "Contributions made during the year are included in the portfolio value, "
    "so a green year does not necessarily mean the market went up — it means "
    "your portfolio ended the year higher than it started."
)

fig_yr = go.Figure()
for r in runs:
    yearly = compute_yearly_returns(r["result"])
    colors = ["rgba(46, 160, 67, 0.75)" if v >= 0 else "rgba(220, 53, 69, 0.75)"
              for v in yearly["return"]]
    fig_yr.add_trace(go.Bar(
        x=yearly["year"],
        y=yearly["return"] * 100,
        name=r["name"],
        marker_color=colors,
        hovertemplate="Year %{x}<br>Return: %{y:.1f}%<extra></extra>",
    ))

fig_yr.update_layout(
    xaxis_title="Calendar year",
    yaxis_title="Yearly return (%)",
    barmode="group",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
fig_yr.add_hline(y=0, line_width=1, line_color="black")
st.plotly_chart(fig_yr, width="stretch")

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------
st.subheader("Results table")

summary_rows = []
for r in runs:
    m = r["metrics"]
    summary_rows.append({
        "Scenario": r["name"],
        "Start": m["start"].strftime("%b %Y"),
        "End": m["end"].strftime("%b %Y"),
        "Years": round(m["years"], 2),
        "Invested": f"{CUR}{m['invested']:,.0f}",
        "Final value": f"{CUR}{m['final']:,.0f}",
        "Net gain": f"{CUR}{m['net_gain']:,.0f}",
        "Total growth": f"{m['net_gain_pct']*100:,.1f}%",
        "CAGR": f"{m['cagr']*100:,.2f}%" if m["cagr"] is not None else "—",
        "IRR": f"{m['irr']*100:,.2f}%" if m["irr"] is not None else "—",
        "Max DD": f"{m['max_dd']*100:,.1f}%",
    })

summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, width="stretch", hide_index=True)

st.markdown(
    """
**What the columns mean (in simple words):**

- **Invested** — total money you put in (initial + all contributions).
- **Final value** — what your portfolio is worth at the end.
- **Net gain** — final value minus what you invested. Your profit in money terms.
- **Total growth** — the same profit, expressed as a percentage of what you invested.
- **CAGR** — *Compound Annual Growth Rate*. The average yearly growth rate,
  assuming a single initial investment with no extra contributions. Shown only
  for pure lump sum.
- **IRR** — *Internal Rate of Return*. The average yearly growth rate when you
  made contributions over time. Fairer than CAGR when money entered at different moments.
- **Max DD** — *Maximum Drawdown*. The biggest drop from a peak to a later low.
  A "-30%" means at some point your portfolio was 30% below its previous high.
"""
)

mode_label = (
    "nominal terms"
    if value_mode == "Nominal"
    else "inflation-adjusted terms (start-of-period purchasing power)"
)
st.caption(f"{IDX['name']} — all figures in **{IDX['currency']}**, **{mode_label}**. "
           "Price return only, excludes dividends.")

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
st.subheader("Export")

st.markdown("You can export the data in .csv format below.")

for r in runs:
    res = r["result"].copy()
    meta = (
        f"# Scenario: {r['name']}\n"
        f"# Start: {r['metrics']['start']:%Y-%m-%d}\n"
        f"# End: {r['metrics']['end']:%Y-%m-%d}\n"
        f"# Index: {IDX['name']} ({IDX_META.get('ticker', '')}, {IDX['currency']})\n"
        f"# Value mode: {value_mode}\n"
        f"# Price return only, excludes dividends\n"
        f"# Initial: {r['params']['initial']}\n"
        f"# Contribution: {r['params']['contribution']} ({r['params']['frequency']})\n"
        f"# Escalation: {r['params']['escalation']}\n"
    )
    csv = meta + res.to_csv(index=False)
    st.download_button(
        label=f"⬇️ Download CSV — {r['name']}",
        data=csv.encode("utf-8"),
        file_name=f"{index_id}_{r['name'].replace(' ', '_').replace('(', '').replace(')', '')}.csv",
        mime="text/csv",
        key=f"dl_{r['name']}",
    )
