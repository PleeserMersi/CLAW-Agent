#!/usr/bin/env python3
"""
Parallel Workers Benchmark (Batch Size 5)

Generates visualization graphs showing performance across different worker counts
when using a fixed batch size of 5. This helps identify the optimal number of
parallel workers for fault extraction.

Data is loaded from accuracy_data.json which contains results from running
the pipeline with --parallel-workers flag.
"""

import matplotlib.pyplot as plt
import numpy as np
import json
import os
from collections import defaultdict

# Create graphs directory if it doesn't exist
script_dir = os.path.dirname(os.path.abspath(__file__))
graphs_dir = os.path.join(script_dir, 'graphs')
os.makedirs(graphs_dir, exist_ok=True)

# Load benchmark data from accuracy_data.json
data_file = os.path.join(script_dir, 'accuracy_data.json')
if not os.path.exists(data_file):
    print(f"Error: Benchmark data file not found: {data_file}")
    print("Run the pipeline with --parallel-workers flag first to generate data.")
    exit(1)

with open(data_file, 'r') as f:
    accuracy_data = json.load(f)

# Filter for batch size 5 (or the specified batch size)
# The data should have entries with "max_workers" field for parallel testing
parallel_data = [d for d in accuracy_data if 'max_workers' in d]

if not parallel_data:
    print("Error: No parallel workers data found in accuracy_data.json")
    print("Make sure to run with --parallel-workers flag.")
    exit(1)

# Organize data by difficulty level
difficulty_groups = defaultdict(list)
for entry in parallel_data:
    difficulty = entry.get('difficulty', 'unknown')
    difficulty_groups[difficulty].append(entry)

# Function to calculate average metrics per worker count
def analyze_parallel_data(entries):
    """Group by worker count and calculate mean + std for each metric.
    
    Handles both individual run entries and aggregated entries:
    - If individual runs exist: uses them to calculate mean/std
    - If only aggregated entries exist: uses the pre-calculated mean/stdev
    """
    worker_metrics = defaultdict(lambda: {
        'precision': [], 'recall': [], 'f1': [], 'total_time': []
    })
    worker_agg = defaultdict(lambda: {
        'precision_mean': None, 'precision_stdev': 0,
        'recall_mean': None, 'recall_stdev': 0,
        'f1_mean': None, 'f1_stdev': 0
    })
    
    for entry in entries:
        workers = entry.get('max_workers', 1)
        
        # Check if this is an aggregated entry
        if entry.get('is_aggregated', False):
            # Store aggregated values separately
            if 'precision_mean' in entry:
                worker_agg[workers]['precision_mean'] = entry['precision_mean']
                worker_agg[workers]['precision_stdev'] = entry.get('precision_stdev', 0)
            if 'recall_mean' in entry:
                worker_agg[workers]['recall_mean'] = entry['recall_mean']
                worker_agg[workers]['recall_stdev'] = entry.get('recall_stdev', 0)
            if 'f1_score_mean' in entry:
                worker_agg[workers]['f1_mean'] = entry['f1_score_mean']
                worker_agg[workers]['f1_stdev'] = entry.get('f1_score_stdev', 0)
        else:
            # Individual run entry - collect raw values
            if 'precision' in entry:
                worker_metrics[workers]['precision'].append(entry['precision'])
            if 'recall' in entry:
                worker_metrics[workers]['recall'].append(entry['recall'])
            if 'f1' in entry or 'f1_score' in entry:
                f1 = entry.get('f1', entry.get('f1_score', 0))
                worker_metrics[workers]['f1'].append(f1)
    
    # Calculate final metrics per worker count
    workers = sorted(set(worker_metrics.keys()) | set(worker_agg.keys()))
    precisions = []
    prec_stds = []
    recalls = []
    rec_stds = []
    f1_scores = []
    f1_stds = []
    
    for w in workers:
        # Prefer aggregated values if available, otherwise calculate from individual runs
        if worker_agg[w]['precision_mean'] is not None:
            precisions.append(worker_agg[w]['precision_mean'])
            prec_stds.append(worker_agg[w]['precision_stdev'])
        elif worker_metrics[w]['precision']:
            precisions.append(np.mean(worker_metrics[w]['precision']))
            prec_stds.append(np.std(worker_metrics[w]['precision']) if len(worker_metrics[w]['precision']) > 1 else 0)
        else:
            precisions.append(0)
            prec_stds.append(0)
        
        if worker_agg[w]['recall_mean'] is not None:
            recalls.append(worker_agg[w]['recall_mean'])
            rec_stds.append(worker_agg[w]['recall_stdev'])
        elif worker_metrics[w]['recall']:
            recalls.append(np.mean(worker_metrics[w]['recall']))
            rec_stds.append(np.std(worker_metrics[w]['recall']) if len(worker_metrics[w]['recall']) > 1 else 0)
        else:
            recalls.append(0)
            rec_stds.append(0)
        
        if worker_agg[w]['f1_mean'] is not None:
            f1_scores.append(worker_agg[w]['f1_mean'])
            f1_stds.append(worker_agg[w]['f1_stdev'])
        elif worker_metrics[w]['f1']:
            f1_scores.append(np.mean(worker_metrics[w]['f1']))
            f1_stds.append(np.std(worker_metrics[w]['f1']) if len(worker_metrics[w]['f1']) > 1 else 0)
        else:
            f1_scores.append(0)
            f1_stds.append(0)
    
    return workers, precisions, prec_stds, recalls, rec_stds, f1_scores, f1_stds

# Generate graphs for each difficulty level
for difficulty, entries in difficulty_groups.items():
    workers, precisions, prec_stds, recalls, rec_stds, f1_scores, f1_stds = analyze_parallel_data(entries)
    
    if not workers:
        print(f"Warning: No data for difficulty level '{difficulty}'")
        continue
    
    # Graph 1: Accuracy Metrics vs Worker Count with error bars
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(workers))
    width = 0.25
    
    ax.bar(x - width, precisions, width, yerr=prec_stds, label='Precision', alpha=0.8, color='steelblue', capsize=5)
    ax.bar(x, recalls, width, yerr=rec_stds, label='Recall', alpha=0.8, color='coral', capsize=5)
    ax.bar(x + width, f1_scores, width, yerr=f1_stds, label='F1 Score', alpha=0.8, color='forestgreen', capsize=5)
    
    ax.set_xlabel('Number of Parallel Workers', fontsize=11)
    ax.set_ylabel('Accuracy Score', fontsize=11)
    ax.set_title(f'Parallel Workers Performance (Batch Size 5)\n{difficulty.capitalize()} Difficulty', fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels([str(w) for w in workers])
    ax.legend(loc='lower left')
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars (only if std is 0 or single run)
    for i, (p, r, f) in enumerate(zip(precisions, recalls, f1_scores)):
        if prec_stds[i] == 0 and rec_stds[i] == 0 and f1_stds[i] == 0:
            ax.text(i - width, p + 0.02, f'{p:.2f}', ha='center', fontsize=9)
            ax.text(i, r + 0.02, f'{r:.2f}', ha='center', fontsize=9)
            ax.text(i + width, f + 0.02, f'{f:.2f}', ha='center', fontsize=9)
    
    output_path = os.path.join(graphs_dir, f'parallel_workers_batch5_{difficulty}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Graph saved: {output_path}")
    plt.close()

# Graph 2: Combined comparison across all difficulty levels
if len(difficulty_groups) > 1:
    fig, axes = plt.subplots(1, len(difficulty_groups), figsize=(5 * len(difficulty_groups), 5), sharey=True)
    if len(difficulty_groups) == 1:
        axes = [axes]
    
    for idx, (difficulty, entries) in enumerate(sorted(difficulty_groups.items())):
        workers, precisions, prec_stds, recalls, rec_stds, f1_scores, f1_stds = analyze_parallel_data(entries)
        
        if not workers:
            continue
        
        ax = axes[idx]
        x = np.arange(len(workers))
        width = 0.25
        
        ax.bar(x - width, precisions, width, yerr=prec_stds, label='Precision', alpha=0.8, color='steelblue', capsize=5)
        ax.bar(x, recalls, width, yerr=rec_stds, label='Recall', alpha=0.8, color='coral', capsize=5)
        ax.bar(x + width, f1_scores, width, yerr=f1_stds, label='F1 Score', alpha=0.8, color='forestgreen', capsize=5)
        
        ax.set_xlabel('Number of Workers', fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([str(w) for w in workers])
        ax.set_title(f'{difficulty.capitalize()}\n(Batch Size 5)', fontsize=11)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3, axis='y')
        ax.legend(fontsize=8)
    
    axes[0].set_ylabel('Accuracy Score', fontsize=11)
    fig.suptitle('Parallel Workers Performance Comparison (Batch Size 5)', fontsize=13, fontweight='bold')
    
    output_path = os.path.join(graphs_dir, 'parallel_workers_batch5_comparison.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Graph saved: {output_path}")
    plt.close()

# Graph 3: F1 Score trend line with error bars
if len(difficulty_groups) > 0:
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = {'easy': 'green', 'medium': 'orange', 'hard': 'red'}
    markers = {'easy': 'o', 'medium': 's', 'hard': '^'}
    
    for difficulty, entries in sorted(difficulty_groups.items()):
        workers, precisions, prec_stds, recalls, rec_stds, f1_scores, f1_stds = analyze_parallel_data(entries)
        if not workers:
            continue
        
        color = colors.get(difficulty, 'blue')
        marker = markers.get(difficulty, 'o')
        ax.errorbar(workers, f1_scores, yerr=f1_stds, marker=marker, linewidth=2, markersize=8, 
                    label=f'{difficulty.capitalize()}', color=color, capsize=5, ecolor=color)
    
    ax.set_xlabel('Number of Parallel Workers', fontsize=11)
    ax.set_ylabel('F1 Score', fontsize=11)
    ax.set_title('F1 Score Trend Across Worker Counts (Batch Size 5)', fontsize=12)
    ax.legend(loc='lower left')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.05)
    
    output_path = os.path.join(graphs_dir, 'parallel_workers_batch5_f1_trend.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Graph saved: {output_path}")
    plt.close()

print(f"\nAll parallel workers (batch=5) benchmark graphs saved in '{graphs_dir}' directory.")
print(f"Generated {len(difficulty_groups)} difficulty-specific graphs and comparison charts.")