#!/usr/bin/env python3
"""
Main pipeline orchestrator for CLAW-Agent.
Handles SSH tunnel management and runs the complete fault extraction pipeline.
"""
import argparse
import time
import subprocess
import sys
import shutil
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utils.logging_utils import logger, setup_logging
from utils.shutdown import setup_shutdown_handler, is_shutdown_requested
from data.data_loading import main_function1 as load_data
from analysis.shift_summary import main_function2 as extract_faults
from analysis.fault_filter import main_function_filter as filter_faults
from analysis.accuracy_test import main_function3 as verify_faults
from analysis.fixer import main_function4 as fix_timestamps
from analysis.verifyer import main_function5 as final_verification
from analysis.tag_extraction import main_tagger
from config import AGENT_NAME, DEFAULT_HALLS, BASE_DIR, validate_config_strict, SSH_TUNNELS, SSH_USERNAME, SSH_HOST, SSH_FORCE_CLOSE_PORTS


def _check_port_conflicts(ports: list) -> tuple:
    """
    Check which ports are already in use.
    
    Args:
        ports: List of local port numbers to check
        
    Returns:
        Tuple of (conflicting_ports, all_ports_free)
        - conflicting_ports: List of ports that are in use
        - all_ports_free: True if all ports are free, False otherwise
    """
    conflicting_ports = []
    
    for port in ports:
        try:
            # Method 1: Try fuser first
            result = subprocess.run(
                ["fuser", str(port)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                conflicting_ports.append(port)
            else:
                # Method 2: Try lsof as fallback
                lsof_result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True
                )
                if lsof_result.returncode == 0 and lsof_result.stdout.strip():
                    conflicting_ports.append(port)
        except FileNotFoundError:
            # fuser/lsof not available - try socket binding check
            logger.debug(f"Port checking tools not available, attempting direct bind test for port {port}")
            try:
                import socket
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_result = test_sock.connect_ex(('127.0.0.1', port))
                test_sock.close()
                if test_result == 0:
                    conflicting_ports.append(port)
            except Exception as e:
                logger.debug(f"Could not test port {port}: {e}")
        except Exception as e:
            logger.warning(f"Error checking port {port}: {e}")
    
    return conflicting_ports, len(conflicting_ports) == 0


def _kill_port_processes(ports: list) -> int:
    """
    Kill any processes using the specified local ports.
    
    Args:
        ports: List of local port numbers to free
        
    Returns:
        Number of processes killed
    """
    killed_count = 0
    for port in ports:
        try:
            # Method 1: Try fuser first
            result = subprocess.run(
                ["fuser", str(port)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                # Port is in use, kill the process
                logger.info(f"Port {port} is in use (PID: {result.stdout.strip()}). Killing process...")
                kill_result = subprocess.run(
                    ["fuser", "-k", "-9", f"{port}/tcp"],  # -9 for SIGKILL
                    capture_output=True,
                    text=True
                )
                if kill_result.returncode == 0:
                    logger.info(f"Successfully killed process on port {port}")
                    killed_count += 1
                else:
                    logger.warning(f"fuser -k failed for port {port}: {kill_result.stderr}")
            else:
                # Method 2: Try lsof as fallback
                lsof_result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True
                )
                if lsof_result.returncode == 0 and lsof_result.stdout.strip():
                    pids = lsof_result.stdout.strip().split()
                    logger.info(f"Port {port} is in use (PIDs: {', '.join(pids)}). Killing processes...")
                    for pid in pids:
                        kill_result = subprocess.run(
                            ["kill", "-9", pid],
                            capture_output=True,
                            text=True
                        )
                        if kill_result.returncode == 0:
                            logger.info(f"Successfully killed PID {pid} on port {port}")
                            killed_count += 1
                        else:
                            logger.warning(f"Failed to kill PID {pid}: {kill_result.stderr}")
                else:
                    logger.debug(f"Port {port} appears free")
        except FileNotFoundError:
            # fuser/lsof not available - try socket binding check
            logger.debug(f"Port checking tools not available, attempting direct bind test for port {port}")
            try:
                import socket
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_result = test_sock.connect_ex(('127.0.0.1', port))
                test_sock.close()
                if test_result == 0:
                    logger.warning(f"Port {port} is in use but cannot be freed (no fuser/lsof available)")
            except Exception as e:
                logger.debug(f"Could not test port {port}: {e}")
        except Exception as e:
            logger.warning(f"Error checking/killing port {port}: {e}")
    
    # Add delay to ensure ports are fully released
    if killed_count > 0:
        logger.info("Waiting 2 seconds for ports to be fully released...")
        time.sleep(2)
    
    return killed_count


def _cleanup_data_folder():
    """
    Delete all CSV and JSON files in the data folder except those in final_output subfolder.
    Handles both .json and .JSON extensions.
    """
    data_dir = BASE_DIR / "data"
    if not data_dir.exists():
        logger.debug("Data directory does not exist, skipping cleanup")
        return
    
    final_output_dir = data_dir / "final_output"
    cleaned_count = 0
    
    # Walk through all subdirectories
    for item in data_dir.rglob("*"):
        if item.is_file() and item.suffix.lower() in (".csv", ".json"):
            # Skip files in final_output
            try: 
                item.relative_to(final_output_dir)
                # If we get here, the file is in final_output - skip it
                continue
            except ValueError:
                # File is NOT in final_output - delete it
                try:
                    item.unlink()
                    logger.debug(f"Deleted: {item}")
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {item}: {e}")
    
    logger.info(f"Cleaned up {cleaned_count} files (CSV/JSON) from data folder (preserved final_output)")


def run_pipeline(start_date: str, end_date: str, verbose: bool = False, 
                 agent: str = None, filter_faults_flag: bool = False, max_workers: int = 4, 
                 extract_batch_size: int = None, tag_batch_size: int = None, 
                 filter_batch_size: int = None, validation_batch_size: int = None, 
                 fixing_batch_size: int = None, halls: list = None):
    """
    Run the complete fault extraction pipeline.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        verbose: Enable verbose logging
        agent: Agent for all pipeline stages (defaults to AGENT_NAME)
        filter_faults_flag: Whether to run fault filtering step
        max_workers: Number of parallel workers for LLM calls (default: 4)
        extract_batch_size: Number of summaries per batch for extraction (None = no batching)
        tag_batch_size: Number of faults per batch for tagging (None = no batching)
        filter_batch_size: Number of faults per batch for filtering (None = no batching)
        validation_batch_size: Number of faults per batch for verification (None = no batching)
        fixing_batch_size: Number of faults per batch for fixing (None = no batching)
        halls: List of halls to process (default: all halls)
    """
    # Set up shutdown handler for graceful Ctrl+C
    setup_shutdown_handler()
    
    # Validate configuration before starting
    logger.info("Validating configuration...")
    try:
        validate_config_strict()
        logger.info("Configuration validation passed.")
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        return
    
    if verbose:
        setup_logging(level="DEBUG")
    else:
        setup_logging()
    
    # Clean up old CSV files before starting
    logger.info("Cleaning up old CSV files from data folder...")
    _cleanup_data_folder()
    
    logger.info("=" * 60)
    logger.info("CLAW-Agent Pipeline Started")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info("=" * 60)
    
    total_start = time.time()
    
    # Step 1: Load data
    logger.info("\n[1/5] Loading shift summaries...")
    step_start = time.time()
    halls = halls or DEFAULT_HALLS
    shift_df = load_data(start_date, end_date, halls=halls)
    
    if shift_df is None or len(shift_df) == 0:
        logger.error("No data loaded. Aborting.")
        return
    
    logger.info(f"Step 1 completed in {time.time() - step_start:.2f}s: {len(shift_df)} summaries")
    
    # Step 2: Extract faults
    logger.info(f"\n[2/5] Extracting faults from summaries...")
    step_start = time.time()
    faults_df, start_time = extract_faults(agent=agent, max_workers=max_workers, batch_size=extract_batch_size)
    
    if faults_df is None or len(faults_df) == 0:
        logger.warning("No faults extracted. Continuing with empty dataset.")
        faults_df = None
    else:
        # Step 2.4: Filter faults (optional - only if --filter flag is set) - BEFORE tagging
        if filter_faults_flag:
            logger.info(f"\n[2.4/5] Filtering non-fault entries...")
            filter_start = time.time()
            faults_df, removed_df = filter_faults(faults_df=faults_df, agent=agent, max_workers=max_workers, batch_size=filter_batch_size)
            
            if faults_df is None or len(faults_df) == 0:
                logger.warning("All faults filtered out. Continuing with empty dataset.")
                faults_df = None
            else:
                removed_count = len(removed_df) if removed_df is not None else 0
                logger.info(f"Filtering completed in {time.time() - filter_start:.2f}s: {removed_count} removed as non-faults")
        
        # Step 2.5: Add tags to extracted faults (after filtering if enabled)
        if faults_df is not None and len(faults_df) > 0:
            logger.info(f"\n[2.5/5] Adding tags to extracted faults...")
            faults_df = main_tagger(faults_df, start_time, agent=agent, max_workers=max_workers, batch_size=tag_batch_size)
            
            # Save extracted faults to CSV for downstream processing (after tagging)
            try:
                from config import PROCESSED_SUMMARIES_CSV
                PROCESSED_SUMMARIES_CSV.parent.mkdir(parents=True, exist_ok=True)
                faults_df.to_csv(PROCESSED_SUMMARIES_CSV, index=False)
                logger.info(f"Saved {len(faults_df)} extracted faults to {PROCESSED_SUMMARIES_CSV}")
            except Exception as e:
                logger.error(f"Failed to save faults to CSV: {e}")
            
            logger.info(f"Step 2 completed in {time.time() - step_start:.2f}s: {len(faults_df)} faults")
        else:
            logger.info(f"Step 2 completed in {time.time() - step_start:.2f}s: 0 faults (all filtered or none extracted)")
    
    # Step 3: Verify timestamps
    logger.info(f"\n[3/5] Verifying timestamp accuracy...")
    step_start = time.time()
    accurate_df, inaccurate_df = verify_faults(agent=agent, max_workers=max_workers, batch_size=validation_batch_size)
    
    accurate_count = len(accurate_df) if accurate_df is not None else 0
    inaccurate_count = len(inaccurate_df) if inaccurate_df is not None else 0
    logger.info(f"Step 3 completed in {time.time() - step_start:.2f}s: {accurate_count} accurate, {inaccurate_count} inaccurate")
    
    # Step 4: Fix inaccurate timestamps
    if inaccurate_count > 0:
        logger.info(f"\n[4/5] Fixing inaccurate timestamps...")
        step_start = time.time()
        fixed_df, manual_df = fix_timestamps(agent=agent, max_workers=max_workers, batch_size=fixing_batch_size)
        
        fixed_count = len(fixed_df) if fixed_df is not None else 0
        manual_count = len(manual_df) if manual_df is not None else 0
        logger.info(f"Step 4 completed in {time.time() - step_start:.2f}s: {fixed_count} fixed, {manual_count} manual check")
    else:
        logger.info("\n[4/5] Skipping fix step (no inaccurate timestamps)")
        from config import FIXED_CSV
        if FIXED_CSV.exists():
            FIXED_CSV.unlink()
            logger.debug("Cleared fixed.csv (no fixes needed)")
        fixed_df = None
        manual_df = None
    
    # Step 5: Consolidation (merge verified + fixed faults)
    logger.info("\n[5/5] Consolidating verified faults...")
    step_start = time.time()
    final_df = final_verification(agent=agent)
    
    final_count = len(final_df) if final_df is not None else 0
    logger.info(f"Step 5 completed in {time.time() - step_start:.2f}s: {final_count} faults consolidated")
    
    # Summary
    total_elapsed = time.time() - total_start
    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Summary")
    logger.info("=" * 60)
    logger.info(f"Shift summaries processed: {len(shift_df)}")
    logger.info(f"Initial faults extracted: {len(faults_df) if faults_df is not None else 0}")
    logger.info(f"Accurate on first pass: {accurate_count}")
    logger.info(f"Inaccurate (needed fixing): {inaccurate_count}")
    logger.info(f"Fixed successfully: {len(fixed_df) if fixed_df is not None else 0}")
    logger.info(f"Second pass verified faults: {final_count}")
    logger.info(f"Manual review needed: {len(manual_df) if manual_df is not None else 0}")
    logger.info(f"Final verified faults: {final_count}")
    logger.info(f"Total time: {total_elapsed:.2f} seconds ({total_elapsed/60:.2f} minutes)")
    logger.info("=" * 60)


def run_pipeline_with_tunnel(start_date: str, end_date: str, verbose: bool = False,
                             agent: str = None, filter_faults_flag: bool = False, max_workers: int = 4, 
                             extract_batch_size: int = None, tag_batch_size: int = None, 
                             filter_batch_size: int = None, validation_batch_size: int = None,
                             fixing_batch_size: int = None, halls: list = None):
    """
    Run the pipeline with SSH tunnel management for remote JLab access.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        verbose: Enable verbose logging
        agent: Agent for all pipeline stages
        filter_faults_flag: Whether to run fault filtering step
        max_workers: Number of parallel workers for LLM calls (default: 4)
        extract_batch_size: Number of summaries per batch for extraction (None = no batching)
        tag_batch_size: Number of faults per batch for tagging (None = no batching)
        filter_batch_size: Number of faults per batch for filtering (None = no batching)
        validation_batch_size: Number of faults per batch for verification (None = no batching)
        fixing_batch_size: Number of faults per batch for fixing (None = no batching)
        halls: List of halls to process (default: all halls)
    """
    # Only perform SSH tunnel operations if both credentials AND tunnel ports are configured
    ssh_enabled = SSH_USERNAME and SSH_HOST and SSH_TUNNELS
    
    if not ssh_enabled:
        # Skip all SSH tunnel cleanup and creation
        if not SSH_USERNAME:
            logger.warning("SSH_USERNAME not configured. Skipping SSH tunnel setup.")
        elif not SSH_HOST:
            logger.warning("SSH_HOST not configured. Skipping SSH tunnel setup.")
        elif not SSH_TUNNELS:
            logger.info("No SSH tunnel ports configured. Running without tunneling.")
        tunnel = None
    else:
        # Build SSH command with dynamic port forwards
        ssh_args = ["ssh", "-o", "LogLevel=ERROR", "-N"]
        for local_port, remote_port in SSH_TUNNELS:
            ssh_args.extend(["-L", f"{local_port}:127.0.0.1:{remote_port}"])
        ssh_args.append(f"{SSH_USERNAME}@{SSH_HOST}")
        
        # Extract local ports and check for conflicts
        local_ports = [local_port for local_port, _ in SSH_TUNNELS]
        
        logger.info(f"Checking ports {local_ports} for conflicts...")
        conflicting_ports, all_ports_free = _check_port_conflicts(local_ports)
        
        tunnel = None  # Default to no tunnel
        
        if conflicting_ports:
            if SSH_FORCE_CLOSE_PORTS:
                # Force-close conflicting ports
                logger.info(f"Ports {conflicting_ports} are in use. Force-closing processes...")
                killed = _kill_port_processes(conflicting_ports)
                if killed > 0:
                    logger.info(f"Freed {killed} port(s) for SSH tunnel")
                else:
                    logger.warning("Failed to free all conflicting ports. Tunnel creation may fail.")
                # Proceed to create tunnel after freeing ports
            else:
                # Skip tunnel creation - continue without tunneling
                logger.warning(f"\n{'='*60}")
                logger.warning(f"SSH tunnel skipped: Ports {conflicting_ports} are already in use.")
                logger.warning(f"Set SSH_FORCE_CLOSE_PORTS=true in .env to force-close these ports.")
                logger.warning(f"Pipeline will continue WITHOUT SSH tunneling.")
                logger.warning(f"{'='*60}\n")
                # tunnel remains None
        
        # Create tunnel if we have no conflicts or conflicts were resolved
        if tunnel is None and (all_ports_free or (conflicting_ports and SSH_FORCE_CLOSE_PORTS)):
            logger.info(f"Establishing SSH tunnel to {SSH_USERNAME}@{SSH_HOST} with {len(SSH_TUNNELS)} tunnel(s):")
            for local_port, remote_port in SSH_TUNNELS:
                logger.info(f"  {local_port} -> {remote_port}")
            
            tunnel = subprocess.Popen(ssh_args)
            
            # Wait for tunnel to establish
            time.sleep(2)
            
            if tunnel.poll() is not None:
                logger.error("SSH tunnel failed to start. Check SSH configuration.")
                tunnel = None  # Don't crash, just continue without tunnel
    
    try:
        # Run the main pipeline
        run_pipeline(start_date, end_date, verbose, agent, filter_faults_flag, max_workers, extract_batch_size, tag_batch_size, filter_batch_size, validation_batch_size, fixing_batch_size, halls)
    finally:
        # Clean up tunnel only if SSH was enabled
        if ssh_enabled:
            logger.info("Cleaning up SSH tunnel...")
            if tunnel is not None:
                tunnel.terminate()
                tunnel.wait()
            time.sleep(1)
            
            # Kill any remaining processes on configured ports
            local_ports = [local_port for local_port, _ in SSH_TUNNELS]
            _kill_port_processes(local_ports)


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='CLAW-Agent: Jefferson Lab Shift Summary Fault Analysis with parallel processing (up to 2.5x faster)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --verbose
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --workers 6
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --extract-size 5
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --tag-size 10
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --filter-size 15
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --validation-size 20
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --fixing-size 25
  python src/pipeline.py --start-date 2024-01-01 --end-date 2024-01-31 --halls hall_a hall_b
        """
    )
    
    parser.add_argument(
        '--start-date', 
        type=str, 
        default="2024-01-01", 
        help='Start date in YYYY-MM-DD format (default: 2024-01-01)'
    )
    
    parser.add_argument(
        '--end-date', 
        type=str, 
        default="2024-01-31", 
        help='End date in YYYY-MM-DD format (default: 2024-01-31)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--no-tunnel',
        action='store_true',
        help='Skip SSH tunnel creation (use if running locally)'
    )
    
    parser.add_argument(
        '--filter',
        action='store_true',
        help='Enable fault filtering step to remove non-fault entries'
    )
    
    parser.add_argument(
        '--agent',
        type=str,
        default=AGENT_NAME,
        help=f'Agent for all pipeline stages (default: {AGENT_NAME})'
    )
    
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=5,
        help='Number of parallel workers for LLM calls (default: 4, optimal based on benchmark)'
    )
    
    parser.add_argument(
        '--extract-size', '-e',
        type=int,
        default=5,
        help='Number of shift summaries to batch together per LLM call for extraction (default: None = no batching)'
    )
    
    parser.add_argument(
        '--tag-size', '-t',
        type=int,
        default=5,
        help='Number of faults to batch together per LLM call for tagging (default: None = no batching)'
    )
    
    parser.add_argument(
        '--filter-size', '-f',
        type=int,
        default=5,
        help='Number of faults to batch together per LLM call for filtering (default: None = no batching)'
    )
    
    parser.add_argument(
        '--validation-size', '-v',
        type=int,
        default=5,
        help='Number of faults to batch together per LLM call for timestamp verification (default: None = no batching)'
    )
    
    parser.add_argument(
        '--fixing-size', '-x',
        type=int,
        default=5,
        help='Number of faults to batch together per LLM call for timestamp fixing (default: None = no batching)'
    )
    
    parser.add_argument(
        '--halls',
        type=str,
        nargs='+',
        choices=['hall_a', 'hall_b', 'hall_c', 'hall_d'],
        default=None,
        help='Hall(s) to process (hall_a, hall_b, hall_c, hall_d). Default: all halls'
    )
    
    args = parser.parse_args()
    
    # Validate dates
    try:
        from datetime import datetime
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
        end = datetime.strptime(args.end_date, "%Y-%m-%d")
        
        if start > end:
            parser.error("Start date must be before end date")
    except ValueError as e:
        parser.error(f"Invalid date format: {e}. Use YYYY-MM-DD.")
    
    # Run pipeline with or without tunnel based on --no-tunnel flag
    # Convert hall argument to list if provided
    halls = args.halls if args.halls else None
    
    if args.no_tunnel:
        run_pipeline(
            args.start_date, 
            args.end_date, 
            args.verbose, 
            args.agent,
            args.filter,
            args.workers,
            args.extract_size,
            args.tag_size,
            args.filter_size,
            args.validation_size,
            args.fixing_size,
            halls
        )
    else:
        run_pipeline_with_tunnel(
            args.start_date, 
            args.end_date, 
            args.verbose, 
            args.agent,
            args.filter,
            args.workers,
            args.extract_size,
            args.tag_size,
            args.filter_size,
            args.validation_size,
            args.fixing_size,
            halls
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)  # 130 is the conventional exit code for Ctrl+C
