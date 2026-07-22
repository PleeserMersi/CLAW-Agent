# CLAW-Agent Documentation Index

Complete index of all documentation files organized by category.

---

## 📁 Documentation Structure

### Getting Started (`getting-started/`)
- **[README.md](../getting-started/README.md)** - Project overview and quick start
- **[QUICKSTART.md](../getting-started/QUICKSTART.md)** - 5-minute setup guide
- **[DASHBOARD.md](../getting-started/DASHBOARD.md)** - Streamlit dashboard guide
- **[DEVELOPER_TESTING.md](../getting-started/DEVELOPER_TESTING.md)** - Testing guidelines

### Configuration (`config/`)
- **[CONFIGURATION.md](../config/CONFIGURATION.md)** - Complete configuration reference
- **[ENVIRONMENT.md](../config/ENVIRONMENT.md)** - Environment variables reference
- **[INSTALLATION.md](../config/INSTALLATION.md)** - Detailed installation instructions
- **[TAG_DATABASE.md](../config/TAG_DATABASE.md)** - 16 fault categories reference
- **[OUTPUT_FORMATS.md](../config/OUTPUT_FORMATS.md)** - CSV output specifications

### Pipeline (`pipeline/`)
- **[ARCHITECTURE.md](../pipeline/ARCHITECTURE.md)** - System architecture and design patterns
- **[OPERATIONS_PIPELINE.md](../pipeline/OPERATIONS_PIPELINE.md)** - Running and operating pipeline
- **[PIPELINE_DATA_LOADING.md](../pipeline/PIPELINE_DATA_LOADING.md)** - JLab API integration
- **[PIPELINE_FAULT_EXTRACTION.md](../pipeline/PIPELINE_FAULT_EXTRACTION.md)** - LLM-based fault extraction
- **[PIPELINE_FAULT_FILTERING.md](../pipeline/PIPELINE_FAULT_FILTERING.md)** - Validation and filtering
- **[PIPELINE_TAGGING.md](../pipeline/PIPELINE_TAGGING.md)** - Semantic tag classification
- **[PIPELINE_VERIFICATION.md](../pipeline/PIPELINE_VERIFICATION.md)** - Timestamp accuracy verification
- **[PIPELINE_FIXING.md](../pipeline/PIPELINE_FIXING.md)** - Timestamp correction
- **[PIPELINE_CONSOLIDATION.md](../pipeline/PIPELINE_CONSOLIDATION.md)** - Final output generation

### Utilities (`utils/`)
- **[UTILS_LLM.md](../utils/UTILS_LLM.md)** - LLM interaction utilities
- **[UTILS_TEXT.md](../utils/UTILS_TEXT.md)** - Text processing (HTML cleaning, timestamp parsing)
- **[UTILS_CACHE.md](../utils/UTILS_CACHE.md)** - Caching system (LRU with TTL)
- **[UTILS_SHUTDOWN.md](../utils/UTILS_SHUTDOWN.md)** - Shutdown handling (graceful interrupt)
- **[UTILS_LINKS.md](../utils/UTILS_LINKS.md)** - Link generation (text fragment URLs)

### Scripts (`scripts/`)
- **[SCRIPTS_PIPELINE.md](../scripts/SCRIPTS_PIPELINE.md)** - run_pipeline.sh reference
- **[SCRIPTS_AUTO.md](../scripts/SCRIPTS_AUTO.md)** - auto_run.sh convenience script
- **[SCRIPTS_DASHBOARD.md](../scripts/SCRIPTS_DASHBOARD.md)** - manage_dashboard.sh (start/stop/status)
- **[SCRIPTS_CLEAN.md](../scripts/SCRIPTS_CLEAN.md)** - clean_data.sh (data cleanup)
- **[SCRIPTS_TESTS.md](../scripts/SCRIPTS_TESTS.md)** - run_all_tests.sh (test runner)

### Reference (`reference/`)
- **[DOCUMENTATION_INDEX.md](../reference/DOCUMENTATION_INDEX.md)** - This file: complete documentation index

---

## 📖 Quick Navigation

### I want to...

#### Get started quickly
→ **[QUICKSTART.md](../getting-started/QUICKSTART.md)**

#### Install and set up
→ **[INSTALLATION.md](../config/INSTALLATION.md)**

#### Understand how it works
→ **[ARCHITECTURE.md](../pipeline/ARCHITECTURE.md)**

#### Configure the system
→ **[CONFIGURATION.md](../config/CONFIGURATION.md)**

#### Run the pipeline
→ **[OPERATIONS_PIPELINE.md](../pipeline/OPERATIONS_PIPELINE.md)**

#### Understand a specific pipeline stage
→ See **[Pipeline Stages](#pipeline-stages-detailed)** section

#### Troubleshoot issues
→ **[OPERATIONS_PIPELINE.md](../pipeline/OPERATIONS_PIPELINE.md)** (Troubleshooting section)

#### View output format
→ **[OUTPUT_FORMATS.md](../config/OUTPUT_FORMATS.md)**

#### Use the dashboard
→ **[DASHBOARD.md](../getting-started/DASHBOARD.md)**

#### Add new tags
→ **[TAG_DATABASE.md](../config/TAG_DATABASE.md)**

#### Understand environment variables
→ **[ENVIRONMENT.md](../config/ENVIRONMENT.md)**

#### Learn about utilities
→ See **[Utilities](#utilities)** section

#### Run tests
→ **[SCRIPTS_TESTS.md](../scripts/SCRIPTS_TESTS.md)** or **[DEVELOPER_TESTING.md](../getting-started/DEVELOPER_TESTING.md)**

---

## 📊 Documentation Statistics

| Category | Folder | Files | Total Pages |
|----------|--------|-------|-------------|
| Getting Started | `getting-started/` | 4 | ~30 |
| Configuration | `config/` | 5 | ~35 |
| Pipeline | `pipeline/` | 9 | ~100 |
| Utilities | `utils/` | 5 | ~35 |
| Scripts | `scripts/` | 5 | ~20 |
| Reference | `reference/` | 1 | ~5 |
| **Total** | **6 folders** | **29** | **~225** |

---

## 🎯 Recommended Reading Order

### For New Users
1. `getting-started/README.md`
2. `getting-started/QUICKSTART.md`
3. `config/INSTALLATION.md`
4. `pipeline/OPERATIONS_PIPELINE.md`
5. `getting-started/DASHBOARD.md`

### For Developers
1. `getting-started/README.md`
2. `pipeline/ARCHITECTURE.md`
3. `pipeline/PIPELINE_FAULT_EXTRACTION.md`
4. `pipeline/PIPELINE_TAGGING.md`
5. `config/CONFIGURATION.md`

### For Administrators
1. `getting-started/README.md`
2. `config/CONFIGURATION.md`
3. `pipeline/OPERATIONS_PIPELINE.md`
4. `config/ENVIRONMENT.md`
5. `config/TAG_DATABASE.md`

### For Troubleshooting
1. `pipeline/OPERATIONS_PIPELINE.md` (Troubleshooting section)
2. `config/INSTALLATION.md` (Troubleshooting section)
3. `getting-started/DEVELOPER_TESTING.md` (Debugging tips)

---

## 🔍 Search Tips

### Find information about...

**Fault Extraction**:
- `pipeline/PIPELINE_FAULT_EXTRACTION.md`
- `pipeline/ARCHITECTURE.md` (Section: Fault Extraction)

**Tagging**:
- `pipeline/PIPELINE_TAGGING.md`
- `config/TAG_DATABASE.md`

**Timestamp Handling**:
- `pipeline/PIPELINE_VERIFICATION.md`
- `pipeline/PIPELINE_FIXING.md`
- `utils/UTILS_TEXT.md` (Timestamp parsing details)

**Configuration**:
- `config/CONFIGURATION.md`
- `config/ENVIRONMENT.md`

**Troubleshooting**:
- `pipeline/OPERATIONS_PIPELINE.md` (Troubleshooting section)
- `config/INSTALLATION.md` (Troubleshooting section)
- `getting-started/DEVELOPER_TESTING.md`

**Performance**:
- `config/CONFIGURATION.md` (Batch Size Configuration)
- `pipeline/OPERATIONS_PIPELINE.md` (Performance Tuning)

**Utilities**:
- `utils/UTILS_LLM.md` - LLM calls
- `utils/UTILS_TEXT.md` - Text processing
- `utils/UTILS_CACHE.md` - Caching
- `utils/UTILS_SHUTDOWN.md` - Interrupt handling
- `utils/UTILS_LINKS.md` - URL fragments

**Scripts**:
- `scripts/SCRIPTS_PIPELINE.md` - Main runner
- `scripts/SCRIPTS_AUTO.md` - Auto date handling
- `scripts/SCRIPTS_DASHBOARD.md` - Dashboard management
- `scripts/SCRIPTS_CLEAN.md` - Data cleanup
- `scripts/SCRIPTS_TESTS.md` - Test runner

---

## 📝 Documentation Quality

All documentation includes:
- ✅ Clear explanations
- ✅ Code examples
- ✅ Diagrams where helpful
- ✅ Troubleshooting sections
- ✅ Related documentation links
- ✅ Usage examples

---

## 🔄 Documentation Maintenance

### Last Updated
- **All files**: 2026-07-17

### To Update Documentation
1. Edit the relevant `.md` file in `docs/`
2. Update version/date in file header
3. Update DOCUMENTATION_INDEX.md if adding new files
4. Test examples in documentation

---

## 📞 Support

For questions not covered in documentation:
1. Check the relevant pipeline stage documentation
2. Review ARCHITECTURE.md for system overview
3. Check CONFIGURATION.md for settings
4. Review troubleshooting sections

---

*Documentation index: 2026-07-17*
*CLAW-Agent v1.0*
*Total: 29 documentation files in 6 folders, ~225 pages*