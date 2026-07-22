"""
Test-specific configuration override for CLAW-Agent testing.
Ensures testing scripts write to isolated test output directories,
never touching the main project's data/final_output or other data folders.
"""
from pathlib import Path

# Base test directory
TEST_BASE_DIR = Path(__file__).parent.resolve()

# Isolated test data directories (all under testing/)
TEST_RAW_DIR = TEST_BASE_DIR / "test_data" / "raw"
TEST_PROCESSED_DIR = TEST_BASE_DIR / "test_data" / "processed"
TEST_FINAL_OUTPUT_DIR = TEST_BASE_DIR / "test_data" / "final_output"
TEST_VERIFIED_DIR = TEST_BASE_DIR / "test_data" / "verified"
TEST_FIXED_DIR = TEST_BASE_DIR / "test_data" / "fixed"

# Test-specific file paths (mirroring config.py structure)
TEST_SHIFT_SUMMARY_JSON = TEST_RAW_DIR / "shift_summary.JSON"
TEST_SHIFT_SUMMARY_CSV = TEST_RAW_DIR / "shift_summary.csv"
TEST_PROCESSED_SUMMARIES_CSV = TEST_PROCESSED_DIR / "processed_summaries.csv"
TEST_ALL_FAULTS_CSV = TEST_FINAL_OUTPUT_DIR / "all_shift_faults.csv"
TEST_NOT_FAULTS_CSV = TEST_PROCESSED_DIR / "not_faults.csv"
TEST_ACCURATE_CSV = TEST_VERIFIED_DIR / "accurate.csv"
TEST_INACCURATE_CSV = TEST_VERIFIED_DIR / "inaccurate.csv"
TEST_FIXED_CSV = TEST_FIXED_DIR / "fixed.csv"
TEST_MANUAL_CHECK_CSV = TEST_FINAL_OUTPUT_DIR / "manual_check.csv"

# Ensure all test directories exist
for dir_path in [TEST_RAW_DIR, TEST_PROCESSED_DIR, TEST_FINAL_OUTPUT_DIR, TEST_VERIFIED_DIR, TEST_FIXED_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


def override_main_config():
    """
    Override the main config module's paths with test-specific paths.
    Call this at the start of any test script before importing pipeline modules.
    
    This ensures all pipeline operations write to isolated test directories.
    """
    import sys
    from pathlib import Path
    
    # Add src directory to path if not already there
    script_dir = Path(__file__).parent.resolve()
    src_dir = script_dir.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    # Get the main config module
    if 'config' in sys.modules:
        config_mod = sys.modules['config']
    else:
        # Import and then override
        import config as config_mod
    
    # Override all path constants
    config_mod.BASE_DIR = TEST_BASE_DIR
    config_mod.DATA_DIR = TEST_BASE_DIR / "test_data"
    config_mod.RAW_DIR = TEST_RAW_DIR
    config_mod.PROCESSED_DIR = TEST_PROCESSED_DIR
    config_mod.FINAL_OUTPUT_DIR = TEST_FINAL_OUTPUT_DIR
    config_mod.VERIFIED_DIR = TEST_VERIFIED_DIR
    config_mod.FIXED_DIR = TEST_FIXED_DIR
    
    config_mod.SHIFT_SUMMARY_JSON = TEST_SHIFT_SUMMARY_JSON
    config_mod.SHIFT_SUMMARY_CSV = TEST_SHIFT_SUMMARY_CSV
    config_mod.PROCESSED_SUMMARIES_CSV = TEST_PROCESSED_SUMMARIES_CSV
    config_mod.ALL_FAULTS_CSV = TEST_ALL_FAULTS_CSV
    config_mod.NOT_FAULTS_CSV = TEST_NOT_FAULTS_CSV
    config_mod.ACCURATE_CSV = TEST_ACCURATE_CSV
    config_mod.INACCURATE_CSV = TEST_INACCURATE_CSV
    config_mod.FIXED_CSV = TEST_FIXED_CSV
    config_mod.MANUAL_CHECK_CSV = TEST_MANUAL_CHECK_CSV
    
    return config_mod


def clean_test_data():
    """
    Remove all test data directories.
    Call this to clean up after testing.
    """
    import shutil
    test_data_dir = TEST_BASE_DIR / "test_data"
    if test_data_dir.exists():
        shutil.rmtree(test_data_dir)
        print(f"Cleaned test data directory: {test_data_dir}")