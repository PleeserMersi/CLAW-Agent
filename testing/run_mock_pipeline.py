#!/usr/bin/env python3
"""
Mock Data Pipeline Runner for CLAW-Agent Testing

This script runs the CLAW-Agent pipeline using mock shift summaries instead of
live JLab API data. It tests different batching sizes and evaluates accuracy.

The mock data project is integrated as a subfolder that:
1. Generates mock shift summaries and ground truth faults
2. Runs the CLAW-Agent pipeline with different batching sizes
3. Saves ALL output data to testing/test_data/ (isolated from main data/ folders)
4. Runs accuracy tests and generates graphs
5. Supports parallel workers testing with fixed batch size 5

IMPORTANT: This script uses an isolated test_data/ directory under testing/
to prevent any modifications to the main project's data/ folders.

Usage:
    python run_mock_pipeline.py [--levels easy medium hard] [--batch-sizes 1 2 4 8]
    python run_mock_pipeline.py --parallel-workers 1 2 4 6 --batch-size 5
"""

import argparse
import os
import sys
import time
import json
import shutil
import subprocess
import signal
import logging
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# CRITICAL: Override config paths BEFORE importing any pipeline modules
# This ensures all test operations write to isolated test_data/ directory
# and never touch the main project's data/ folders
import test_config
test_config.override_main_config()

import pandas as pd

# Test directory setup - use absolute path based on script location
SCRIPT_DIR = Path(__file__).parent.resolve()
TEST_DIR = SCRIPT_DIR
MOCK_SUMMARIES_DIR = TEST_DIR / "mock_summaries"
ACCURACY_TESTER_DIR = TEST_DIR / "accuracy_tester"
BENCHMARKS_DIR = TEST_DIR / "benchmarks"
TEST_OUTPUT_DIR = TEST_DIR / "pipeline_output"

# Ensure output directories exist
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Global flag for graceful interrupt
interrupted = False
shutdown_in_progress = False

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global interrupted, shutdown_in_progress
    if not interrupted:
        interrupted = True
        shutdown_in_progress = True
        
        # Also trigger the shutdown event in shutdown.py so LLM calls stop retrying
        try:
            from utils.shutdown import request_shutdown
            request_shutdown()
        except ImportError:
            pass  # shutdown.py not available yet
        
        print("\n\n" + "=" * 60)
        print("INTERRUPTED: Shutting down gracefully...")
        print("=" * 60)
        print("Please wait for current operations to complete...")
        print("(Press Ctrl+C again to force exit immediately)")
        print("=" * 60 + "\n")
    else:
        print("\nForce exiting immediately...")
        # Use os._exit to bypass thread cleanup
        import os
        os._exit(130)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

# Add shutdown filter to suppress log messages during shutdown
class ShutdownFilter(logging.Filter):
    """Filter to suppress log messages during shutdown."""
    def filter(self, record):
        return not shutdown_in_progress

logging.getLogger().addFilter(ShutdownFilter())

def setup_ssh_tunnel(verbose: bool = False):
    """
    Setup SSH tunnel for JLab access and Ollama.
    
    Returns:
        subprocess.Popen: Tunnel process if created, None otherwise
    """
    import time
    import os
    
    logger = logging.getLogger(__name__)
    
    # Parse SSH tunnels from environment variables (same logic as config.py)
    ssh_tunnels = []
    n = 1
    while True:
        local_key = f"SSH_TUNNEL_{n}_LOCAL"
        remote_key = f"SSH_TUNNEL_{n}_REMOTE"
        
        local_port = os.getenv(local_key)
        remote_port = os.getenv(remote_key)
        
        if local_port is None and remote_port is None:
            break
        
        if local_port is None or remote_port is None:
            logger.warning(f"Incomplete SSH tunnel configuration for pair {n}: "
                          f"{local_key}={local_port}, {remote_key}={remote_port}")
            n += 1
            continue
        
        try:
            ssh_tunnels.append((int(local_port), int(remote_port)))
        except ValueError:
            logger.warning(f"Invalid port numbers for SSH tunnel {n}: "
                          f"{local_key}={local_port}, {remote_key}={remote_port}")
        
        n += 1
    
    # Kill any existing processes on configured tunnel ports
    print("Cleaning up any existing tunnel processes...")
    logger.info("Cleaning up any existing tunnel processes...")
    for local_port, _ in ssh_tunnels:
        subprocess.run(["fuser", "-k", f"{local_port}/tcp"], capture_output=True)
    
    time.sleep(1)
    
    # Create SSH tunnel for JLab access and Ollama
    # Use credentials from environment variables
    ssh_username = os.getenv("SSH_USERNAME")
    ssh_host = os.getenv("SSH_HOST")
    
    if not ssh_username or not ssh_host:
        msg = "SSH credentials not configured. Set SSH_USERNAME and SSH_HOST in environment variables."
        print(msg)
        logger.error(msg)
        return None
    
    if not ssh_tunnels:
        msg = "SSH credentials configured but no tunnels defined. Running without tunneling."
        print(msg)
        logger.info(msg)
        return None
    
    # Build SSH command with dynamic port forwards
    ssh_args = ["ssh", "-o", "LogLevel=ERROR", "-N"]
    for local_port, remote_port in ssh_tunnels:
        ssh_args.extend(["-L", f"{local_port}:127.0.0.1:{remote_port}"])
    ssh_args.append(f"{ssh_username}@{ssh_host}")
    
    msg = f"Establishing SSH tunnel to {ssh_username}@{ssh_host} with {len(ssh_tunnels)} tunnel(s):"
    print(msg)
    logger.info(msg)
    for local_port, remote_port in ssh_tunnels:
        port_msg = f"  {local_port} -> {remote_port}"
        print(port_msg)
        logger.info(port_msg)
    
    tunnel = subprocess.Popen(ssh_args)
    
    # Wait for tunnel to establish
    time.sleep(2)
    
    if tunnel.poll() is not None:
        msg = "SSH tunnel failed to start. Check SSH configuration."
        print(msg)
        logger.error(msg)
        return None
    
    msg = "SSH tunnel established successfully."
    print(msg)
    logger.info(msg)
    return tunnel


def cleanup_ssh_tunnel(tunnel, verbose: bool = False):
    """
    Cleanup SSH tunnel and kill port processes.
    """
    import time
    import os
    
    logger = logging.getLogger(__name__)
    
    if tunnel is not None:
        print("Cleaning up SSH tunnel...")
        logger.info("Cleaning up SSH tunnel...")
        tunnel.terminate()
        tunnel.wait()
        time.sleep(1)
    
    # Parse tunnels again to know which ports to clean
    ssh_tunnels = []
    n = 1
    while True:
        local_key = f"SSH_TUNNEL_{n}_LOCAL"
        remote_key = f"SSH_TUNNEL_{n}_REMOTE"
        
        local_port = os.getenv(local_key)
        remote_port = os.getenv(remote_key)
        
        if local_port is None and remote_port is None:
            break
        
        if local_port is not None and remote_port is not None:
            try:
                ssh_tunnels.append((int(local_port), int(remote_port)))
            except ValueError:
                pass
        
        n += 1
    
    # Kill any remaining processes on configured ports
    for local_port, _ in ssh_tunnels:
        subprocess.run(["fuser", "-k", f"{local_port}/tcp"], capture_output=True)
    
    msg = "SSH tunnel cleanup completed."
    print(msg)
    logger.info(msg)


@contextmanager
def graceful_shutdown():
    """Context manager for graceful shutdown."""
    global shutdown_in_progress
    try:
        yield
    except KeyboardInterrupt:
        global interrupted
        interrupted = True
        shutdown_in_progress = True
        print("\n\n" + "=" * 60)
        print("INTERRUPTED: Shutting down gracefully...")
        print("=" * 60)
        raise


def run_pipeline_with_mock_data(
    mock_csv_path: Path,
    difficulty: str,
    batch_size: int,
    agent: str = None,
    max_workers: int = 4,
    verbose: bool = False,
    run_index: int = None
):
    """
    Run the CLAW-Agent pipeline using mock data as input.
    
    This function:
    1. Copies mock data to the CLAW-Agent expected location temporarily
    2. Runs the extraction pipeline
    3. Saves output to testing folder instead of default location
    4. Returns the extracted faults dataframe
    
    Args:
        mock_csv_path: Path to mock shift summaries CSV
        difficulty: Difficulty level (easy/medium/hard)
        batch_size: Batch size for extraction
        agent: Agent name to use
        max_workers: Number of parallel workers
        verbose: Enable verbose logging
        run_index: Run index for multiple runs (None = single run, no suffix)
    
    Returns:
        dict: Results including output file paths and metrics
    """
    # Setup logging
    if verbose:
        from utils.logging_utils import setup_logging, logger
        setup_logging(level="DEBUG")
    else:
        from utils.logging_utils import setup_logging, logger
        setup_logging()
    
    logger.info("=" * 60)
    logger.info(f"Mock Pipeline Run: {difficulty} (batch_size={batch_size})")
    logger.info("=" * 60)
    
    total_start = time.time()
    results = {
        "difficulty": difficulty,
        "batch_size": batch_size,
        "start_time": datetime.now().isoformat(),
        "steps": {}
    }
    
    # Step 1: Load mock data
    logger.info("\n[1/6] Loading mock shift summaries...")
    step_start = time.time()
    
    if not mock_csv_path.exists():
        logger.error(f"Mock CSV not found: {mock_csv_path}")
        return None
    
    shift_df = pd.read_csv(mock_csv_path)
    logger.info(f"Loaded {len(shift_df)} mock summaries from {mock_csv_path.name}")
    
    results["steps"]["load"] = {
        "duration": time.time() - step_start,
        "summaries_loaded": len(shift_df)
    }
    
    # Step 2: Temporarily copy mock data to CLAW-Agent expected location
    from config import SHIFT_SUMMARY_CSV, PROCESSED_SUMMARIES_CSV, FINAL_OUTPUT_DIR
    
    logger.info("\n[2/6] Preparing data for extraction...")
    step_start = time.time()
    
    # Backup original if exists
    original_backup = None
    if SHIFT_SUMMARY_CSV.exists():
        original_backup = Path(str(SHIFT_SUMMARY_CSV) + ".backup")
        shutil.copy(SHIFT_SUMMARY_CSV, original_backup)
        logger.info(f"Backed up original {SHIFT_SUMMARY_CSV}")
    
    # Copy mock data to expected location
    shutil.copy(mock_csv_path, SHIFT_SUMMARY_CSV)
    logger.info(f"Copied mock data to {SHIFT_SUMMARY_CSV}")
    
    results["steps"]["prepare"] = {
        "duration": time.time() - step_start
    }
    
    # Step 3: Extract faults
    logger.info(f"\n[3/6] Extracting faults (batch_size={batch_size})...")
    step_start = time.time()
    
    try:
        from analysis.shift_summary import main_function2 as extract_faults
        if interrupted:
            logger.info("Aborting extraction due to interrupt signal.")
            return None
        with graceful_shutdown():
            faults_df, start_time = extract_faults(
                agent=agent,
                max_workers=max_workers,
                batch_size=batch_size
            )
        
        if faults_df is not None and len(faults_df) > 0:
            logger.info(f"Extracted {len(faults_df)} faults")
            results["steps"]["extract"] = {
                "duration": time.time() - step_start,
                "faults_extracted": len(faults_df)
            }
        else:
            logger.warning("No faults extracted")
            results["steps"]["extract"] = {
                "duration": time.time() - step_start,
                "faults_extracted": 0
            }
            faults_df = None
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        results["steps"]["extract"] = {
            "duration": time.time() - step_start,
            "error": str(e)
        }
        faults_df = None
    
    # Step 4: Add tags
    if faults_df is not None and len(faults_df) > 0:
        logger.info("\n[4/6] Adding tags...")
        step_start = time.time()
        
        # Check if ChromaDB vector database exists, create if missing
        try:
            from analysis.tag_extraction import CHROMA_DB_PATH
            if not CHROMA_DB_PATH.exists():
                logger.info(f"ChromaDB database not found at {CHROMA_DB_PATH}")
                logger.info("Creating ChromaDB vector database...")
                CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
                logger.info(f"ChromaDB directory created at {CHROMA_DB_PATH}")
        except Exception as e:
            logger.warning(f"Failed to check/create ChromaDB database: {e}")
        
        try:
            from analysis.tag_extraction import main_tagger
            if interrupted:
                logger.info("Aborting tagging due to interrupt signal.")
                return faults_df
            with graceful_shutdown():
                faults_df = main_tagger(
                    faults_df,
                    start_time,
                    agent=agent,
                    max_workers=max_workers,
                    batch_size=batch_size
                )
            logger.info(f"Tagged {len(faults_df)} faults")
        except Exception as e:
            logger.error(f"Tagging failed: {e}")
            import traceback
            traceback.print_exc()
        
        results["steps"]["tag"] = {
            "duration": time.time() - step_start,
            "faults_tagged": len(faults_df) if faults_df is not None else 0
        }
        
        # Save to processed_summaries.csv so verification step can find it
        from config import PROCESSED_SUMMARIES_CSV
        PROCESSED_SUMMARIES_CSV.parent.mkdir(parents=True, exist_ok=True)
        faults_df.to_csv(PROCESSED_SUMMARIES_CSV, index=False)
        logger.info(f"Saved {len(faults_df)} tagged faults to {PROCESSED_SUMMARIES_CSV}")
        
        # Also save to test-specific output file
        # Include run_index in filename if multiple runs
        if run_index is not None:
            output_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}_run{run_index + 1}.csv"
        else:
            output_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}.csv"
        faults_df.to_csv(output_file, index=False)
        logger.info(f"Saved extracted faults to {output_file}")
        results["extracted_faults_file"] = str(output_file)
    
    # Step 5: Verify timestamps
    logger.info("\n[5/6] Verifying timestamps...")
    step_start = time.time()
    
    try:
        from analysis.accuracy_test import main_function3 as verify_faults
        if interrupted:
            logger.info("Aborting verification due to interrupt signal.")
            return
        with graceful_shutdown():
            accurate_df, inaccurate_df = verify_faults(
                agent=agent,
                max_workers=max_workers,
                batch_size=batch_size
            )
        
        accurate_count = len(accurate_df) if accurate_df is not None else 0
        inaccurate_count = len(inaccurate_df) if inaccurate_df is not None else 0
        logger.info(f"Verified: {accurate_count} accurate, {inaccurate_count} inaccurate")
        
        results["steps"]["verify"] = {
            "duration": time.time() - step_start,
            "accurate": accurate_count,
            "inaccurate": inaccurate_count
        }
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()
        results["steps"]["verify"] = {
            "duration": time.time() - step_start,
            "error": str(e)
        }
    
    # Step 6: Fix inaccurate timestamps (if any)
    inaccurate_count = results["steps"]["verify"].get("inaccurate", 0)
    
    if inaccurate_count > 0:
        logger.info("\n[6/6] Fixing inaccurate timestamps...")
        step_start = time.time()
        
        try:
            from analysis.fixer import main_function4 as fix_timestamps
            if interrupted:
                logger.info("Aborting timestamp fix due to interrupt signal.")
                return
            with graceful_shutdown():
                fixed_df, manual_df = fix_timestamps(
                    agent=agent,
                    max_workers=max_workers,
                    batch_size=batch_size
                )
            
            fixed_count = len(fixed_df) if fixed_df is not None else 0
            manual_count = len(manual_df) if manual_df is not None else 0
            logger.info(f"Fixed: {fixed_count} fixed, {manual_count} manual check")
            
            results["steps"]["fix"] = {
                "duration": time.time() - step_start,
                "fixed": fixed_count,
                "manual": manual_count
            }
        except Exception as e:
            logger.error(f"Fixing failed: {e}")
            import traceback
            traceback.print_exc()
            results["steps"]["fix"] = {
                "duration": time.time() - step_start,
                "error": str(e)
            }
    else:
        logger.info("\n[6/6] Skipping fix (no inaccurate timestamps)")
        results["steps"]["fix"] = {
            "duration": 0,
            "fixed": 0,
            "manual": 0
        }
    
    # Step 7: Final consolidation
    logger.info("\n[7/7] Consolidating final output...")
    step_start = time.time()
    
    try:
        from analysis.verifyer import main_function5 as final_verification
        if interrupted:
            logger.info("Aborting final verification due to interrupt signal.")
            return
        with graceful_shutdown():
            final_df = final_verification(agent=agent)
        final_count = len(final_df) if final_df is not None else 0
        logger.info(f"Final output: {final_count} faults")
        
        results["steps"]["consolidate"] = {
            "duration": time.time() - step_start,
            "final_faults": final_count
        }
        
        # Save final output to test folder (NOT to all_shift_faults.csv)
        # Include run_index in filename if multiple runs
        if final_df is not None and len(final_df) > 0:
            if run_index is not None:
                final_output_file = TEST_OUTPUT_DIR / f"final_faults_{difficulty}_batch{batch_size}_run{run_index + 1}.csv"
            else:
                final_output_file = TEST_OUTPUT_DIR / f"final_faults_{difficulty}_batch{batch_size}.csv"
            final_df.to_csv(final_output_file, index=False)
            results["final_output_file"] = str(final_output_file)
            logger.info(f"Saved final output to {final_output_file}")
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        import traceback
        traceback.print_exc()
        results["steps"]["consolidate"] = {
            "duration": time.time() - step_start,
            "error": str(e)
        }
    
    # Calculate total time
    results["total_duration"] = time.time() - total_start
    results["end_time"] = datetime.now().isoformat()
    
    # Restore original data if backup exists
    if original_backup and original_backup.exists():
        shutil.copy(original_backup, SHIFT_SUMMARY_CSV)
        original_backup.unlink()
        logger.info(f"Restored original {SHIFT_SUMMARY_CSV}")
    
    # Clean up processed files
    if PROCESSED_SUMMARIES_CSV.exists():
        PROCESSED_SUMMARIES_CSV.unlink()
    
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Pipeline Complete: {results['total_duration']:.2f}s")
    logger.info(f"{'=' * 60}")
    
    return results


def run_accuracy_evaluation(
    difficulty: str,
    batch_size: int,
    extracted_faults_path: Path,
    ground_truth_csv: Path,
    ground_truth_faults: Path,
    verbose: bool = False
):
    """
    Run accuracy evaluation on extracted faults.
    
    Args:
        difficulty: Difficulty level
        batch_size: Batch size used
        extracted_faults_path: Path to extracted faults CSV
        ground_truth_csv: Path to ground truth summaries
        ground_truth_faults: Path to ground truth faults
        verbose: Enable verbose logging
    
    Returns:
        dict: Accuracy metrics
    """
    from utils.logging_utils import logger
    
    logger.info(f"\nRunning accuracy evaluation for {difficulty} (batch_size={batch_size})...")
    
    if not extracted_faults_path.exists():
        logger.error(f"Extracted faults not found: {extracted_faults_path}")
        return None
    
    # Run evaluation using the accuracy tester
    try:
        # Run fault_accuracy_evaluator.py as a subprocess
        output_base = str(TEST_OUTPUT_DIR / f"accuracy_report_{difficulty}_batch{batch_size}")
        output_json = output_base + '.json'
        
        result = subprocess.run(
            ["python3", str(ACCURACY_TESTER_DIR / "fault_accuracy_evaluator.py"),
             "--ground-truth", str(ground_truth_csv),
             "--faults", str(ground_truth_faults),
             "--extracted", str(extracted_faults_path),
             "--output", output_base],
            cwd=ACCURACY_TESTER_DIR,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Read the results from the JSON file (script adds .json extension)
            if os.path.exists(output_json):
                with open(output_json, 'r') as f:
                    results = json.load(f)
                
                scores = results.get('summary', results.get('scores', {}))
                logger.info(f"Accuracy: Precision={scores.get('precision', 0):.2%}, "
                           f"Recall={scores.get('recall', 0):.2%}, F1={scores.get('f1', scores.get('f1_score', 0)):.2%}")
                
                return scores
            else:
                logger.error(f"JSON output file not created: {output_json}")
                return None
        else:
            logger.error(f"Accuracy evaluation failed: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Accuracy evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_benchmarks(verbose: bool = False):
    """
    Run benchmark scripts to generate graphs.
    
    Args:
        verbose: Enable verbose logging
    """
    from utils.logging_utils import logger
    
    logger.info("\n" + "=" * 60)
    logger.info("Running Benchmarks")
    logger.info("=" * 60)
    
    try:
        # Run batching accuracy
        logger.info("\nGenerating batching accuracy graphs...")
        result = subprocess.run(
            ["python3", str(BENCHMARKS_DIR / "batching_accuracy.py")],
            cwd=BENCHMARKS_DIR,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.warning(f"batching_accuracy.py had issues: {result.stderr[:200]}")
        
        # Run batching time
        logger.info("Generating batching time graphs...")
        result = subprocess.run(
            ["python3", str(BENCHMARKS_DIR / "batching_time.py")],
            cwd=BENCHMARKS_DIR,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.warning(f"batching_time.py had issues: {result.stderr[:200]}")
        
        # Run parallel time
        logger.info("Generating parallel time graphs...")
        result = subprocess.run(
            ["python3", str(BENCHMARKS_DIR / "parallel_time.py")],
            cwd=BENCHMARKS_DIR,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.warning(f"parallel_time.py had issues: {result.stderr[:200]}")
        
        logger.info("\nBenchmark graphs saved to: " + str(BENCHMARKS_DIR / "graphs"))
        
    except Exception as e:
        logger.error(f"Benchmarks failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Run CLAW-Agent pipeline with mock data")
    parser.add_argument(
        "--levels",
        nargs="+",
        default=["easy", "medium", "hard"],
        choices=["easy", "medium", "hard"],
        help="Difficulty levels to test"
    )
    parser.add_argument(
        "--batch-sizes",
        nargs="+",
        type=int,
        default=[1, 2, 4],
        help="Batch sizes to test"
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Agent name to use (defaults to config)"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel workers"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--skip-accuracy",
        action="store_true",
        help="Skip accuracy evaluation"
    )
    parser.add_argument(
        "--skip-benchmarks",
        action="store_true",
        help="Skip benchmark graph generation"
    )
    parser.add_argument(
        "--generate-mock-data",
        action="store_true",
        help="Generate mock data before running pipeline (if not already present)"
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Force regeneration of mock data (deletes existing mock summaries and faults before regenerating)"
    )
    parser.add_argument(
        "--parallel-workers",
        nargs="+",
        type=int,
        default=None,
        help="Worker counts to test for parallel performance (with fixed batch_size=5)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Single batch size to use (default: 1, used with --parallel-workers)"
    )
    parser.add_argument(
        "--all-tests",
        action="store_true",
        help="Run comprehensive test suite: batch sizes 1-20 for all difficulties, then parallel workers for medium"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per configuration (default: 1). Multiple runs enable mean/std statistics."
    )
    parser.add_argument(
        "--no-tunnel",
        action="store_true",
        help="Skip SSH tunnel creation (use if running locally or with mock data only)"
    )
    
    args = parser.parse_args()
    
    from utils.logging_utils import logger
    
    # Generate mock data if requested or if missing
    from utils.logging_utils import logger
    
    # Check if mock data exists, generate if missing
    mock_data_missing = False
    for level in args.levels:
        mock_csv = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}.csv"
        mock_faults = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}_faults.csv"
        if not mock_csv.exists() or not mock_faults.exists():
            mock_data_missing = True
            break
    
    # Force regeneration if requested
    if args.force_regenerate:
        logger.info("Force regeneration mode: Deleting existing mock data...")
        for level in args.levels:
            mock_csv = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}.csv"
            mock_faults = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}_faults.csv"
            if mock_csv.exists():
                mock_csv.unlink()
                logger.info(f"  Deleted {mock_csv.name}")
            if mock_faults.exists():
                mock_faults.unlink()
                logger.info(f"  Deleted {mock_faults.name}")
        mock_data_missing = True
    
    if args.generate_mock_data or mock_data_missing:
        logger.info("Checking/generating mock data...")
        try:
            # Run generate_summaries.py as a subprocess
            result = subprocess.run(
                ["python3", str(MOCK_SUMMARIES_DIR / "generate_summaries.py")],
                cwd=MOCK_SUMMARIES_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info("Mock summaries generated.")
                
                # Now generate ground truth faults for each level
                logger.info("Generating ground truth faults...")
                for level in args.levels:
                    mock_csv = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}.csv"
                    mock_faults = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}_faults.csv"
                    
                    if mock_csv.exists() and not mock_faults.exists():
                        result = subprocess.run(
                            ["python3", str(ACCURACY_TESTER_DIR / "generate_ground_truth.py"),
                             "--input", str(mock_csv),
                             "--type", level,
                             "--output", str(mock_faults)],
                            cwd=ACCURACY_TESTER_DIR,
                            capture_output=True,
                            text=True
                        )
                        if result.returncode == 0:
                            logger.info(f"  Ground truth generated for {level}")
                        else:
                            logger.error(f"  Failed to generate ground truth for {level}: {result.stderr}")
            else:
                logger.error(f"Failed to generate mock data: {result.stderr}")
        except Exception as e:
            logger.error(f"Failed to generate mock data: {e}")
    
    # Setup SSH tunnel if not disabled
    tunnel = None
    if not args.no_tunnel:
        tunnel = setup_ssh_tunnel(verbose=args.verbose)
        if tunnel is None:
            logger.warning("SSH tunnel setup failed. Pipeline may fail if it requires network access.")
    else:
        logger.info("SSH tunnel disabled (--no-tunnel flag set).")
    
    logger.info("=" * 60)
    logger.info("CLAW-Agent Mock Data Testing Suite")
    logger.info("=" * 60)
    
    # Check if running parallel workers test
    if args.parallel_workers:
        logger.info("Mode: Parallel Workers Testing")
        logger.info(f"Worker counts: {args.parallel_workers}")
        logger.info(f"Fixed batch size: {args.batch_size}")
        logger.info(f"Levels: {args.levels}")
        logger.info(f"Max workers (per job): {args.max_workers}")
    elif args.all_tests:
        logger.info("Mode: Comprehensive All-Tests Suite")
        logger.info("Phase 1: Batch sizes 1-20 for all difficulty levels")
        logger.info("Phase 2: Parallel workers for medium difficulty")
        logger.info("Will generate all benchmark graphs automatically")
    else:
        logger.info("Mode: Batch Size Testing")
        logger.info(f"Levels: {args.levels}")
        logger.info(f"Batch sizes: {args.batch_sizes}")
        logger.info(f"Max workers: {args.max_workers}")
    
    logger.info(f"Agent: {args.agent or 'default'}")
    logger.info("=" * 60)
    
    # Collect all results
    all_results = []
    accuracy_results = []
    
    # Determine test mode: all-tests, parallel workers, or batch sizes
    if args.all_tests:
        # Comprehensive mode: use provided batch sizes and parallel workers, or defaults
        if args.batch_sizes and len(args.batch_sizes) > 0:
            batch_sizes_to_test = args.batch_sizes
        else:
            batch_sizes_to_test = list(range(1, 21))  # Default: 1 to 20
        
        if args.parallel_workers and len(args.parallel_workers) > 0:
            parallel_workers_to_test = args.parallel_workers
        else:
            parallel_workers_to_test = list(range(1, 11))  # Default: 1 to 10
        
        logger.info("\n" + "=" * 60)
        logger.info(f"PHASE 1: Batch Size Testing ({min(batch_sizes_to_test)}-{max(batch_sizes_to_test)}) for All Difficulty Levels")
        logger.info("=" * 60)
        
        # Phase 1: Batch size testing for all difficulty levels
        for difficulty in args.levels:
            if interrupted:
                logger.info("Interrupted - exiting Phase 1 batch testing")
                break
            for batch_size in batch_sizes_to_test:
                if interrupted:
                    logger.info("Interrupted - exiting batch testing")
                    break
                logger.info(f"\n\n{'=' * 60}")
                logger.info(f"Testing: {difficulty} (batch_size={batch_size}, runs={args.runs})")
                logger.info(f"{'=' * 60}\n")
                
                mock_csv = MOCK_SUMMARIES_DIR / f"mock_summaries_{difficulty}.csv"
                mock_faults = MOCK_SUMMARIES_DIR / f"mock_summaries_{difficulty}_faults.csv"
                
                if not mock_csv.exists():
                    logger.error(f"Mock data not found for {difficulty}. Skipping.")
                    continue
                
                # Run multiple times and aggregate
                run_pipeline_results = []
                run_accuracy_results = []
                
                for run_idx in range(args.runs):
                    if interrupted:
                        logger.info("Interrupted - exiting run loop")
                        break
                    if args.runs > 1:
                        logger.info(f"  Run {run_idx + 1}/{args.runs}")
                    
                    pipeline_results = run_pipeline_with_mock_data(
                        mock_csv_path=mock_csv,
                        difficulty=difficulty,
                        batch_size=batch_size,
                        agent=args.agent,
                        max_workers=args.max_workers,
                        verbose=args.verbose,
                        run_index=run_idx
                    )
                    
                    if pipeline_results:
                        # Tag with run index for tracking
                        pipeline_results["run_index"] = run_idx
                        run_pipeline_results.append(pipeline_results)
                        all_results.append(pipeline_results)
                        
                        if not args.skip_accuracy:
                            # Use run-specific file path if multiple runs
                            if run_idx is not None:
                                extracted_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}_run{run_idx + 1}.csv"
                            else:
                                extracted_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}.csv"
                            
                            if extracted_file.exists():
                                accuracy = run_accuracy_evaluation(
                                    difficulty=difficulty,
                                    batch_size=batch_size,
                                    extracted_faults_path=extracted_file,
                                    ground_truth_csv=mock_csv,
                                    ground_truth_faults=mock_faults,
                                    verbose=args.verbose
                                )
                                
                                if accuracy:
                                    accuracy["run_index"] = run_idx
                                    run_accuracy_results.append(accuracy)
                                    
                                    # Get timing data from pipeline results for this run
                                    pipeline_timing = run_pipeline_results[run_idx] if run_idx < len(run_pipeline_results) else {}
                                    
                                    # Build accuracy result entry with timing data
                                    accuracy_entry = {
                                        "difficulty": difficulty,
                                        "batch_size": batch_size,
                                        **accuracy
                                    }
                                    
                                    # Add timing data from pipeline
                                    if pipeline_timing:
                                        steps_data = pipeline_timing.get("steps", {})
                                        for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate"]:
                                            step_data = steps_data.get(step, {})
                                            if isinstance(step_data, dict) and "duration" in step_data:
                                                accuracy_entry[f"{step}"] = step_data["duration"]
                                        
                                        # Add total duration
                                        if "total_duration" in pipeline_timing:
                                            accuracy_entry["total"] = pipeline_timing["total_duration"]
                                    
                                    accuracy_results.append(accuracy_entry)
                
                # Aggregate statistics if multiple runs
                if args.runs > 1 and run_pipeline_results:
                    import statistics
                    
                    # Aggregate timing data
                    total_durations = [r.get("total_duration", 0) for r in run_pipeline_results]
                    if len(total_durations) > 1:
                        mean_duration = statistics.mean(total_durations)
                        stdev_duration = statistics.stdev(total_durations) if len(total_durations) > 1 else 0
                        
                        # Add aggregated entry
                        agg_entry = {
                            "difficulty": difficulty,
                            "batch_size": batch_size,
                            "runs": args.runs,
                            "total_duration_mean": mean_duration,
                            "total_duration_stdev": stdev_duration,
                            "is_aggregated": True
                        }
                        
                        # Aggregate step durations
                        for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate"]:
                            step_durations = []
                            for r in run_pipeline_results:
                                step_data = r.get("steps", {}).get(step, {})
                                if isinstance(step_data, dict) and "duration" in step_data:
                                    step_durations.append(step_data["duration"])
                            
                            if len(step_durations) > 0:
                                agg_entry[f"{step}_duration_mean"] = statistics.mean(step_durations)
                                if len(step_durations) > 1:
                                    agg_entry[f"{step}_duration_stdev"] = statistics.stdev(step_durations)
                        
                        all_results.append(agg_entry)
                
                # Aggregate accuracy stats if multiple runs
                if args.runs > 1 and run_accuracy_results:
                    import statistics
                    
                    # Aggregate ALL metrics into ONE entry (not separate entries per metric)
                    precision_values = [r.get('precision', r.get('precision_mean', 0)) for r in run_accuracy_results if r.get('precision', r.get('precision_mean')) is not None]
                    recall_values = [r.get('recall', r.get('recall_mean', 0)) for r in run_accuracy_results if r.get('recall', r.get('recall_mean')) is not None]
                    f1_values = [r.get('f1', r.get('f1_score', r.get('f1_mean', 0))) for r in run_accuracy_results if r.get('f1', r.get('f1_score', r.get('f1_mean'))) is not None]
                    
                    # Create single aggregated entry
                    agg_acc_entry = {
                        "difficulty": difficulty,
                        "batch_size": batch_size,
                        "runs": args.runs,
                        "is_aggregated": True
                    }
                    
                    if len(precision_values) > 0:
                        agg_acc_entry["precision_mean"] = statistics.mean(precision_values)
                        agg_acc_entry["precision_stdev"] = statistics.stdev(precision_values) if len(precision_values) > 1 else 0
                    
                    if len(recall_values) > 0:
                        agg_acc_entry["recall_mean"] = statistics.mean(recall_values)
                        agg_acc_entry["recall_stdev"] = statistics.stdev(recall_values) if len(recall_values) > 1 else 0
                    
                    if len(f1_values) > 0:
                        agg_acc_entry["f1_mean"] = statistics.mean(f1_values)
                        agg_acc_entry["f1_stdev"] = statistics.stdev(f1_values) if len(f1_values) > 1 else 0
                    
                    # Add aggregated timing data
                    for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate", "total"]:
                        step_key = step if step != "total" else "total_duration"
                        step_values = [r.get(step, r.get(step_key)) for r in run_accuracy_results if r.get(step, r.get(step_key)) is not None]
                        
                        if len(step_values) > 0:
                            agg_acc_entry[f"{step}_mean"] = statistics.mean(step_values)
                            if len(step_values) > 1:
                                agg_acc_entry[f"{step}_stdev"] = statistics.stdev(step_values)
                    
                    accuracy_results.append(agg_acc_entry)
        
        logger.info("\n" + "=" * 60)
        logger.info(f"PHASE 2: Parallel Workers Testing ({min(parallel_workers_to_test)}-{max(parallel_workers_to_test)}) for Medium Difficulty, Batch Size 5")
        logger.info("=" * 60)
        
        # Phase 2: Parallel workers testing for medium difficulty
        difficulty = "medium"
        batch_size = 5  # Fixed batch size for parallel testing
        
        mock_csv = MOCK_SUMMARIES_DIR / f"mock_summaries_{difficulty}.csv"
        mock_faults = MOCK_SUMMARIES_DIR / f"mock_summaries_{difficulty}_faults.csv"
        
        if mock_csv.exists():
            for worker_count in parallel_workers_to_test:
                if interrupted:
                    logger.info("Interrupted - exiting Phase 2 parallel workers testing")
                    break
                logger.info(f"\n\n{'=' * 60}")
                logger.info(f"Testing: {difficulty} (batch_size={batch_size}, workers={worker_count}, runs={args.runs})")
                logger.info(f"{'=' * 60}\n")
                
                # Run multiple times and aggregate
                run_pipeline_results = []
                run_accuracy_results = []
                
                for run_idx in range(args.runs):
                    if interrupted:
                        logger.info("Interrupted - exiting run loop")
                        break
                    if args.runs > 1:
                        logger.info(f"  Run {run_idx + 1}/{args.runs}")
                    
                    pipeline_results = run_pipeline_with_mock_data(
                        mock_csv_path=mock_csv,
                        difficulty=difficulty,
                        batch_size=batch_size,
                        agent=args.agent,
                        max_workers=worker_count,
                        verbose=args.verbose,
                        run_index=run_idx
                    )
                    
                    if pipeline_results:
                        pipeline_results["max_workers"] = worker_count
                        pipeline_results["test_label"] = f"parallel_workers_{worker_count}"
                        pipeline_results["test_phase"] = "parallel_workers"
                        pipeline_results["run_index"] = run_idx
                        run_pipeline_results.append(pipeline_results)
                        all_results.append(pipeline_results)
                        
                        if not args.skip_accuracy:
                            # Use run-specific file path if multiple runs
                            if run_idx is not None:
                                extracted_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}_run{run_idx + 1}.csv"
                            else:
                                extracted_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}.csv"
                            
                            if extracted_file.exists():
                                accuracy = run_accuracy_evaluation(
                                    difficulty=difficulty,
                                    batch_size=batch_size,
                                    extracted_faults_path=extracted_file,
                                    ground_truth_csv=mock_csv,
                                    ground_truth_faults=mock_faults,
                                    verbose=args.verbose
                                )
                                
                                if accuracy:
                                    accuracy["max_workers"] = worker_count
                                    accuracy["test_label"] = f"parallel_workers_{worker_count}"
                                    accuracy["test_phase"] = "parallel_workers"
                                    accuracy["run_index"] = run_idx
                                    run_accuracy_results.append(accuracy)
                                    
                                    # Get timing data from pipeline results for this run
                                    pipeline_timing = run_pipeline_results[run_idx] if run_idx < len(run_pipeline_results) else {}
                                    
                                    # Build accuracy result entry with timing data
                                    accuracy_entry = {
                                        "difficulty": difficulty,
                                        "batch_size": batch_size,
                                        "max_workers": worker_count,
                                        "test_label": f"parallel_workers_{worker_count}",
                                        "test_phase": "parallel_workers",
                                        **accuracy
                                    }
                                    
                                    # Add timing data from pipeline
                                    if pipeline_timing:
                                        steps_data = pipeline_timing.get("steps", {})
                                        for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate"]:
                                            step_data = steps_data.get(step, {})
                                            if isinstance(step_data, dict) and "duration" in step_data:
                                                accuracy_entry[f"{step}"] = step_data["duration"]
                                        
                                        # Add total duration
                                        if "total_duration" in pipeline_timing:
                                            accuracy_entry["total"] = pipeline_timing["total_duration"]
                                    
                                    accuracy_results.append(accuracy_entry)
                
                # Aggregate statistics if multiple runs
                if args.runs > 1 and run_pipeline_results:
                    import statistics
                    
                    # Aggregate timing data
                    total_durations = [r.get("total_duration", 0) for r in run_pipeline_results]
                    if len(total_durations) > 1:
                        mean_duration = statistics.mean(total_durations)
                        stdev_duration = statistics.stdev(total_durations) if len(total_durations) > 1 else 0
                        
                        # Add aggregated entry
                        agg_entry = {
                            "difficulty": difficulty,
                            "batch_size": batch_size,
                            "max_workers": worker_count,
                            "runs": args.runs,
                            "total_duration_mean": mean_duration,
                            "total_duration_stdev": stdev_duration,
                            "test_label": f"parallel_workers_{worker_count}",
                            "test_phase": "parallel_workers",
                            "is_aggregated": True
                        }
                        
                        # Aggregate step durations
                        for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate"]:
                            step_durations = []
                            for r in run_pipeline_results:
                                step_data = r.get("steps", {}).get(step, {})
                                if isinstance(step_data, dict) and "duration" in step_data:
                                    step_durations.append(step_data["duration"])
                            
                            if len(step_durations) > 0:
                                agg_entry[f"{step}_duration_mean"] = statistics.mean(step_durations)
                                if len(step_durations) > 1:
                                    agg_entry[f"{step}_duration_stdev"] = statistics.stdev(step_durations)
                        
                        all_results.append(agg_entry)
                
                # Aggregate accuracy stats if multiple runs
                if args.runs > 1 and run_accuracy_results:
                    import statistics
                    
                    # Aggregate ALL metrics into ONE entry (not separate entries per metric)
                    precision_values = [r.get('precision', r.get('precision_mean', 0)) for r in run_accuracy_results if r.get('precision', r.get('precision_mean')) is not None]
                    recall_values = [r.get('recall', r.get('recall_mean', 0)) for r in run_accuracy_results if r.get('recall', r.get('recall_mean')) is not None]
                    f1_values = [r.get('f1', r.get('f1_score', r.get('f1_mean', 0))) for r in run_accuracy_results if r.get('f1', r.get('f1_score', r.get('f1_mean'))) is not None]
                    
                    # Create single aggregated entry
                    agg_acc_entry = {
                        "difficulty": difficulty,
                        "batch_size": batch_size,
                        "max_workers": worker_count,
                        "test_label": f"parallel_workers_{worker_count}",
                        "test_phase": "parallel_workers",
                        "runs": args.runs,
                        "is_aggregated": True
                    }
                    
                    if len(precision_values) > 0:
                        agg_acc_entry["precision_mean"] = statistics.mean(precision_values)
                        agg_acc_entry["precision_stdev"] = statistics.stdev(precision_values) if len(precision_values) > 1 else 0
                    
                    if len(recall_values) > 0:
                        agg_acc_entry["recall_mean"] = statistics.mean(recall_values)
                        agg_acc_entry["recall_stdev"] = statistics.stdev(recall_values) if len(recall_values) > 1 else 0
                    
                    if len(f1_values) > 0:
                        agg_acc_entry["f1_mean"] = statistics.mean(f1_values)
                        agg_acc_entry["f1_stdev"] = statistics.stdev(f1_values) if len(f1_values) > 1 else 0
                    
                    # Add aggregated timing data
                    for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate", "total"]:
                        step_key = step if step != "total" else "total_duration"
                        step_values = [r.get(step, r.get(step_key)) for r in run_accuracy_results if r.get(step, r.get(step_key)) is not None]
                        
                        if len(step_values) > 0:
                            agg_acc_entry[f"{step}_mean"] = statistics.mean(step_values)
                            if len(step_values) > 1:
                                agg_acc_entry[f"{step}_stdev"] = statistics.stdev(step_values)
                    
                    accuracy_results.append(agg_acc_entry)
        else:
            logger.warning(f"Medium difficulty mock data not found. Skipping parallel workers phase.")
    
    # Check for interrupt after Phase 1 - exit early if interrupted
    if interrupted:
        logger.info("Interrupted - exiting all tests early")
        return
    
    elif args.parallel_workers:
        # Parallel workers testing mode: fixed batch size, varying worker counts
        test_configs = []
        for difficulty in args.levels:
            for worker_count in args.parallel_workers:
                test_configs.append({
                    "difficulty": difficulty,
                    "batch_size": args.batch_size,
                    "max_workers": worker_count,
                    "label": f"workers_{worker_count}",
                    "is_parallel": True
                })
    else:
        # Standard batch size testing mode
        test_configs = []
        for difficulty in args.levels:
            for batch_size in args.batch_sizes:
                test_configs.append({
                    "difficulty": difficulty,
                    "batch_size": batch_size,
                    "max_workers": args.max_workers,
                    "label": f"batch_{batch_size}",
                    "is_parallel": False
                })
    
    # Only run the main test loop if NOT in all-tests mode (which runs inline)
    if not args.all_tests:
        for config in test_configs:
            if interrupted:
                logger.info("Interrupted - exiting test loop")
                break
            difficulty = config["difficulty"]
            batch_size = config["batch_size"]
            worker_count = config["max_workers"]
            label = config["label"]
            is_parallel = config.get("is_parallel", False)
            
            logger.info(f"\n\n{'=' * 60}")
            if is_parallel:
                logger.info(f"Testing: {difficulty} (batch_size={batch_size}, workers={worker_count}, runs={args.runs})")
            else:
                logger.info(f"Testing: {difficulty} (batch_size={batch_size}, runs={args.runs})")
            logger.info(f"{'=' * 60}\n")
            
            # Paths for mock data
            mock_csv = MOCK_SUMMARIES_DIR / f"mock_summaries_{difficulty}.csv"
            mock_faults = MOCK_SUMMARIES_DIR / f"mock_summaries_{difficulty}_faults.csv"
            
            if not mock_csv.exists():
                logger.error(f"Mock data not found for {difficulty}. Skipping.")
                logger.info("Run with --generate-mock-data to create mock data first.")
                continue
            
            # Run multiple times and aggregate
            run_pipeline_results = []
            run_accuracy_results = []
            
            for run_idx in range(args.runs):
                if interrupted:
                    logger.info("Interrupted - exiting run loop")
                    break
                if args.runs > 1:
                    logger.info(f"  Run {run_idx + 1}/{args.runs}")
                
                # Run pipeline
                pipeline_results = run_pipeline_with_mock_data(
                    mock_csv_path=mock_csv,
                    difficulty=difficulty,
                    batch_size=batch_size,
                    agent=args.agent,
                    max_workers=worker_count,
                    verbose=args.verbose,
                    run_index=run_idx
                )
                
                if pipeline_results:
                    # Add worker count info for parallel testing
                    if is_parallel:
                        pipeline_results["max_workers"] = worker_count
                        pipeline_results["test_label"] = label
                        pipeline_results["test_phase"] = "parallel_workers"
                    
                    pipeline_results["run_index"] = run_idx
                    run_pipeline_results.append(pipeline_results)
                    all_results.append(pipeline_results)
                    
                    # Run accuracy evaluation
                    if not args.skip_accuracy:
                        # Use run-specific file path if multiple runs
                        if run_idx is not None:
                            extracted_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}_run{run_idx + 1}.csv"
                        else:
                            extracted_file = TEST_OUTPUT_DIR / f"extracted_faults_{difficulty}_batch{batch_size}.csv"
                        
                        if extracted_file.exists():
                            accuracy = run_accuracy_evaluation(
                                difficulty=difficulty,
                                batch_size=batch_size,
                                extracted_faults_path=extracted_file,
                                ground_truth_csv=mock_csv,
                                ground_truth_faults=mock_faults,
                                verbose=args.verbose
                            )
                            
                            if accuracy:
                                accuracy["run_index"] = run_idx
                                run_accuracy_results.append(accuracy)
                                
                                # Get timing data from pipeline results for this run
                                pipeline_timing = run_pipeline_results[run_idx] if run_idx < len(run_pipeline_results) else {}
                                
                                # Build accuracy result entry with timing data
                                accuracy_entry = {
                                    "difficulty": difficulty,
                                    "batch_size": batch_size,
                                    **accuracy
                                }
                                if is_parallel:
                                    accuracy_entry["max_workers"] = worker_count
                                    accuracy_entry["test_label"] = label
                                    accuracy_entry["test_phase"] = "parallel_workers"
                                
                                # Add timing data from pipeline
                                if pipeline_timing:
                                    steps_data = pipeline_timing.get("steps", {})
                                    for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate"]:
                                        step_data = steps_data.get(step, {})
                                        if isinstance(step_data, dict) and "duration" in step_data:
                                            accuracy_entry[f"{step}"] = step_data["duration"]
                                    
                                    # Add total duration
                                    if "total_duration" in pipeline_timing:
                                        accuracy_entry["total"] = pipeline_timing["total_duration"]
                                
                                accuracy_results.append(accuracy_entry)
            
            # Aggregate statistics if multiple runs
            if args.runs > 1 and run_pipeline_results:
                import statistics
                
                # Aggregate timing data
                total_durations = [r.get("total_duration", 0) for r in run_pipeline_results]
                if len(total_durations) > 1:
                    mean_duration = statistics.mean(total_durations)
                    stdev_duration = statistics.stdev(total_durations) if len(total_durations) > 1 else 0
                    
                    # Add aggregated entry
                    agg_entry = {
                        "difficulty": difficulty,
                        "batch_size": batch_size,
                        "runs": args.runs,
                        "total_duration_mean": mean_duration,
                        "total_duration_stdev": stdev_duration,
                        "is_aggregated": True
                    }
                    
                    if is_parallel:
                        agg_entry["max_workers"] = worker_count
                        agg_entry["test_label"] = label
                        agg_entry["test_phase"] = "parallel_workers"
                    
                    # Aggregate step durations
                    for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate"]:
                        step_durations = []
                        for r in run_pipeline_results:
                            step_data = r.get("steps", {}).get(step, {})
                            if isinstance(step_data, dict) and "duration" in step_data:
                                step_durations.append(step_data["duration"])
                        
                        if len(step_durations) > 0:
                            agg_entry[f"{step}_duration_mean"] = statistics.mean(step_durations)
                            if len(step_durations) > 1:
                                agg_entry[f"{step}_duration_stdev"] = statistics.stdev(step_durations)
                    
                    all_results.append(agg_entry)
        
        # Aggregate accuracy stats if multiple runs
        if args.runs > 1 and run_accuracy_results:
            import statistics
            
            # Aggregate ALL metrics into ONE entry (not separate entries per metric)
            precision_values = [r.get('precision', r.get('precision_mean', 0)) for r in run_accuracy_results if r.get('precision', r.get('precision_mean')) is not None]
            recall_values = [r.get('recall', r.get('recall_mean', 0)) for r in run_accuracy_results if r.get('recall', r.get('recall_mean')) is not None]
            f1_values = [r.get('f1', r.get('f1_score', r.get('f1_mean', 0))) for r in run_accuracy_results if r.get('f1', r.get('f1_score', r.get('f1_mean'))) is not None]
            
            # Create single aggregated entry
            agg_acc_entry = {
                "difficulty": difficulty,
                "batch_size": batch_size,
                "runs": args.runs,
                "is_aggregated": True
            }
            
            if len(precision_values) > 0:
                agg_acc_entry["precision_mean"] = statistics.mean(precision_values)
                agg_acc_entry["precision_stdev"] = statistics.stdev(precision_values) if len(precision_values) > 1 else 0
            
            if len(recall_values) > 0:
                agg_acc_entry["recall_mean"] = statistics.mean(recall_values)
                agg_acc_entry["recall_stdev"] = statistics.stdev(recall_values) if len(recall_values) > 1 else 0
            
            if len(f1_values) > 0:
                agg_acc_entry["f1_mean"] = statistics.mean(f1_values)
                agg_acc_entry["f1_stdev"] = statistics.stdev(f1_values) if len(f1_values) > 1 else 0
            
            if is_parallel:
                agg_acc_entry["max_workers"] = worker_count
                agg_acc_entry["test_label"] = label
                agg_acc_entry["test_phase"] = "parallel_workers"
            
            # Add aggregated timing data
            for step in ["load", "prepare", "extract", "tag", "verify", "fix", "consolidate", "total"]:
                step_key = step if step != "total" else "total_duration"
                step_values = [r.get(step, r.get(step_key)) for r in run_accuracy_results if r.get(step, r.get(step_key)) is not None]
                
                if len(step_values) > 0:
                    agg_acc_entry[f"{step}_mean"] = statistics.mean(step_values)
                    if len(step_values) > 1:
                        agg_acc_entry[f"{step}_stdev"] = statistics.stdev(step_values)

            accuracy_results.append(agg_acc_entry)

            # Check for interrupt after each config in parallel_workers and standard batch modes
            if interrupted:
                logger.info("Interrupted - exiting test loop")
                return

    # Run benchmarks based on test mode
    if not args.skip_benchmarks and accuracy_results:
        logger.info("\nPreparing benchmark data...")
        
        # Save accuracy results for benchmark scripts
        benchmark_data_file = BENCHMARKS_DIR / "accuracy_data.json"
        with open(benchmark_data_file, 'w') as f:
            json.dump(accuracy_results, f, indent=2)
        
        if args.all_tests:
            # Comprehensive mode: generate all graphs
            logger.info("Generating batch size benchmark graphs...")
            result = subprocess.run(
                ["python3", str(BENCHMARKS_DIR / "batching_accuracy.py")],
                cwd=BENCHMARKS_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"batching_accuracy.py had issues: {result.stderr[:200]}")
            
            logger.info("Generating batching time graphs...")
            result = subprocess.run(
                ["python3", str(BENCHMARKS_DIR / "batching_time.py")],
                cwd=BENCHMARKS_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"batching_time.py had issues: {result.stderr[:200]}")
            
            logger.info("Generating parallel workers (batch=5) benchmark graphs...")
            result = subprocess.run(
                ["python3", str(BENCHMARKS_DIR / "parallel_workers_batch5.py")],
                cwd=BENCHMARKS_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"parallel_workers_batch5.py had issues: {result.stderr[:200]}")
            else:
                logger.info("All benchmark graphs generated successfully.")
        
        elif args.parallel_workers:
            # Parallel workers mode only
            logger.info("Generating parallel workers benchmark graphs...")
            result = subprocess.run(
                ["python3", str(BENCHMARKS_DIR / "parallel_workers_batch5.py")],
                cwd=BENCHMARKS_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"parallel_workers_batch5.py had issues: {result.stderr[:200]}")
            else:
                logger.info("Parallel workers benchmark graphs generated.")
            
            # Also run standard parallel_time.py for comparison
            logger.info("Generating standard parallel time graphs for comparison...")
            result = subprocess.run(
                ["python3", str(BENCHMARKS_DIR / "parallel_time.py")],
                cwd=BENCHMARKS_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"parallel_time.py had issues: {result.stderr[:200]}")
        
        else:
            # Standard batch size mode
            run_benchmarks(verbose=args.verbose)
    
    # Save summary
    summary_file = TEST_OUTPUT_DIR / "test_summary.json"
    config_data = {
        "levels": args.levels,
        "agent": args.agent,
    }
    if args.all_tests:
        config_data["mode"] = "comprehensive_all_tests"
        config_data["batch_sizes_range"] = "1-20"
        config_data["parallel_workers"] = [1, 2, 4, 6, 8]
        config_data["parallel_batch_size"] = 5
    elif args.parallel_workers:
        config_data["mode"] = "parallel_workers"
        config_data["worker_counts"] = args.parallel_workers
        config_data["batch_size"] = args.batch_size
    else:
        config_data["mode"] = "batch_sizes"
        config_data["batch_sizes"] = args.batch_sizes
        config_data["max_workers"] = args.max_workers
    
    with open(summary_file, 'w') as f:
        json.dump({
            "pipeline_results": all_results,
            "accuracy_results": accuracy_results,
            "config": config_data
        }, f, indent=2)
    
    logger.info(f"\n{'=' * 60}")
    logger.info("All tests complete!")
    logger.info(f"Summary saved to: {summary_file}")
    logger.info(f"{'=' * 60}")
    
    # Print summary table
    if accuracy_results:
        logger.info("\nAccuracy Summary:")
        logger.info("-" * 60)
        logger.info(f"{'Difficulty':<10} {'Batch':<8} {'Precision':<12} {'Recall':<12} {'F1':<12}")
        logger.info("-" * 60)
        
        for r in accuracy_results:
            # Handle both individual run results and aggregated results
            if r.get('is_aggregated'):
                # Aggregated result: use _mean fields
                precision = r.get('precision_mean', 0)
                recall = r.get('recall_mean', 0)
                f1_val = r.get('f1_mean', r.get('f1_score_mean', 0))
                batch_label = f"{r['batch_size']}(n={r.get('runs', 1)})"
            else:
                # Individual run result
                precision = r.get('precision', r.get('precision_mean', 0))
                recall = r.get('recall', r.get('recall_mean', 0))
                f1_val = r.get('f1', r.get('f1_score', r.get('f1_mean', 0)))
                batch_label = r['batch_size']
            
            logger.info(f"{r['difficulty']:<10} {batch_label:<8} "
                       f"{precision:<12.2%} {recall:<12.2%} {f1_val:<12.2%}")
    
    # Cleanup SSH tunnel
    if tunnel is not None:
        cleanup_ssh_tunnel(tunnel, verbose=args.verbose)
    
    return all_results, accuracy_results


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("Test suite interrupted by user.")
        print("=" * 60)
        print("Partial results may have been saved to:")
        print(f"  - {TEST_OUTPUT_DIR}/test_summary.json")
        print(f"  - {TEST_OUTPUT_DIR}/extracted_faults_*.csv")
        print(f"  - {TEST_OUTPUT_DIR}/final_faults_*.csv")
        print("=" * 60 + "\n")
        sys.exit(130)  # Standard exit code for Ctrl+C