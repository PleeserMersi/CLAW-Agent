#!/usr/bin/env python3
"""
Estimate test runtime based on number of runs per configuration.

Based on observed data:
- 1 run per config = ~6 hours
- 2 runs per config = ~12 hours
- Linear scaling with runs count

Configuration breakdown:
- Phase 1: 3 difficulties × 20 batch sizes = 60 configs
- Phase 2: 10 parallel worker counts (medium, batch=5) = 10 configs
- Total: 70 configurations
"""

def estimate_time_hours(runs: int) -> float:
    """
    Estimate total test runtime in hours based on runs per configuration.
    
    Args:
        runs: Number of runs per configuration (1, 2, 3, etc.)
    
    Returns:
        Estimated total runtime in hours
    """
    # Based on empirical measurement: 1 run = ~6 hours for 70 configs
    BASE_TIME_HOURS = 6.0
    return BASE_TIME_HOURS * runs


def estimate_time_breakdown(runs: int) -> dict:
    """
    Get detailed time breakdown by test phase.
    
    Args:
        runs: Number of runs per configuration
    
    Returns:
        Dictionary with time breakdown
    """
    # Phase 1: Batch testing (3 difficulties × 20 batch sizes = 60 configs)
    phase1_configs = 60
    
    # Phase 2: Parallel workers testing (10 configs for medium difficulty)
    phase2_configs = 10
    
    # Total configs
    total_configs = phase1_configs + phase2_configs  # 70
    
    # Time per pipeline run (based on 6 hours / 70 configs)
    time_per_run_minutes = (6.0 * 60) / total_configs  # ~5.14 minutes
    
    # Total runs
    total_runs = total_configs * runs
    
    # Time breakdown
    phase1_time = phase1_configs * runs * time_per_run_minutes / 60  # hours
    phase2_time = phase2_configs * runs * time_per_run_minutes / 60  # hours
    
    return {
        'runs_per_config': runs,
        'total_configs': total_configs,
        'phase1_configs': phase1_configs,
        'phase2_configs': phase2_configs,
        'total_runs': total_runs,
        'time_per_run_minutes': round(time_per_run_minutes, 2),
        'phase1_hours': round(phase1_time, 2),
        'phase2_hours': round(phase2_time, 2),
        'total_hours': round(phase1_time + phase2_time, 2),
        'total_days': round((phase1_time + phase2_time) / 24, 2)
    }


def print_estimate(runs: int):
    """Print a formatted time estimate."""
    breakdown = estimate_time_breakdown(runs)
    
    print("=" * 50)
    print("TEST TIME ESTIMATE")
    print("=" * 50)
    print(f"Runs per configuration: {breakdown['runs_per_config']}")
    print(f"Total configurations:   {breakdown['total_configs']}")
    print(f"  - Phase 1 (batch):    {breakdown['phase1_configs']} configs")
    print(f"  - Phase 2 (parallel): {breakdown['phase2_configs']} configs")
    print(f"Total pipeline runs:    {breakdown['total_runs']}")
    print(f"Time per run:           ~{breakdown['time_per_run_minutes']} minutes")
    print("-" * 50)
    print(f"Phase 1 time:           ~{breakdown['phase1_hours']} hours")
    print(f"Phase 2 time:           ~{breakdown['phase2_hours']} hours")
    print(f"TOTAL TIME:             ~{breakdown['total_hours']} hours ({breakdown['total_days']} days)")
    print("=" * 50)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        runs = int(sys.argv[1])
    else:
        # Show common examples
        runs = 3
    
    print_estimate(runs)
    
    # Show a quick reference table
    print("\nQuick Reference:")
    print("-" * 30)
    for r in [1, 2, 3, 5, 10, 30]:
        hours = estimate_time_hours(r)
        days = hours / 24
        print(f"  runs={r:2d}: ~{hours:5.1f} hours ({days:5.2f} days)")