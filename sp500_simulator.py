import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="S&P 500 Backtester",
    page_icon="📈",
    layout="wide",
)

st.title("📈 S&P 500 Backtester")

st.markdown(
    """
**What this app does**

This tool lets you simulate how a hypothetical investment in the S&P 500 would
have performed if you had started at any month between **31 December 1927** and
**14 October 2026**. You can model a single lump sum, regular yearly
contributions, or a mix of both — and compare up to three scenarios side by side.

**How to use it**

1. In the sidebar, choose whether you want results in *Nominal* or
   *Inflation-adjusted* terms.
2. Set up one or more scenarios:
   - **Lump sum** — invest once at the start, nothing after.
   - **DCA** (Dollar-Cost Averaging) — invest the same amount every January.
   - **Escalated DCA** — invest every January, increasing the amount each year
     by your escalation percentage (e.g. to track salary growth).
   - **Custom** — set initial capital, yearly contributions, and escalation freely.
3. Pick a **start date** and a **duration** (in years).
4. The app shows the **final portfolio value**, the **total amount you invested**,
   the **net gain**, the annualized return (CAGR and/or IRR), and the
   **maximum drawdown** — plus an equity curve and drawdown chart.
5. Download any scenario's monthly data as a CSV if you want to explore further.

**What the outputs mean**

- **Final value** — portfolio value at the end of the chosen period.
- **Invested** — total capital you put in (initial + all contributions).
- **Net gain** — final value minus invested.
- **CAGR** — compound annual growth rate; shown only when there are no
  contributions (pure lump sum), since CAGR assumes a single initial investment.
- **IRR** — internal rate of return; the fair annualized return when
  contributions exist. Accounts for the timing of each cash flow.
- **Max drawdown** — the largest peak-to-trough decline experienced during
  the period.

**Important**

All results are **price return only and exclude dividends**. The data range
covers **31 December 1927 to 14 October 2026**.
"""
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
FILE = "s&p500_19271231_20261014.csv"


@st.cache_data
def load_index(path):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y")
    df = df.sort_values("date").reset_index(drop=True)

    df = df.dropna(subset=["inflation_adjusted", "nominal"]).reset_index(drop=True)

    df["ret_real"] = df["inflation_adjusted"].pct_change()
    df["ret_nom"] = df["nominal"].pct_change()

    return df


df = load_index(FILE)
MIN_DATE = df["date"].min()
MAX_DATE = df["date"].max()

# ---------------------------------------------------------------------------
# Sidebar — global settings
# ---------------------------------------------------------------------------
st.sidebar.header("Global settings")

value_mode = st.sidebar.radio(
    "Value mode",
    options=["Nominal", "Inflation-adjusted"],
    index=0,
    help=(
        "**Nominal** — actual euro/dollar amounts of the day.\n\n"
        "**Inflation-adjusted** — expresses past values in start-of-period "
        "purchasing power, i.e. it assumes inflation didn't exist, so you can "
        "compare returns across different eras in 'real' terms."
    ),
)

log_scale = st.sidebar.radio(
    "Y-axis scale (charts)",
    options=["Linear", "Log"],
    index=0,
)

# ---------------------------------------------------------------------------
# IRR helper (internal bisection; no external dependency)
# ---------------------------------------------------------------------------
def irr_monthly(cashflows, tol=1e-7, max_iter=200):
    def npv(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))

    lo, hi = -0.99, 1.0
    for _ in range(20):
        if npv(lo) * npv(hi) < 0:
            break
        hi *= 2

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
    return (1 + m) ** 12 - 1


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------
def simulate(df, start_date, years, initial, yearly, escalation,
             contribution_month, mode="Nominal"):
    col = "nominal" if mode == "Nominal" else "inflation_adjusted"
    ret_col = "ret_nom" if mode == "Nominal" else "ret_real"

    start_date = pd.Timestamp(start_date).replace(day=1)

    end_target = start_date + pd.DateOffset(years=int(years)) - pd.DateOffset(months=1)
    end_date = min(end_target, MAX_DATE)

    window = df[(df["date"] >= start_date) & (df["date"] <= end_date)].reset_index(drop=True)
    if window.empty:
        return None, None

    portfolio = 0.0
    invested = 0.0
    peak = 0.0
    rows = []
    cashflows = []

    start_year = window["date"].iloc[0].year

    for i, row in window.iterrows():
        contrib = 0.0

        if i == 0:
            contrib += float(initial)

        if yearly > 0:
            if i == 0:
                contrib += float(yearly)
            elif row["date"].month == 1:
                year_index = row["date"].year - start_year
                contrib += float(yearly) * (1 + escalation) ** year_index

        portfolio += contrib
        invested += contrib

        if contrib > 0:
            cashflows.append(-contrib)

        if i > 0:
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
    cashflows.append(result["portfolio"].iloc[-1])

    final_value = result["portfolio"].iloc[-1]
    net_gain = final_value - invested
    net_gain_pct = net_gain / invested if invested > 0 else 0.0
    years_actual = (result["date"].iloc[-1] - result["date"].iloc[0]).days / 365.25

    if initial > 0 and yearly == 0:
        cagr = (final_value / initial) ** (1 / years_actual) - 1 if years_actual > 0 else 0.0
    else:
        cagr = None

    try:
        irr = irr_annual(cashflows) if yearly > 0 or initial > 0 else None
    except Exception:
        irr = None

    max_dd = result["drawdown"].min()

    metrics = {
        "start": result["date"].iloc[0],
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
        return dict(initial=10000.0, yearly=0.0, escalation=0.0)
    if kind == "DCA":
        return dict(initial=0.0, yearly=5000.0, escalation=0.0)
    if kind == "Escalated DCA":
        return dict(initial=0.0, yearly=5000.0, escalation=0.02)
    return dict(initial=10000.0, yearly=5000.0, escalation=0.02)


TYPE_HELP = (
    "**Lump sum** — invest a single amount once at the start, nothing after.\n\n"
    "**DCA** (Dollar-Cost Averaging) — invest the same amount every January.\n\n"
    "**Escalated DCA** — invest every January, increasing the amount each year "
    "by the escalation percentage (e.g. to track salary growth).\n\n"
    "**Custom** — set initial capital, yearly contributions, and escalation freely."
)

for idx, sc in enumerate(st.session_state.scenarios):
    with st.sidebar.expander(f"Scenario {idx+1}: {sc['name']}", expanded=(idx == 0)):
        kind = st.selectbox(
            "Type",
            options=["Lump sum", "DCA", "Escalated DCA", "Custom"],
            index=["Lump sum", "DCA", "Escalated DCA", "Custom"].index(sc["type"]),
            key=f"type_{idx}",
            help=TYPE_HELP,
        )

        defaults = scenario_defaults(kind) if kind != "Custom" else dict(
            initial=sc.get("initial", 10000.0),
            yearly=sc.get("yearly", 5000.0),
            escalation=sc.get("escalation", 0.02),
        )

        start_date = st.date_input(
            "Start date",
            value=sc.get("start_date", date(1999, 1, 1)),
            min_value=MIN_DATE.date(),
            max_value=MAX_DATE.date(),
            key=f"start_{idx}",
        )
        years = st.number_input(
            "Duration (years)",
            min_value=1, max_value=100,
            value=sc.get("years", 10),
            key=f"years_{idx}",
        )
        initial = st.number_input(
            "Initial capital (€)",
            min_value=0.0, step=1000.0,
            value=float(defaults["initial"]),
            key=f"initial_{idx}",
        )
        yearly = st.number_input(
            "Yearly contribution (€)",
            min_value=0.0, step=500.0,
            value=float(defaults["yearly"]),
            key=f"yearly_{idx}",
        )
        escalation = st.number_input(
            "Contribution escalation (% per year)",
            min_value=0.0, max_value=20.0, step=0.5,
            value=float(defaults["escalation"]) * 100,
            key=f"esc_{idx}",
        ) / 100.0

        sc.update({
            "type": kind,
            "start_date": start_date,
            "years": int(years),
            "initial": initial,
            "yearly": yearly,
            "escalation": escalation,
        })

        if len(st.session_state.scenarios) > 1:
            if st.button(f"🗑️ Remove scenario {idx+1}", key=f"remove_{idx}"):
                st.session_state.scenarios.pop(idx)
                st.rerun()


if len(st.session_state.scenarios) < 3:
    if st.sidebar.button("➕ Add scenario"):
        st.session_state.scenarios.append(
            {"name": f"Scenario {len(st.session_state.scenarios)+1}", "type": "DCA"}
        )
        st.rerun()


# ---------------------------------------------------------------------------
# Run simulations
# ---------------------------------------------------------------------------
st.subheader("Results")

runs = []
for idx, sc in enumerate(st.session_state.scenarios):
    if sc.get("initial", 0) == 0 and sc.get("yearly", 0) == 0:
        st.warning(f"Scenario {idx+1} has no contributions — skipped.")
        continue

    result, metrics = simulate(
        df,
        start_date=sc["start_date"],
        years=sc["years"],
        initial=sc["initial"],
        yearly=sc["yearly"],
        escalation=sc["escalation"],
        contribution_month=1,
        mode=value_mode,
    )
    if result is None:
        st.warning(f"Scenario {idx+1}: no data in chosen window — skipped.")
        continue

    requested_end = pd.Timestamp(sc["start_date"]).replace(day=1) + \
        pd.DateOffset(years=sc["years"]) - pd.DateOffset(months=1)
    if requested_end > MAX_DATE:
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
# KPI summary table
# ---------------------------------------------------------------------------
summary_rows = []
for r in runs:
    m = r["metrics"]
    summary_rows.append({
        "Scenario": r["name"],
        "Start": m["start"].strftime("%b %Y"),
        "End": m["end"].strftime("%b %Y"),
        "Years": round(m["years"], 2),
        "Invested": f"€{m['invested']:,.0f}",
        "Final value": f"€{m['final']:,.0f}",
        "Net gain": f"€{m['net_gain']:,.0f}",
        "Net gain %": f"{m['net_gain_pct']*100:,.1f}%",
        "CAGR": f"{m['cagr']*100:,.2f}%" if m["cagr"] is not None else "—",
        "IRR": f"{m['irr']*100:,.2f}%" if m["irr"] is not None else "—",
        "Max DD": f"{m['max_dd']*100:,.1f}%",
    })

summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

mode_label = (
    "nominal terms"
    if value_mode == "Nominal"
    else "inflation-adjusted terms (start-of-period purchasing power)"
)
st.caption(f"All figures in **{mode_label}**. Price return only, excludes dividends.")

# ---------------------------------------------------------------------------
# Charts — x-axis is years since start (aligned for comparison)
# ---------------------------------------------------------------------------
def add_years_since_start(result):
    res = result.copy()
    res["years_since_start"] = (
        (res["date"] - res["date"].iloc[0]).dt.days / 365.25
    )
    return res


st.subheader("Return")

fig_eq = go.Figure()
for r in runs:
    res = add_years_since_start(r["result"])
    fig_eq.add_trace(go.Scatter(
        x=res["years_since_start"], y=res["portfolio"],
        mode="lines", name=r["name"],
    ))
    fig_eq.add_trace(go.Scatter(
        x=res["years_since_start"], y=res["invested"],
        mode="lines", name=f"{r['name']} — invested",
        line=dict(dash="dot", width=1),
        opacity=0.5,
    ))

fig_eq.update_layout(
    xaxis_title="Years since start",
    yaxis_title="Portfolio value",
    yaxis_type="log" if log_scale == "Log" else "linear",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_eq, use_container_width=True)

st.subheader("Drawdown")
fig_dd = go.Figure()
for r in runs:
    res = add_years_since_start(r["result"])
    fig_dd.add_trace(go.Scatter(
        x=res["years_since_start"], y=res["drawdown"] * 100,
        mode="lines", name=r["name"],
        fill="tozeroy",
    ))
fig_dd.update_layout(
    xaxis_title="Years since start",
    yaxis_title="Drawdown (%)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_dd, use_container_width=True)

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
        f"# Value mode: {value_mode}\n"
        f"# Price return only, excludes dividends\n"
        f"# Initial: {r['params']['initial']}\n"
        f"# Yearly: {r['params']['yearly']}\n"
        f"# Escalation: {r['params']['escalation']}\n"
    )
    csv = meta + res.to_csv(index=False)
    st.download_button(
        label=f"⬇️ Download CSV — {r['name']}",
        data=csv.encode("utf-8"),
        file_name=f"sp500_{r['name'].replace(' ', '_').replace('(', '').replace(')', '')}.csv",
        mime="text/csv",
        key=f"dl_{r['name']}",
    )
