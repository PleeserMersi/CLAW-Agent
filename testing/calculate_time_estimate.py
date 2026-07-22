#!/usr/bin/env python3
"""
Calculate time estimates for mock pipeline tests based on historical time data.
"""

import json
import sys
from pathlib import Path

# Path to time data file (JSON format)
TIME_DATA_FILE = Path(__file__).parent / "time_data.json"

# Path to mock summaries directory
MOCK_SUMMARIES_DIR = Path(__file__).parent / "mock_summaries"

def parse_time_data():
    """Parse the time data JSON file and return structured data."""
    if not TIME_DATA_FILE.exists():
        return None, None
    
    try:
        with open(TIME_DATA_FILE, 'r') as f:
            data = json.load(f)
        
        batching_data = data.get('batching_time_data', [])
        parallel_data = data.get('parallel_worker_time_data', [])
        
        return batching_data, parallel_data
    except (json.JSONDecodeError, IOError):
        return None, None

def get_mock_summary_count(level: str) -> int:
    """Get the number of shift summaries in the mock data for a given difficulty level."""
    import csv
    mock_file = MOCK_SUMMARIES_DIR / f"mock_summaries_{level}.csv"
    if not mock_file.exists():
        return 10  # Default fallback
    
    # Count CSV rows (shift summaries) properly handling multi-line content
    with open(mock_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        count = sum(1 for _ in reader)
    return max(1, count)

def get_avg_batch_time(batch_size: int, level: str = "medium") -> float:
    """Get average time for a specific batch size, scaled to mock data entry count."""
    batching_data, _ = parse_time_data()
    if not batching_data:
        return None
    
    # Map batch size to label
    batch_labels = {
        1: "Single Batch",
        2: "Double Batch",
        3: "Triple Batch",
        4: "Quadruple Batch",
        5: "Quintuple Batch",
        6: "Sextuple Batch",
        7: "Septuple Batch",
        8: "Octuple Batch",
        9: "Nonuple",
        10: "Decuple",
        15: "Quindecuple",
        20: "Vigintuple"
    }
    
    label = batch_labels.get(batch_size)
    if not label:
        # For batch sizes not in data, interpolate
        base_time = estimate_batch_time(batch_size)
    else:
        times = [entry['total'] for entry in batching_data if entry['batch'] == label]
        if times:
            base_time = sum(times) / len(times)
        else:
            base_time = estimate_batch_time(batch_size)
    
    if base_time is None:
        return None
    
    # Scale based on mock data entry count vs time data entry count
    mock_count = get_mock_summary_count(level)
    time_data_count = 9  # Standard entry count in time_data.json for batching
    
    scaled_time = base_time * (mock_count / time_data_count)
    return scaled_time

def estimate_batch_time(batch_size):
    """Estimate time for batch sizes not in the data using linear interpolation."""
    # Known data points (batch_size, avg_time)
    known_points = [
        (1, 772.23),   # Average of Single Batch runs
        (2, 375.44),   # Average of Double Batch runs
        (3, 316.15),   # Average of Triple Batch runs
        (4, 299.31),   # Average of Quadruple Batch runs
        (5, 266.61),   # Average of Quintuple Batch runs
        (6, 253.64),   # Average of Sextuple Batch runs
        (7, 227.84),   # Average of Septuple Batch runs
        (8, 249.52),   # Average of Octuple Batch runs
        (9, 195.37),   # Average of Nonuple runs
        (10, 206.92),  # Average of Decuple runs
        (15, 191.53),  # Average of Quindecuple runs
        (20, 174.89)   # Average of Vigintuple runs
    ]
    
    # Sort by batch size
    known_points.sort(key=lambda x: x[0])
    
    # Find surrounding points
    if batch_size <= known_points[0][0]:
        return known_points[0][1]
    if batch_size >= known_points[-1][0]:
        return known_points[-1][1]
    
    for i in range(len(known_points) - 1):
        if known_points[i][0] <= batch_size <= known_points[i+1][0]:
            x0, y0 = known_points[i]
            x1, y1 = known_points[i+1]
            # Linear interpolation
            return y0 + (batch_size - x0) * (y1 - y0) / (x1 - x0)
    
    return known_points[-1][1]

def get_avg_parallel_time(num_workers: int, dataset_size: str = "medium") -> float:
    """Get average time for a specific number of parallel workers, scaled to mock data entry count."""
    _, parallel_data = parse_time_data()
    if not parallel_data:
        return None
    
    # Filter by dataset size
    filtered = [entry for entry in parallel_data if entry.get('dataset') == dataset_size and entry.get('workers') == num_workers]
    
    times = [entry['total'] for entry in filtered]
    if times:
        base_time = sum(times) / len(times)
    else:
        # Estimate if not found
        base_time = estimate_parallel_time(num_workers, dataset_size)
    
    if base_time is None:
        return None
    
    # Scale based on mock data entry count vs time data entry count
    mock_count = get_mock_summary_count(dataset_size)
    time_data_count = 9  # Standard entry count in time_data.json for medium dataset
    
    scaled_time = base_time * (mock_count / time_data_count)
    return scaled_time

def estimate_parallel_time(num_workers, dataset_size="medium"):
    """Estimate time for worker counts not in the data."""
    # Known data points for medium dataset (workers, avg_time)
    known_points = [
        (1, 1665.42),
        (2, 1064.55),
        (3, 764.00),
        (4, 772.23),
        (5, 743.46),
        (6, 653.55)
    ]
    
    # Sort by worker count
    known_points.sort(key=lambda x: x[0])
    
    if num_workers <= known_points[0][0]:
        return known_points[0][1]
    if num_workers >= known_points[-1][0]:
        # Extrapolate with diminishing returns
        last_workers, last_time = known_points[-1]
        # Assume ~10% improvement per additional worker up to a limit
        improvement_factor = max(0.5, 1 - (num_workers - last_workers) * 0.1)
        return last_time * improvement_factor
    
    for i in range(len(known_points) - 1):
        if known_points[i][0] <= num_workers <= known_points[i+1][0]:
            x0, y0 = known_points[i]
            x1, y1 = known_points[i+1]
            return y0 + (num_workers - x0) * (y1 - y0) / (x1 - x0)
    
    return known_points[-1][1]

def calculate_total_estimate(batch_sizes, parallel_workers, runs_per_config, num_difficulties=3):
    """
    Calculate total estimated time for the test suite.
    
    Args:
        batch_sizes: List of batch sizes to test
        parallel_workers: List of parallel worker counts to test
        runs_per_config: Number of runs per configuration
        num_difficulties: Number of difficulty levels (default 3: easy, medium, hard)
    
    Returns:
        Total estimated time in seconds
    """
    total_seconds = 0
    
    # Calculate batch testing time
    # Each batch size is run for each difficulty level
    for batch_size in batch_sizes:
        # Use medium level for batching time data (standard reference)
        avg_time = get_avg_batch_time(batch_size, "medium")
        if avg_time is None:
            avg_time = estimate_batch_time(batch_size)
        # Run for each difficulty level and each run count
        total_seconds += avg_time * num_difficulties * runs_per_config
    
    # Calculate parallel workers testing time
    # Parallel testing is only for medium difficulty
    for num_workers in parallel_workers:
        avg_time = get_avg_parallel_time(num_workers, "medium")
        if avg_time is None:
            avg_time = estimate_parallel_time(num_workers, "medium")
        # Run for each run count (single difficulty level)
        total_seconds += avg_time * runs_per_config
    
    return total_seconds

def format_time(seconds):
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"~{int(seconds)} seconds"
    
    minutes = seconds / 60
    if minutes < 60:
        return f"~{int(minutes)} minutes"
    
    hours = minutes / 60
    if hours < 24:
        int_hours = int(hours)
        rem_minutes = int((hours - int_hours) * 60)
        if rem_minutes == 0:
            return f"~{int_hours} hours"
        return f"~{int_hours} hours {rem_minutes} minutes"
    
    days = hours / 24
    int_days = int(days)
    rem_hours = int((days - int_days) * 24)
    if rem_hours == 0:
        return f"~{int_days} days"
    return f"~{int_days} days {rem_hours} hours"

def main():
    """Main entry point."""
    if len(sys.argv) < 4:
        print("Usage: calculate_time_estimate.py <batch_sizes> <parallel_workers> <runs_per_config>")
        print("  batch_sizes: comma-separated list (e.g., '1,2,4,8')")
        print("  parallel_workers: comma-separated list (e.g., '1,2,4,8')")
        print("  runs_per_config: integer")
        sys.exit(1)
    
    batch_sizes = [int(x.strip()) for x in sys.argv[1].split(',')]
    parallel_workers = [int(x.strip()) for x in sys.argv[2].split(',')]
    runs_per_config = int(sys.argv[3])
    
    total_seconds = calculate_total_estimate(batch_sizes, parallel_workers, runs_per_config)
    formatted_time = format_time(total_seconds)
    
    print(formatted_time)

if __name__ == "__main__":
    main()