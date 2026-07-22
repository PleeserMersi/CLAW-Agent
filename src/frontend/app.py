"""
Fault Dashboard
================
Streamlit app that visualizes fault records from `all_shift_faults.csv` and
`manual_review.csv`.

Expected columns:
  all_shift_faults.csv:
    FullTimestamp, timestamp, description, tag, run_number, ShiftLogNumber,
    ShiftLogbookURL, ShiftTitle, ShiftDateTime, ShiftHall, FragmentLink,
    verification_status

  manual_review.csv:
    Same as above, minus verification_status. Every row in this file is
    treated as verification_status = "uncertain" (since it hasn't been
    confirmed yet). Every row in all_shift_faults.csv is treated as
    verification_status = "accurate".

Run with:
    streamlit run fault_dashboard.py

Place all_shift_faults.csv and manual_review.csv in the same folder as this
script. If neither is found, the app falls back to generated sample data so
you can still see how everything works.
"""

from __future__ import annotations

import datetime as dt
import os
import random

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Fault Timeline Dashboard",
    page_icon="\U0001F6A8",
    layout="wide",
)

ALL_FAULTS_FILE = "data/final_output/all_shift_faults.csv"
MANUAL_REVIEW_FILE = "data/final_output/manual_check.csv"

ALL_FAULTS_COLUMNS = [
    "FullTimestamp", "timestamp", "description", "tag", "run_number",
    "ShiftLogNumber", "ShiftLogbookURL", "ShiftTitle", "ShiftDateTime",
    "ShiftHall", "FragmentLink", "verification_status",
]
MANUAL_REVIEW_COLUMNS = [c for c in ALL_FAULTS_COLUMNS if c != "verification_status"]

TAG_COLORS = [
    "#E4572E", "#29335C", "#F3A712", "#669BBC", "#A8C686",
    "#C86B85", "#4E937A", "#8367C7", "#D7A9E3", "#5B8C5A",
]

STATUS_COLORS = {"accurate": "#4E937A", "uncertain": "#E4572E"}

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Cap for the O(n * window) co-occurrence computation so a huge date range
# with a wide window doesn't stall the UI.
COOCCURRENCE_ROW_CAP = 8000


# --------------------------------------------------------------------------
# Sample data (only used if no real files are found / uploaded)
# --------------------------------------------------------------------------
def _generate_sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    random.seed(7)
    halls = ["Hall A", "Hall B", "Hall C"]
    tags = ["Beam Trip", "DAQ Error", "Magnet Fault", "Vacuum", "Cooling", "RF Fault"]
    base_day = dt.datetime(2026, 6, 1)

    def make_rows(n, status):
        rows = []
        for i in range(n):
            ts = base_day + dt.timedelta(
                days=random.randint(0, 29),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            hall = random.choice(halls)
            tag = random.choice(tags)
            log_num = random.randint(4490000, 4490999)
            row = {
                "FullTimestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": ts.strftime("%H:%M"),
                "description": f"{tag} detected during run — sample description #{i}.",
                "tag": tag,
                "run_number": random.randint(245000, 245999) if random.random() > 0.3 else "",
                "ShiftLogNumber": log_num,
                "ShiftLogbookURL": f"https://logbooks.jlab.org/entry/{log_num}",
                "ShiftTitle": f"{hall} Shift Summary",
                "ShiftDateTime": base_day.strftime("%Y-%m-%d %H:%M:%S"),
                "ShiftHall": hall,
                "FragmentLink": f"https://logbooks.jlab.org/entry/{log_num}#:~:text={ts.strftime('%H:%M')}",
            }
            if status is not None:
                row["verification_status"] = status
            rows.append(row)
        return rows

    all_df = pd.DataFrame(make_rows(140, status="accurate"), columns=ALL_FAULTS_COLUMNS)
    manual_df = pd.DataFrame(make_rows(25, status=None), columns=MANUAL_REVIEW_COLUMNS)
    return all_df, manual_df


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    using_sample = False

    all_df = pd.read_csv(ALL_FAULTS_FILE) if os.path.exists(ALL_FAULTS_FILE) else None
    manual_df = pd.read_csv(MANUAL_REVIEW_FILE) if os.path.exists(MANUAL_REVIEW_FILE) else None

    if all_df is None and manual_df is None:
        using_sample = True
        all_df, manual_df = _generate_sample_data()
    elif all_df is None:
        all_df = pd.DataFrame(columns=ALL_FAULTS_COLUMNS)
    elif manual_df is None:
        manual_df = pd.DataFrame(columns=MANUAL_REVIEW_COLUMNS)

    all_df = all_df.copy()
    manual_df = manual_df.copy()

    # Every row from all_shift_faults.csv is a confirmed/accurate fault.
    all_df["source"] = "All Shift Faults"
    all_df["verification_status"] = "accurate"

    # Every row from manual_review.csv hasn't been confirmed yet.
    manual_df["source"] = "Manual Review"
    manual_df["verification_status"] = "uncertain"

    combined = pd.concat([all_df, manual_df], ignore_index=True, sort=False)

    combined["FullTimestamp"] = pd.to_datetime(combined["FullTimestamp"], errors="coerce")
    combined = combined.dropna(subset=["FullTimestamp"])

    for col in ["description", "tag", "ShiftHall", "ShiftTitle", "ShiftLogbookURL", "FragmentLink"]:
        if col in combined.columns:
            combined[col] = combined[col].fillna("").astype(str)
        else:
            combined[col] = ""

    combined["run_number"] = pd.to_numeric(combined.get("run_number"), errors="coerce")

    combined["date"] = combined["FullTimestamp"].dt.date
    combined["time_of_day"] = combined["FullTimestamp"].dt.time
    combined = combined.sort_values("FullTimestamp").reset_index(drop=True)
    combined.attrs["using_sample"] = using_sample
    return combined


# --------------------------------------------------------------------------
# Sidebar: data source + filters
# --------------------------------------------------------------------------
st.sidebar.title("Fault Dashboard")

df = load_data()

if df.attrs.get("using_sample"):
    st.sidebar.info(
        "No CSV files found; showing generated sample data. "
        "Verify that the CSV file paths are correct."
    )

st.sidebar.markdown("### Filters")

if df.empty:
    st.warning("No fault data available.")
    st.stop()

min_date, max_date = df["date"].min(), df["date"].max()
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

time_cols = st.sidebar.columns(2)
start_time = time_cols[0].time_input("Start time", value=dt.time(0, 0), step=dt.timedelta(minutes=15))
end_time = time_cols[1].time_input("End time", value=dt.time(23, 59), step=dt.timedelta(minutes=15))

time_of_day_range = st.sidebar.slider(
    "Time of day",
    min_value=dt.time(0, 0),
    max_value=dt.time(23, 59),
    value=(dt.time(0, 0), dt.time(23, 59)),
    step=dt.timedelta(minutes=15),
)
start_time_of_day, end_time_of_day = time_of_day_range

all_tags = sorted(df["tag"].unique())
selected_tags = st.sidebar.multiselect("Tags", options=all_tags, default=all_tags)

all_statuses = sorted(df["verification_status"].unique())
selected_statuses = st.sidebar.multiselect(
    "Verification status", options=all_statuses, default=all_statuses
)

search_text = st.sidebar.text_input("Search description", "")

st.sidebar.markdown("---")
st.sidebar.caption(f"{len(df):,} total fault records loaded.")

# --------------------------------------------------------------------------
# Apply filters
# --------------------------------------------------------------------------
start_datetime = dt.datetime.combine(start_date, start_time)
end_datetime = dt.datetime.combine(end_date, end_time)

mask = (
    (df["FullTimestamp"] >= start_datetime)
    & (df["FullTimestamp"] <= end_datetime)
    & (df["time_of_day"] >= start_time_of_day)
    & (df["time_of_day"] <= end_time_of_day)
    & (df["tag"].isin(selected_tags))
    & (df["verification_status"].isin(selected_statuses))
)
if search_text.strip():
    mask &= df["description"].str.contains(search_text.strip(), case=False, na=False)

filtered = df[mask]

tag_color_map = {tag: TAG_COLORS[i % len(TAG_COLORS)] for i, tag in enumerate(all_tags)}


# --------------------------------------------------------------------------
# Helpers — timeline (original)
# --------------------------------------------------------------------------
def build_timeline(hall_df: pd.DataFrame, group_by_hall: bool = False) -> go.Figure:
    fig = go.Figure()

    if group_by_hall:
        # "All Halls" view: one row per hall, colored/shaped the same way,
        # with the hall shown on hover so points can still be told apart.
        tags_present = sorted(hall_df["tag"].unique())
        for tag in tags_present:
            tag_df = hall_df[hall_df["tag"] == tag]
            fig.add_trace(
                go.Scatter(
                    x=tag_df["FullTimestamp"],
                    y=tag_df["ShiftHall"],
                    mode="markers",
                    name=tag,
                    marker=dict(
                        size=12,
                        color=tag_color_map.get(tag, "#888888"),
                        line=dict(width=1, color="white"),
                        symbol=tag_df["verification_status"].map(
                            lambda s: "x" if s == "uncertain" else "circle"
                        ),
                    ),
                    customdata=tag_df.index,
                    text=tag_df["tag"],
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        + "%{text}<br>"
                        + "%{x|%Y-%m-%d %H:%M:%S}<br>"
                        + "<extra></extra>"
                    ),
                )
            )
        y_title = "Hall"
        n_rows = max(hall_df["ShiftHall"].nunique(), 1)
    else:
        tags_present = sorted(hall_df["tag"].unique())
        for tag in tags_present:
            tag_df = hall_df[hall_df["tag"] == tag]
            fig.add_trace(
                go.Scatter(
                    x=tag_df["FullTimestamp"],
                    y=tag_df["tag"],
                    mode="markers",
                    name=tag,
                    marker=dict(
                        size=12,
                        color=tag_color_map.get(tag, "#888888"),
                        line=dict(width=1, color="white"),
                        symbol=tag_df["verification_status"].map(
                            lambda s: "x" if s == "uncertain" else "circle"
                        ),
                    ),
                    customdata=tag_df.index,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        + "%{x|%Y-%m-%d %H:%M:%S}<br>"
                        + "<extra></extra>"
                    ),
                )
            )
        y_title = "Tag"
        n_rows = max(len(tags_present), 1)

    fig.update_layout(
        height=max(320, 90 * n_rows),
        xaxis_title="Time",
        yaxis_title=y_title,
        legend_title="Tag",
        hovermode="closest",
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(categoryorder="category ascending")
    return fig


def render_detail_card(row: pd.Series) -> None:
    with st.container(border=True):
        st.markdown(f"#### {row['tag']}")
        st.caption(row["FullTimestamp"].strftime("%Y-%m-%d %H:%M:%S"))
        st.write(row["description"])

        run_number = row.get("run_number")
        run_display = "—" if pd.isna(run_number) else f"{int(run_number)}"

        c1, c2, c3 = st.columns(3)
        c1.metric("Run number", run_display)
        c2.metric("Shift log #", row.get("ShiftLogNumber", "—"))
        c3.metric("Status", str(row.get("verification_status", "—")).capitalize())

        st.markdown(f"**Shift title:** {row.get('ShiftTitle', '—')}")
        st.markdown(f"**Shift hall:** {row.get('ShiftHall', '—')}")
        st.markdown(f"**Source file:** {row.get('source', '—')}")

        link_cols = st.columns(2)
        logbook_url = row.get("ShiftLogbookURL", "")
        fragment_url = row.get("FragmentLink", "")
        if logbook_url:
            link_cols[0].link_button("\U0001F517 Open shift logbook", logbook_url)
        if fragment_url:
            link_cols[1].link_button("\U0001F4CE Open fragment link", fragment_url)


def render_hall_tab(label: str, hall_df: pd.DataFrame, selection_key: str, group_by_hall: bool = False) -> None:
    """Renders the metrics + timeline + detail card + table for one tab."""
    m1, m2, m3 = st.columns(3)
    m1.metric("Faults in view", len(hall_df))
    m2.metric("Distinct tags", hall_df["tag"].nunique())
    m3.metric(
        "Uncertain",
        int((hall_df["verification_status"] == "uncertain").sum()),
    )

    if hall_df.empty:
        st.info("No faults for this view with the current filters.")
        return

    fig = build_timeline(hall_df, group_by_hall=group_by_hall)
    event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key=selection_key,
    )

    st.markdown("##### Fault details")
    points = event.selection.points if event and event.selection else []
    if points:
        idx = points[0]["customdata"]
        # customdata may come back as a 1-item list or a scalar
        if isinstance(idx, list):
            idx = idx[0]
        try:
            row = df.loc[idx]
            render_detail_card(row)
        except KeyError:
            st.info("Click a point on the timeline to see fault details here.")
    else:
        st.info("Click a point on the timeline to see fault details here.")

    with st.expander("View as table"):
        display_cols = [
            "FullTimestamp", "ShiftHall", "tag", "description", "run_number",
            "verification_status", "source", "ShiftLogbookURL",
        ]
        st.dataframe(
            hall_df[display_cols].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )


# --------------------------------------------------------------------------
# Helpers — analytics charts (original set)
# --------------------------------------------------------------------------
def _empty_note():
    st.info("No data for this chart with the current filters.")


def chart_faults_per_day(data: pd.DataFrame) -> go.Figure | None:
    """Faults per day (bar) + 7-day rolling average (line overlay)."""
    if data.empty:
        return None
    daily = data.groupby(data["FullTimestamp"].dt.date).size()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.asfreq("D", fill_value=0).sort_index()
    rolling = daily.rolling(7, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(go.Bar(x=daily.index, y=daily.values, name="Faults per day", marker_color="#669BBC"))
    fig.add_trace(go.Scatter(x=rolling.index, y=rolling.values, name="7-day rolling avg",
                              mode="lines", line=dict(color="#E4572E", width=2)))
    fig.update_layout(
        xaxis_title="Date", yaxis_title="Fault count",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def chart_cumulative_faults(data: pd.DataFrame) -> go.Figure | None:
    """Cumulative fault count over time."""
    if data.empty:
        return None
    daily = data.groupby(data["FullTimestamp"].dt.date).size()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.asfreq("D", fill_value=0).sort_index()
    cumulative = daily.cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cumulative.index, y=cumulative.values, mode="lines",
                              line=dict(color="#4E937A", width=2), fill="tozeroy",
                              fillcolor="rgba(78,147,122,0.15)", name="Cumulative faults"))
    fig.update_layout(
        xaxis_title="Date", yaxis_title="Cumulative fault count",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def chart_tag_frequency(data: pd.DataFrame) -> go.Figure | None:
    """Tag frequency bar chart, sorted descending."""
    if data.empty:
        return None
    counts = data["tag"].value_counts().sort_values(ascending=True)
    colors = [tag_color_map.get(t, "#888888") for t in counts.index]
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h", marker_color=colors))
    fig.update_layout(
        xaxis_title="Fault count", yaxis_title="Tag",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        height=max(320, 32 * len(counts)),
    )
    return fig


def chart_pareto(data: pd.DataFrame) -> go.Figure | None:
    """Pareto chart: tag counts (bar) + cumulative % (line)."""
    if data.empty:
        return None
    counts = data["tag"].value_counts().sort_values(ascending=False)
    cum_pct = counts.cumsum() / counts.sum() * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(x=counts.index, y=counts.values, name="Fault count",
                          marker_color="#669BBC", yaxis="y1"))
    fig.add_trace(go.Scatter(x=counts.index, y=cum_pct.values, name="Cumulative %",
                              mode="lines+markers", line=dict(color="#E4572E", width=2),
                              yaxis="y2"))
    fig.update_layout(
        xaxis_title="Tag",
        yaxis=dict(title="Fault count"),
        yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0, 105]),
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def chart_hall_tag_heatmap(data: pd.DataFrame) -> go.Figure | None:
    """Hall vs. tag heatmap of counts."""
    if data.empty:
        return None
    pivot = pd.crosstab(data["ShiftHall"], data["tag"])
    if pivot.empty:
        return None
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale="OrRd", colorbar=dict(title="Count"),
        hovertemplate="Hall: %{y}<br>Tag: %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Tag", yaxis_title="Hall",
        margin=dict(l=10, r=10, t=30, b=10),
        height=max(280, 60 * len(pivot.index)),
    )
    return fig


def chart_hall_tag_stacked(data: pd.DataFrame) -> go.Figure | None:
    """Stacked bar: tag composition within each hall."""
    if data.empty:
        return None
    pivot = pd.crosstab(data["ShiftHall"], data["tag"])
    if pivot.empty:
        return None
    fig = go.Figure()
    for tag in pivot.columns:
        fig.add_trace(go.Bar(x=pivot.index, y=pivot[tag], name=tag,
                              marker_color=tag_color_map.get(tag, "#888888")))
    fig.update_layout(
        barmode="stack", xaxis_title="Hall", yaxis_title="Fault count",
        legend_title="Tag", margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_hour_histogram(data: pd.DataFrame) -> go.Figure | None:
    """Hour-of-day histogram."""
    if data.empty:
        return None
    hours = data["FullTimestamp"].dt.hour
    counts = hours.value_counts().reindex(range(24), fill_value=0).sort_index()
    fig = go.Figure(go.Bar(x=[f"{h:02d}:00" for h in counts.index], y=counts.values,
                            marker_color="#A8C686"))
    fig.update_layout(
        xaxis_title="Hour of day", yaxis_title="Fault count",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_day_hour_heatmap(data: pd.DataFrame) -> go.Figure | None:
    """Day-of-week x hour-of-day 'punch card' heatmap."""
    if data.empty:
        return None
    tmp = data.copy()
    tmp["dow"] = tmp["FullTimestamp"].dt.day_name()
    tmp["hour"] = tmp["FullTimestamp"].dt.hour
    pivot = pd.crosstab(tmp["dow"], tmp["hour"]).reindex(DAY_ORDER).fillna(0)
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=[f"{h:02d}:00" for h in pivot.columns], y=pivot.index,
        colorscale="Blues", colorbar=dict(title="Count"),
        hovertemplate="%{y}, %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Hour of day", yaxis_title="Day of week",
        margin=dict(l=10, r=10, t=30, b=10), height=380,
    )
    return fig


def chart_status_over_time(data: pd.DataFrame) -> go.Figure | None:
    """Uncertain vs. accurate faults over time (stacked bar)."""
    if data.empty:
        return None
    tmp = data.copy()
    tmp["day"] = tmp["FullTimestamp"].dt.date
    pivot = pd.crosstab(tmp["day"], tmp["verification_status"])
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.asfreq("D", fill_value=0).sort_index()

    fig = go.Figure()
    for status in pivot.columns:
        fig.add_trace(go.Bar(x=pivot.index, y=pivot[status], name=status.capitalize(),
                              marker_color=STATUS_COLORS.get(status, "#888888")))
    fig.update_layout(
        barmode="stack", xaxis_title="Date", yaxis_title="Fault count",
        legend_title="Status", margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_pct_uncertain_by_tag(data: pd.DataFrame) -> go.Figure | None:
    """% uncertain by tag."""
    if data.empty:
        return None
    grp = data.groupby("tag")["verification_status"].apply(
        lambda s: (s == "uncertain").mean() * 100
    ).sort_values(ascending=True)
    fig = go.Figure(go.Bar(x=grp.values, y=grp.index, orientation="h",
                            marker_color="#C86B85"))
    fig.update_layout(
        xaxis_title="% uncertain", yaxis_title="Tag",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        height=max(320, 32 * len(grp)), xaxis_range=[0, 100],
    )
    return fig


def chart_faults_per_run(data: pd.DataFrame, top_n: int = 25) -> go.Figure | None:
    """Faults per run number — top N runs by fault count."""
    sub = data.dropna(subset=["run_number"])
    if sub.empty:
        return None
    counts = sub["run_number"].astype(int).value_counts().sort_values(ascending=False).head(top_n)
    counts = counts.sort_values(ascending=True)
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index.astype(str), orientation="h",
                            marker_color="#8367C7"))
    fig.update_layout(
        xaxis_title="Fault count", yaxis_title="Run number",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        height=max(320, 24 * len(counts)),
    )
    return fig


def chart_time_between_faults(data: pd.DataFrame) -> go.Figure | None:
    """Histogram of time (hours) between consecutive faults."""
    if len(data) < 2:
        return None
    ts = data["FullTimestamp"].sort_values()
    diffs_hours = ts.diff().dropna().dt.total_seconds() / 3600.0
    diffs_hours = diffs_hours[diffs_hours >= 0]
    if diffs_hours.empty:
        return None
    fig = go.Figure(go.Histogram(x=diffs_hours, nbinsx=40, marker_color="#F3A712"))
    fig.update_layout(
        xaxis_title="Hours between consecutive faults", yaxis_title="Count",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# --------------------------------------------------------------------------
# Helpers — analytics charts (new additions)
# --------------------------------------------------------------------------
def chart_mtbf_trend(data: pd.DataFrame, freq: str = "W") -> go.Figure | None:
    """Reliability trend: mean time between faults, binned (e.g. weekly).

    Rising values mean faults are getting further apart (improving);
    falling values mean faults are bunching up (degrading).
    """
    if len(data) < 3:
        return None
    ts = data["FullTimestamp"].sort_values().reset_index(drop=True)
    gap_hours = ts.diff().dt.total_seconds() / 3600.0
    tmp = pd.DataFrame({"FullTimestamp": ts, "gap_hours": gap_hours}).dropna()
    if tmp.empty:
        return None
    binned = tmp.set_index("FullTimestamp")["gap_hours"].resample(freq).mean().dropna()
    if binned.empty:
        return None
    fig = go.Figure(go.Scatter(
        x=binned.index, y=binned.values, mode="lines+markers",
        line=dict(color="#29335C", width=2), marker=dict(size=6),
    ))
    fig.update_layout(
        xaxis_title="Week", yaxis_title="Mean time between faults (hours)",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def get_longest_fault_free_streaks(data: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Top N longest gaps between consecutive faults, with the faults on either side."""
    if len(data) < 2:
        return pd.DataFrame()
    sub = data.sort_values("FullTimestamp").reset_index(drop=True)
    gap_hours = sub["FullTimestamp"].diff().dt.total_seconds() / 3600.0
    streaks = pd.DataFrame({
        "gap_hours": gap_hours,
        "streak_start": sub["FullTimestamp"].shift(1),
        "streak_end": sub["FullTimestamp"],
        "fault_before": sub["tag"].shift(1),
        "fault_after": sub["tag"],
    }).dropna(subset=["gap_hours"])
    streaks = streaks.sort_values("gap_hours", ascending=False).head(top_n)
    streaks["gap_hours"] = streaks["gap_hours"].round(1)
    return streaks.reset_index(drop=True)


def chart_tag_trend_area(data: pd.DataFrame, freq: str = "W") -> go.Figure | None:
    """Stacked area of fault counts per tag over time (binned, e.g. weekly)."""
    if data.empty:
        return None
    tmp = data.copy()
    tmp["period"] = tmp["FullTimestamp"].dt.to_period(freq).dt.start_time
    pivot = pd.crosstab(tmp["period"], tmp["tag"]).sort_index()
    if pivot.empty:
        return None
    fig = go.Figure()
    for tag in pivot.columns:
        color = tag_color_map.get(tag, "#888888")
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[tag], name=tag, mode="lines",
            stackgroup="one", line=dict(width=0.5, color=color),
        ))
    fig.update_layout(
        xaxis_title="Week", yaxis_title="Fault count", legend_title="Tag",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_faults_per_day_by_hall(data: pd.DataFrame) -> go.Figure | None:
    """Faults per day, one line per hall — lets you compare hall trends directly."""
    if data.empty:
        return None
    tmp = data.copy()
    tmp["day"] = tmp["FullTimestamp"].dt.date
    pivot = pd.crosstab(tmp["day"], tmp["ShiftHall"])
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.asfreq("D", fill_value=0).sort_index()
    if pivot.empty:
        return None
    fig = go.Figure()
    for i, hall in enumerate(pivot.columns):
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[hall], name=hall, mode="lines",
            line=dict(width=2, color=TAG_COLORS[i % len(TAG_COLORS)]),
        ))
    fig.update_layout(
        xaxis_title="Date", yaxis_title="Fault count", legend_title="Hall",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def chart_tag_cooccurrence(data: pd.DataFrame, window_minutes: int = 30) -> go.Figure | None:
    """Heatmap of how often pairs of tags occur within `window_minutes` of each other.

    Useful for spotting cascading failures (e.g. one fault type reliably
    followed by another shortly after).
    """
    if len(data) < 2:
        return None
    sub = data.sort_values("FullTimestamp").reset_index(drop=True)
    if len(sub) > COOCCURRENCE_ROW_CAP:
        sub = sub.tail(COOCCURRENCE_ROW_CAP).reset_index(drop=True)

    tags = sorted(sub["tag"].unique())
    if len(tags) < 2:
        return None

    times = sub["FullTimestamp"].to_numpy()
    tag_arr = sub["tag"].to_numpy()
    window = np.timedelta64(window_minutes, "m")

    counts = pd.DataFrame(0, index=tags, columns=tags, dtype=int)
    n = len(sub)
    # For each fault, find all later faults within the window (searchsorted
    # gives the boundary in O(log n); the inner loop only touches pairs that
    # are actually within the window, so this stays fast for sparse data).
    end_idx = np.searchsorted(times, times + window, side="right")
    for i in range(n):
        a = tag_arr[i]
        for j in range(i + 1, end_idx[i]):
            b = tag_arr[j]
            counts.loc[a, b] += 1
            counts.loc[b, a] += 1

    fig = go.Figure(go.Heatmap(
        z=counts.values, x=tags, y=tags, colorscale="Purples",
        colorbar=dict(title="Co-occurrences"),
        hovertemplate="%{y} + %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Tag", yaxis_title="Tag",
        margin=dict(l=10, r=10, t=30, b=10),
        height=max(320, 32 * len(tags)),
    )
    return fig


def chart_uncertain_age(data: pd.DataFrame) -> go.Figure | None:
    """Histogram of how old each 'uncertain' (manual review) record is."""
    sub = data[data["verification_status"] == "uncertain"]
    if sub.empty:
        return None
    now = pd.Timestamp.now()
    age_days = (now - sub["FullTimestamp"]).dt.total_seconds() / 86400.0
    fig = go.Figure(go.Histogram(x=age_days, nbinsx=30, marker_color="#E4572E"))
    fig.update_layout(
        xaxis_title="Age of uncertain record (days)", yaxis_title="Count",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_run_faults_boxplot_by_tag(data: pd.DataFrame) -> go.Figure | None:
    """Box plot of faults-per-run, grouped by tag (shows spread/outliers, not just totals)."""
    sub = data.dropna(subset=["run_number"])
    if sub.empty:
        return None
    run_tag_counts = sub.groupby(["run_number", "tag"]).size().reset_index(name="count")
    if run_tag_counts.empty:
        return None
    fig = go.Figure()
    for tag in sorted(run_tag_counts["tag"].unique()):
        vals = run_tag_counts.loc[run_tag_counts["tag"] == tag, "count"]
        fig.add_trace(go.Box(y=vals, name=tag, marker_color=tag_color_map.get(tag, "#888888")))
    fig.update_layout(
        xaxis_title="Tag", yaxis_title="Faults per run",
        margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def chart_calendar_heatmap(data: pd.DataFrame) -> go.Figure | None:
    """GitHub-contributions-style calendar heatmap of faults per day."""
    if data.empty:
        return None
    tmp = data.copy()
    tmp["date"] = tmp["FullTimestamp"].dt.normalize()
    daily = tmp.groupby("date").size()
    if daily.empty:
        return None
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0)

    cal = daily.reset_index()
    cal.columns = ["date", "count"]
    cal["weekday"] = cal["date"].dt.weekday  # 0 = Monday
    start = cal["date"].min()
    cal["week"] = ((cal["date"] - start).dt.days + start.weekday()) // 7

    pivot = cal.pivot(index="weekday", columns="week", values="count").reindex(range(7))
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    week_start_dates = cal.groupby("week")["date"].min()
    x_labels = [
        week_start_dates.get(w).strftime("%b %d") if week_start_dates.get(w) is not None else ""
        for w in pivot.columns
    ]

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=x_labels, y=weekday_labels,
        colorscale="Greens", colorbar=dict(title="Faults"),
        hovertemplate="Week of %{x}<br>%{y}: %{z}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Week", yaxis_title="",
        margin=dict(l=10, r=10, t=30, b=10), height=280,
    )
    return fig


def render_analytics_tab(data: pd.DataFrame) -> None:
    """Renders all the trend/composition/periodicity/status/run charts."""
    if data.empty:
        _empty_note()
        return

    # Hall filter, scoped to this tab only — lets you view analytics for a
    # single hall without affecting the per-hall timeline tabs.
    hall_options = ["All Halls"] + sorted(h for h in data["ShiftHall"].dropna().unique() if h)
    selected_hall = st.selectbox(
        "Hall", options=hall_options, key="analytics_hall_filter"
    )
    if selected_hall != "All Halls":
        data = data[data["ShiftHall"] == selected_hall]

    if data.empty:
        st.info("No faults for this hall with the current filters.")
        return

    st.markdown("### Trend")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Faults per day**")
        fig = chart_faults_per_day(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()
    with c2:
        st.markdown("**Cumulative faults over time**")
        fig = chart_cumulative_faults(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()

    st.markdown("**Calendar view**")
    fig = chart_calendar_heatmap(data)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        _empty_note()

    st.markdown("---")
    st.markdown("### Distribution & composition")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Tag frequency**")
        fig = chart_tag_frequency(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()
    with c2:
        st.markdown("**Pareto chart (tags)**")
        fig = chart_pareto(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()

    if selected_hall == "All Halls":
        # These two charts compare *across* halls, so they only make sense
        # when more than one hall is in view.
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Hall vs. tag heatmap**")
            fig = chart_hall_tag_heatmap(data)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                _empty_note()
        with c2:
            st.markdown("**Tag composition per hall (stacked)**")
            fig = chart_hall_tag_stacked(data)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                _empty_note()

    st.markdown("**Tag mix over time (stacked area, weekly)**")
    fig = chart_tag_trend_area(data)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        _empty_note()

    if selected_hall == "All Halls":
        st.markdown("**Faults per day by hall**")
        fig = chart_faults_per_day_by_hall(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()

    st.markdown("---")
    st.markdown("### Time-of-day & periodicity")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Hour-of-day histogram**")
        fig = chart_hour_histogram(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()
    with c2:
        st.markdown("**Day-of-week × hour-of-day heatmap**")
        fig = chart_day_hour_heatmap(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()

    st.markdown("---")
    st.markdown("### Reliability")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Mean time between faults (weekly trend)**")
        fig = chart_mtbf_trend(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()
    with c2:
        st.markdown("**Time between consecutive faults**")
        fig = chart_time_between_faults(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()

    st.markdown("**Longest fault-free streaks**")
    streaks = get_longest_fault_free_streaks(data)
    if not streaks.empty:
        st.dataframe(streaks, use_container_width=True, hide_index=True)
    else:
        _empty_note()

    st.markdown("**Tag co-occurrence (faults within 30 min of each other)**")
    fig = chart_tag_cooccurrence(data)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        _empty_note()

    st.markdown("---")
    st.markdown("### Verification status")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Uncertain vs. accurate over time**")
        fig = chart_status_over_time(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()
    with c2:
        st.markdown("**% uncertain by tag**")
        fig = chart_pct_uncertain_by_tag(data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            _empty_note()

# --------------------------------------------------------------------------
# Main layout
# --------------------------------------------------------------------------
st.title("Fault Timeline Dashboard")
st.caption(
    f"Showing {len(filtered):,} of {len(df):,} faults "
    f"({start_datetime:%Y-%m-%d %H:%M} to {end_datetime:%Y-%m-%d %H:%M}, "
    f"daily window {start_time_of_day.strftime('%H:%M')}–{end_time_of_day.strftime('%H:%M')})"
)

halls = sorted(filtered["ShiftHall"].dropna().unique())
if not halls and filtered.empty:
    st.info("No faults match the current filters.")
    st.stop()

tab_names = ["Analytics"] + halls + ["All Halls"]
tabs = st.tabs(tab_names)

for name, tab in zip(tab_names, tabs):
    with tab:
        if name == "All Halls":
            combined_df = filtered.sort_values("FullTimestamp")
            render_hall_tab(
                "All Halls",
                combined_df,
                selection_key="timeline_all_halls",
                group_by_hall=True,
            )
        elif name == "Analytics":
            render_analytics_tab(filtered.sort_values("FullTimestamp"))
        else:
            hall_df = filtered[filtered["ShiftHall"] == name].sort_values("FullTimestamp")
            render_hall_tab(
                name,
                hall_df,
                selection_key=f"timeline_{name}",
                group_by_hall=False,
            )