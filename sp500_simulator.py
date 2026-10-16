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

# ---------------------------------------------------------------------------
# Collapsible instructions
# ---------------------------------------------------------------------------
with st.expander("ℹ️ What this app does — click to expand", expanded=False):
    st.markdown(
        """
**What this app does**

This tool lets you simulate how a hypothetical investment in the S&P 500 would
have performed if you had started at any month between **31 December 1927** and
**14 October 2026**. You can model a single lump sum, regular contributions,
or a mix of both — and compare up to three scenarios side by side.

**How to use it**

1. In the sidebar, choose whether you want results in *Nominal* or
   *Inflation-adjusted* terms.
2. Set up one or more scenarios:
   - **Lump sum** — invest once at the start, nothing after.
   - **DCA** (Dollar-Cost Averaging) — invest the same amount on a regular schedule.
   - **Escalated DCA** — invest on a regular schedule, increasing the amount
     each year by your escalation percentage.
   - **Custom** — set initial capital, contributions, and escalation freely.
3. Pick a **start date** (type it in manually if you like) and a **duration**.
4. Choose the **contribution frequency**: yearly, quarterly, or monthly.
5. The app shows the **final portfolio value**, the **total amount invested**,
   the **net gain**, the annualized return (CAGR and/or IRR), and the
   **maximum drawdown** — plus a return chart and a drawdown chart.
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
# IRR helper
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
# Simulation engine (with configurable contribution frequency)
# ---------------------------------------------------------------------------
def simulate(df, start_date, years, initial, contribution, escalation,
             frequency, mode="Nominal"):
    """Run one scenario.

    frequency: "Yearly", "Quarterly", or "Monthly".
    Contributions are made at the start of the relevant period.
    Escalation applies once per year (from year 1: year k = base * (1+g)^(k-1)).
    """
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
    start_month = window["date"].iloc[0].month

    # Contribution months within a year
    if frequency == "Yearly":
        contrib_months = {start_month}  # start month each year (anniversary)
    elif frequency == "Quarterly":
        contrib_months = {(start_month - 1 + 3 * k) % 12 + 1 for k in range(4)}
    else:  # Monthly
        contrib_months = set(range(1, 13))

    for i, row in window.iterrows():
        contrib = 0.0

        # Initial capital at month 0
        if i == 0:
            contrib += float(initial)

        # Recurring contributions
        if contribution > 0:
            year_index = row["date"].year - start_year
            escalated = float(contribution) * (1 + escalation) ** year_index

            if frequency == "Yearly":
                # One contribution per year, in the start month
                if row["date"].month == start_month and (i > 0 or initial == 0):
                    contrib += escalated
                elif i == 0:
                    contrib += escalated
            else:
                # Quarterly or Monthly
                if row["date"].month in contrib_months:
                    # Skip the very first month if initial already covers it
                    if i == 0 and initial > 0:
                        pass
                    else:
                        contrib += escalated

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
            contribution=sc.get("contribution", 5000.0),
            escalation=sc.get("escalation", 0.02),
            frequency=sc.get("frequency", "Yearly"),
        )

        # --- Date input: typed text, so any date in the dataset works ---
        default_start = sc.get("start_date", date(1999, 1, 1))
        start_str = st.text_input(
            "Start date (YYYY-MM-DD)",
            value=default_start.strftime("%Y-%m-%d")
            if isinstance(default_start, date) else str(default_start),
            key=f"start_str_{idx}",
            help=f"Any date between {MIN_DATE.date()} and {MAX_DATE.date()}. "
                 "The simulation starts from the first day of that month.",
        )
        try:
            start_date_parsed = pd.to_datetime(start_str).date()
        except Exception:
            st.error(f"Scenario {idx+1}: invalid date format. Use YYYY-MM-DD.")
            start_date_parsed = default_start

        # Clamp
        if start_date_parsed < MIN_DATE.date():
            st.warning(f"Scenario {idx+1}: start before {MIN_DATE.date()} — clamped.")
            start_date_parsed = MIN_DATE.date()
        if start_date_parsed > MAX_DATE.date():
            st.warning(f"Scenario {idx+1}: start after {MAX_DATE.date()} — clamped.")
            start_date_parsed = MAX_DATE.date()

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
        contribution = st.number_input(
            "Recurring contribution (€)",
            min_value=0.0, step=500.0,
            value=float(defaults["contribution"]),
            key=f"contrib_{idx}",
        )
        frequency = st.selectbox(
            "Contribution frequency",
            options=["Yearly", "Quarterly", "Monthly"],
            index=["Yearly", "Quarterly", "Monthly"].index(
                sc.get("frequency", "Yearly")
            ),
            key=f"freq_{idx}",
            help=FREQ_HELP,
        )
        escalation = st.number_input(
            "Contribution escalation (% per year)",
            min_value=0.0, max_value=20.0, step=0.5,
            value=float(defaults["escalation"]) * 100,
            key=f"esc_{idx}",
        ) / 100.0

        sc.update({
            "type": kind,
            "start_date": start_date_parsed,
            "years": int(years),
            "initial": initial,
            "contribution": contribution,
            "frequency": frequency,
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

st.markdown(
    """
**What the columns mean (in simple words):**

- **Invested** — total money you put in (initial + all contributions).
- **Final value** — what your portfolio is worth at the end.
- **Net gain** — final value minus what you invested. Your profit in euros.
- **Net gain %** — the same profit, expressed as a percentage of what you invested.
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
st.caption(f"All figures in **{mode_label}**. Price return only, excludes dividends.")

# ---------------------------------------------------------------------------
# Charts — x-axis is years since start
# ---------------------------------------------------------------------------
def add_years_since_start(result):
    res = result.copy()
    res["years_since_start"] = (
        (res["date"] - res["date"].iloc[0]).dt.days / 365.25
    )
    return res


st.subheader("Return")

# On-screen summary of final values + CAGR
final_summary = "  |  ".join(
    f"**{r['name']}** — final: €{r['metrics']['final']:,.0f}"
    + (
        f", CAGR: {r['metrics']['cagr']*100:,.2f}%"
        if r["metrics"]["cagr"] is not None
        else (
            f", IRR: {r['metrics']['irr']*100:,.2f}%"
            if r["metrics"]["irr"] is not None
            else ""
        )
    )
    for r in runs
)
st.markdown(final_summary)

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
st.plotly_chart(fig_eq, use_container_width=True)

# ---------------------------------------------------------------------------
# Drawdown chart — light red below 0, light green above 0, transparent fills
# ---------------------------------------------------------------------------
st.subheader("Drawdown")
fig_dd = go.Figure()
for r in runs:
    res = add_years_since_start(r["result"])
    dd = res["drawdown"] * 100
    fig_dd.add_trace(go.Scatter(
        x=res["years_since_start"], y=dd,
        mode="lines", name=r["name"],
        fill="tozeroy",
        fillcolor="rgba(255, 99, 71, 0.25)",   # light red
        line=dict(width=1.5),
    ))

# Green band above zero for visual reference
fig_dd.add_hrect(
    y0=0, y1=5,
    fillcolor="rgba(144, 238, 144, 0.15)",  # light green
    line_width=0,
    layer="below",
)

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
        f"# Contribution: {r['params']['contribution']} ({r['params']['frequency']})\n"
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
