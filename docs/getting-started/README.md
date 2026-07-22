# CLAW-Agent Documentation

**CLAW-Agent** is an automated fault analysis pipeline for Jefferson Lab (JLab) shift summaries. It uses Large Language Models (LLMs) and semantic search to extract, validate, tag, and consolidate fault reports from JLab's operational logbooks.

---

## 📚 Documentation Index

### Getting Started (`getting-started/`)
- [Quick Start Guide](./QUICKSTART.md) - Get up and running in 5 minutes
- [Dashboard Guide](./DASHBOARD.md) - Streamlit visualization
- [Developer Testing](./DEVELOPER_TESTING.md) - Testing guidelines

### Configuration (`config/`)
- [Installation Guide](../config/INSTALLATION.md) - Detailed setup instructions
- [Configuration Reference](../config/CONFIGURATION.md) - All configuration options
- [Environment Variables](../config/ENVIRONMENT.md) - Complete env var reference
- [Tag Database](../config/TAG_DATABASE.md) - 16 fault categories
- [Output Formats](../config/OUTPUT_FORMATS.md) - CSV specifications

### Pipeline (`pipeline/`)
- [System Architecture](../pipeline/ARCHITECTURE.md) - High-level system design
- [Running the Pipeline](../pipeline/OPERATIONS_PIPELINE.md) - Execution options & troubleshooting
- [Data Loading](../pipeline/PIPELINE_DATA_LOADING.md) - JLab API integration
- [Fault Extraction](../pipeline/PIPELINE_FAULT_EXTRACTION.md) - LLM-based extraction
- [Fault Filtering](../pipeline/PIPELINE_FAULT_FILTERING.md) - Validation & cleaning
- [Tag Classification](../pipeline/PIPELINE_TAGGING.md) - ChromaDB semantic tagging
- [Timestamp Verification](../pipeline/PIPELINE_VERIFICATION.md) - Accuracy checking
- [Timestamp Fixing](../pipeline/PIPELINE_FIXING.md) - Correction workflow
- [Consolidation](../pipeline/PIPELINE_CONSOLIDATION.md) - Final output generation

### Utilities (`utils/`)
- [LLM Integration](../utils/UTILS_LLM.md) - OpenClaw subprocess calls
- [Text Processing](../utils/UTILS_TEXT.md) - Timestamp parsing & cleaning
- [Caching System](../utils/UTILS_CACHE.md) - API response caching
- [Shutdown Handling](../utils/UTILS_SHUTDOWN.md) - Graceful interrupt handling
- [Link Generation](../utils/UTILS_LINKS.md) - Text fragment URLs

### Scripts (`scripts/`)
- [Pipeline Runner](../scripts/SCRIPTS_PIPELINE.md) - run_pipeline.sh reference + cron scheduling
- [Auto Run Script](../scripts/SCRIPTS_AUTO.md) - Scheduled execution
- [Dashboard Manager](../scripts/SCRIPTS_DASHBOARD.md) - Deployment automation
- [Data Cleanup](../scripts/SCRIPTS_CLEAN.md) - Maintenance scripts
- [Test Runner](../scripts/SCRIPTS_TESTS.md) - Full test suite

---

## 🏗️ Quick Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAW-Agent Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   JLab API   │───▶│   Extract    │───▶│   Filter     │       │
│  │  (Data Load) │    │  (Faults)    │    │  (Validate)  │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                               │                   │             │
│                               ▼                   ▼             │
│                        ┌──────────────┐    ┌──────────────┐     │
│                        │    Tagging   │<───│  (Optional)  │     │
│                        │  (ChromaDB)  │    └──────────────┘     │
│                        └──────────────┘                         │
│                               │                                 │
│                               ▼                                 │
│                        ┌──────────────┐                         │
│                        │  Verify      │                         │
│                        │  (Timestamp) │                         │
│                        └──────────────┘                         │
│                               │                                 │
│                    ┌──────────┴──────────┐                      │
│                    ▼                     ▼                      │
│             ┌──────────────┐      ┌──────────────┐              │
│             │   Accurate   │      │  Inaccurate  │              │
│             └──────────────┘      └──────────────┘              │
│                    \                │                           │
│                     \               ▼                           │
│                      \       ┌──────────────┐                   │
│                       \      │    Fix       │                   │
│                        \     │ (Timestamp)  │                   │
│                         \    └──────────────┘                   │
│                          \          │                           │
│                           ▼         ▼                           │
│                        ┌──────────────────────┐                 │
│                        │   Consolidation      │                 │
│                        │   (Final Output)     │                 │
│                        └──────────────────────┘                 │
│                                     │                           │
│                                     ▼                           │
│                        ┌──────────────────────┐                 │
│                        │   Streamlit Dashboard│                 │
│                        └──────────────────────┘                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Features

- **Multi-Hall Support**: Process shift summaries from all 4 JLab halls (A, B, C, D)
- **LLM-Powered Extraction**: Uses OpenClaw agents for intelligent fault extraction
- **Semantic Tagging**: ChromaDB vector search for accurate fault classification
- **Parallel Processing**: ThreadPoolExecutor for 2.5x performance improvement
- **Timestamp Correction**: Automated fixing of inaccurate timestamps
- **SSH Tunneling**: Secure remote access to JLab infrastructure
- **Interactive Dashboard**: Streamlit visualization with timeline and analytics
- **Caching System**: Reduces API calls with intelligent LRU cache
- **Graceful Shutdown**: Clean interrupt handling for long-running jobs

---

## 📦 Project Structure

```
CLAW-Agent/
├── src/                         # Source code
│   ├── pipeline.py              # Main orchestrator
│   ├── config.py                # Configuration management
│   ├── analysis/                # Pipeline stage modules
│   │   ├── shift_summary.py     # Fault extraction
│   │   ├── fault_filter.py      # Fault validation
│   │   ├── tag_extraction.py    # Semantic tagging
│   │   ├── accuracy_test.py     # Timestamp verification
│   │   ├── fixer.py             # Timestamp correction
│   │   └── verifyer.py          # Final consolidation
│   ├── data/                    # Data loading
│   │   └── data_loading.py      # JLab API integration
│   ├── utils/                   # Utility modules
│   │   ├── llm_utils.py         # LLM interaction
│   │   ├── text_utils.py        # Text processing
│   │   ├── cache_utils.py       # Caching system
│   │   ├── logging_utils.py     # Logging configuration
│   │   ├── shutdown.py          # Interrupt handling
│   │   └── link_logic.py        # URL fragment generation
│   └── frontend/                # Dashboard
│       └── app.py               # Streamlit app
├── data/                        # Data directories
│   ├── raw/                     # Raw API responses
│   ├── processed/               # Intermediate outputs
│   ├── verified/                # Verified faults
│   ├── fixed/                   # Fixed timestamps
│   └── final_output/            # Final CSV outputs
├── tag_db/                      # Tag database
│   ├── tags.json                # 16 fault categories
│   └── chroma_db/               # Vector embeddings
├── scripts/                     # Shell scripts
│   ├── run_pipeline.sh          # Pipeline runner
│   ├── auto_run.sh              # Scheduled execution
│   ├── manage_dashboard.sh      # Dashboard deployment
│   ├── clean_data.sh            # Data cleanup
│   └── run_all_tests.sh         # Test suite
├── testing/                     # Test data and fixtures
├── .env                         # Environment configuration
├── requirements.txt             # Python dependencies
└── docs/                        # This documentation
```

---

## 🚀 Quick Start

```bash
# 1. Clone and setup
cd /home/sec-researchonly/Desktop/CLAW-Agent
cp .env.example .env
# Edit .env with your credentials

# 2. Install dependencies
./scripts/run_pipeline.sh --help  # Auto-installs venv

# 3. Run pipeline (default: 2 days ago to 1 day ago)
./scripts/run_pipeline.sh

# 4. View results
streamlit run src/frontend/app.py
```

---

## 📊 Sample Output

The pipeline generates several CSV files:

**`data/final_output/all_shift_faults.csv`**
```csv
FullTimestamp,timestamp,description,tag,run_number,ShiftLogNumber,verification_status
2025-04-02 04:00:00,04:00,RF issues,Accelerator,,4346807,accurate
2025-04-03 00:38:00,00:38,2L05 dropped filaments,Vacuum,,4347272,accurate
```

---

## 🎯 Use Cases

1. **Daily Fault Analysis**: Run pipeline nightly to extract new faults
2. **Historical Analysis**: Query date ranges for trend analysis
3. **Hall-Specific Reports**: Filter by specific experimental halls
4. **Tag-Based Analytics**: Analyze fault distribution by category
5. **Timestamp Accuracy Studies**: Verify and improve data quality

---

## 📞 Support

- **Documentation**: Browse this `/docs` folder
- **Source Code**: See `src/` for implementation details
- **Issues**: Check `testing/` for known issues and test cases

---

## 📝 Version Information

- **Project**: CLAW-Agent
- **Purpose**: Jefferson Lab Shift Summary Fault Analysis
- **Dependencies**: pandas, numpy, ollama, chromadb, streamlit, sentence-transformers
- **Python**: 3.8+
- **Last Updated**: 2026-07-17

---

*For detailed information, navigate to the specific documentation pages listed above.*

---

## 📖 Full Documentation Index

For a complete index with all cross-references, see [`reference/DOCUMENTATION_INDEX.md`](../reference/DOCUMENTATION_INDEX.md).