#!/usr/bin/env python3
"""
Re-aggregate and print accuracy summary from existing test_summary.json
with CORRECTED aggregation logic (combining all metrics into one line per config).
"""
import json
import statistics
from pathlib import Path
from collections import defaultdict

def main():
    summary_file = Path(__file__).parent / "pipeline_output" / "test_summary.json"
    
    if not summary_file.exists():
        print(f"Error: {summary_file} not found")
        return
    
    with open(summary_file) as f:
        data = json.load(f)
    
    # Get individual run results (not already-aggregated entries)
    accuracy_results = data.get("accuracy_results", [])
    individual_runs = [r for r in accuracy_results if not r.get('is_aggregated')]
    
    if not individual_runs:
        print("No individual run results found")
        return
    
    # Group by (difficulty, batch_size) and re-aggregate correctly
    groups = defaultdict(list)
    for r in individual_runs:
        key = (r['difficulty'], r['batch_size'])
        groups[key].append(r)
    
    print("\n" + "=" * 60)
    print("Accuracy Summary (CORRECTED Aggregation)")
    print("=" * 60)
    print(f"{'Difficulty':<10} {'Batch':<8} {'Precision':<12} {'Recall':<12} {'F1':<12}")
    print("-" * 60)
    
    # Sort keys for consistent output
    sorted_keys = sorted(groups.keys(), key=lambda x: (x[0] == 'medium', x[0] == 'hard', x[1]))
    
    for key in sorted_keys:
        difficulty, batch_size = key
        runs = groups[key]
        # Print individual runs
        for r in runs:
            precision = r.get('precision', r.get('precision_mean', 0))
            recall = r.get('recall', r.get('recall_mean', 0))
            f1_val = r.get('f1', r.get('f1_score', r.get('f1_mean', 0)))
            print(f"{difficulty:<10} {batch_size:<8} "
                   f"{precision:<12.2%} {recall:<12.2%} {f1_val:<12.2%}")
        
        # If multiple runs, print aggregated line with CORRECT logic
        if len(runs) > 1:
            precisions = [r.get('precision', r.get('precision_mean', 0)) for r in runs]
            recalls = [r.get('recall', r.get('recall_mean', 0)) for r in runs]
            f1s = [r.get('f1', r.get('f1_score', r.get('f1_mean', 0))) for r in runs]
            
            avg_precision = statistics.mean(precisions)
            avg_recall = statistics.mean(recalls)
            avg_f1 = statistics.mean(f1s)
            
            batch_label = f"{batch_size}(n={len(runs)})"
            print(f"{difficulty:<10} {batch_label:<8} "
                   f"{avg_precision:<12.2%} {avg_recall:<12.2%} {avg_f1:<12.2%}  <-- CORRECTED!")
    
    print("=" * 60)
    
    # Summary by difficulty
    print("\nSummary by Difficulty (Averaged Across All Batches):")
    print("-" * 60)
    
    for difficulty in ["easy", "medium", "hard"]:
        difficulty_runs = [r for r in individual_runs if r['difficulty'] == difficulty]
        
        if difficulty_runs:
            precisions = [r.get('precision', r.get('precision_mean', 0)) for r in difficulty_runs]
            recalls = [r.get('recall', r.get('recall_mean', 0)) for r in difficulty_runs]
            f1s = [r.get('f1', r.get('f1_score', r.get('f1_mean', 0))) for r in difficulty_runs]
            
            avg_precision = statistics.mean(precisions)
            avg_recall = statistics.mean(recalls)
            avg_f1 = statistics.mean(f1s)
            
            print(f"{difficulty:<10}: Precision={avg_precision:.2%}, Recall={avg_recall:.2%}, F1={avg_f1:.2%}")
    
    print("\n✅ Key Fix: Each (n=X) line now shows ALL three metrics correctly!")
    print("   Previously: 4 broken lines per config (one per metric)")
    print("   Now: 1 correct aggregated line per config")
    print()

if __name__ == "__main__":
    main()
