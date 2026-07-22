# Dashboard Guide

Complete guide to the CLAW-Agent Streamlit dashboard.

---

## Overview

The dashboard provides comprehensive interactive visualization of fault data with timeline views, analytics charts, hall-specific analysis, and detailed filtering capabilities.

**Module**: `src/frontend/app.py`

**Launch Command**:
```bash
cd /home/sec-researchonly/Desktop/CLAW-Agent
python3 -m streamlit run src/frontend/app.py
```

Dashboard opens at `http://localhost:8501`

---

## Input Files

### Required Files

| File | Location | Purpose |
|------|----------|---------|  
| `all_shift_faults.csv` | `data/final_output/` | Verified faults (verification_status = "accurate") |
| `manual_check.csv` | `data/final_output/` | Faults needing manual review (verification_status = "uncertain") |

### Fallback

If files don't exist, dashboard generates sample data for demonstration.

---

## Navigation

The dashboard uses a tabbed interface:

- **Analytics**: Comprehensive trend, distribution, and reliability charts
- **Hall A/B/C/D**: Individual hall timelines
- **All Halls**: Combined timeline view across all halls

---

## Sidebar Filters

All views respect these filters:

- **Date range**: Start/end date selection
- **Time of day**: Start/end time selection  
- **Tags**: Multi-select tag filter
- **Verification status**: Filter by "accurate" or "uncertain"
- **Search**: Text search in fault descriptions

---

## Features

### Timeline Views (Per Hall and All Halls)

**Display**: Interactive Plotly scatter plots showing faults over time

**Interactions**:
- Click any data point to view detailed fault card
- Hover for timestamp and tag info
- Pan and zoom to explore time ranges

**Views**:
- **All Halls**: Stacked view with one row per hall, colored by tag
- **Single Hall**: Faults plotted by tag over time

**Fault Detail Card** (on click):
- Tag, timestamp, description
- Run number, shift log number
- Verification status
- Shift hall and title
- Direct links to shift logbook and fragment link

### Analytics Tab

#### Trend Charts
- **Faults per day**: Bar chart with 7-day rolling average overlay
- **Cumulative faults**: Running total over time
- **Calendar heatmap**: GitHub-style contribution heatmap
- **Tag trend area**: Stacked area chart showing tag composition over weeks
- **Faults per day by hall**: Multi-line chart comparing hall trends

#### Distribution & Composition
- **Tag frequency**: Horizontal bar chart of tag counts
- **Pareto chart**: Tag counts with cumulative percentage line
- **Hall vs. tag heatmap**: Matrix showing fault distribution
- **Tag composition per hall**: Stacked bar chart

#### Time-of-Day & Periodicity
- **Hour-of-day histogram**: Fault distribution across 24 hours
- **Day-of-week × hour heatmap**: "Punch card" showing when faults occur

#### Reliability Analysis
- **Mean time between faults (MTBF)**: Weekly trend showing reliability changes
- **Time between faults histogram**: Distribution of gaps between consecutive faults
- **Longest fault-free streaks**: Table of top 10 longest gaps with surrounding fault tags
- **Tag co-occurrence**: Heatmap showing which tags appear within 30 minutes of each other

#### Verification Status
- **Uncertain vs. accurate over time**: Stacked bar chart
- **% uncertain by tag**: Bar showing review backlog per tag

### Fault Details Table

Each hall tab includes an expandable table view with:
- Full timestamp, hall, tag, description
- Run number, verification status, source file
- Shift logbook URL

**Actions**:
- Sort by any column
- Filter via sidebar controls
- Search descriptions

---

## Usage

### Launch Dashboard

```bash
cd /home/sec-researchonly/Desktop/CLAW-Agent
python3 -m streamlit run src/frontend/app.py
```

### Navigate Sections

1. **All Halls tab**: View combined timeline across all halls
2. **Hall-specific tabs**: Focus on individual hall data
3. **Analytics tab**: Explore trends, distributions, and reliability metrics
4. **Sidebar**: Apply filters to all views simultaneously
5. **Click timeline points**: View detailed fault information
6. **Expand "View as table"**: See raw data for current view

---

## Customization

### Page Configuration

Edit `src/frontend/app.py`:

```python
st.set_page_config(
    page_title="Fault Timeline Dashboard",
    page_icon="🚨",
    layout="wide",
)
```

### Color Schemes

Modify `TAG_COLORS` and `STATUS_COLORS` lists in app.py for custom colors.

### Chart Configurations

- Co-occurrence window: Change `window_minutes` parameter in `chart_tag_cooccurrence()`
- MTBF binning: Change `freq` parameter (e.g., "W" for weekly, "D" for daily)
- Row cap for large datasets: Adjust `COOCCURRENCE_ROW_CAP` constant

---

## Troubleshooting

### "No data found"

**Cause**: Output files don't exist

**Fix**:
```bash
# Run pipeline first
./scripts/run_pipeline.sh

# Or dashboard will auto-generate sample data for demonstration
```

### Dashboard won't start

**Cause**: Missing dependencies

**Fix**:
```bash
pip install streamlit plotly pandas numpy
```

### Charts show no data

**Cause**: Filters may be too restrictive

**Fix**: Check sidebar filters - widen date range, select more tags, or clear search text.

---

## Related Documentation

- [Consolidation](./PIPELINE_CONSOLIDATION.md) - Final output generation
- [Output Formats](./OUTPUT_FORMATS.md) - CSV specifications
- [Operations Pipeline](./OPERATIONS_PIPELINE.md) - Operational details

---

## Usage

### Launch Dashboard

```bash
cd /home/sec-researchonly/Desktop/CLAW-Agent
python3 -m streamlit run src/frontend/app.py
```

Dashboard opens at `http://localhost:8501`

### Navigate Sections

1. **Overview**: Summary statistics
2. **Timeline**: Faults over time
3. **Tags**: Tag distribution
4. **Halls**: Hall comparison
5. **Details**: Full fault table

### Export Data

Dashboard allows exporting filtered data as CSV.

---

## Customization

### Page Configuration

Edit `src/frontend/app.py`:

```python
st.set_page_config(
    page_title="Fault Timeline Dashboard",
    page_icon="🚨",
    layout="wide",
)
```

### Color Schemes

Modify `TAG_COLORS` list in app.py for custom tag colors.

---

## Troubleshooting

### "No data found"

**Cause**: Output files don't exist

**Fix**:
```bash
# Run pipeline first
./scripts/run_pipeline.sh

# Or create sample data
python3 -m streamlit run src/frontend/app.py  # Uses sample data if files missing
```

### Dashboard won't start

**Cause**: Streamlit not installed

**Fix**:
```bash
pip install streamlit plotly
```

---

## Related Documentation

- [Consolidation](./PIPELINE_CONSOLIDATION.md) - Final output generation
- [Output Formats](./OUTPUT_FORMATS.md) - CSV specifications

---

*For operational details, see [OPERATIONS_PIPELINE.md](./OPERATIONS_PIPELINE.md).*