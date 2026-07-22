#!/usr/bin/env python3
"""
Fault Extraction Pipeline Accuracy Evaluator

Calculates precision, recall, and F1 score for fault extraction pipelines.
Accounts for missed faults, hallucinated faults, and partial correctness.

Input Files:
- Ground truth shift summaries (CSV with format: LogNumber,LogbookURL,Title,Date,DateTime,Format,Content,NormalizedContent)
- Extracted faults CSV (CSV with format: FullTimestamp,timestamp,description,tag,run_number,ShiftLogNumber,ShiftLogbookURL,ShiftTitle,ShiftDateTime,FragmentLink,verification_status)

The ground truth file must have a companion file with the same name but _faults suffix
containing the known faults for each shift summary.
"""

import csv
import re
import argparse
import os
from datetime import datetime
from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json


@dataclass
class GroundTruthFault:
    """Represents a known fault from ground truth data."""
    timestamp: str
    description: str
    tag: str
    run_number: Optional[str]
    shift_log_number: int
    shift_logbook_url: str
    shift_title: str
    shift_datetime: str


@dataclass
class ExtractedFault:
    """Represents a fault extracted by the pipeline."""
    full_timestamp: str
    timestamp: str
    description: str
    tag: str
    run_number: Optional[str]
    shift_log_number: int
    shift_logbook_url: str
    shift_title: str
    shift_datetime: str
    fragment_link: str
    verification_status: str


@dataclass
class MatchResult:
    """Result of matching ground truth to extracted faults."""
    true_positives: List[Tuple[GroundTruthFault, ExtractedFault, float]] = field(default_factory=list)
    false_negatives: List[GroundTruthFault] = field(default_factory=list)
    false_positives: List[ExtractedFault] = field(default_factory=list)
    partial_matches: List[Tuple[GroundTruthFault, ExtractedFault, float]] = field(default_factory=list)


def parse_ground_truth_summaries(ground_truth_file: str, faults_file: str) -> Dict[int, List[GroundTruthFault]]:
    """
    Parse ground truth shift summaries and their known faults.
    
    Returns a dict mapping shift_log_number to list of GroundTruthFaults.
    """
    # First, parse the faults file to get known faults
    known_faults = {}  # shift_log_number -> list of GroundTruthFault
    
    with open(faults_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            shift_log_number = int(row['ShiftLogNumber'])
            
            fault = GroundTruthFault(
                timestamp=row.get('timestamp', ''),
                description=row.get('description', ''),
                tag=row.get('tag', ''),
                run_number=row.get('run_number', None) if row.get('run_number', '') else None,
                shift_log_number=shift_log_number,
                shift_logbook_url=row.get('ShiftLogbookURL', ''),
                shift_title=row.get('ShiftTitle', ''),
                shift_datetime=row.get('ShiftDateTime', '')
            )
            
            if shift_log_number not in known_faults:
                known_faults[shift_log_number] = []
            known_faults[shift_log_number].append(fault)
    
    return known_faults


def parse_extracted_faults(extracted_file: str) -> List[ExtractedFault]:
    """Parse the extracted faults CSV file."""
    extracted_faults = []
    
    with open(extracted_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            fault = ExtractedFault(
                full_timestamp=row.get('FullTimestamp', ''),
                timestamp=row.get('timestamp', ''),
                description=row.get('description', ''),
                tag=row.get('tag', ''),
                run_number=row.get('run_number', None) if row.get('run_number', '') else None,
                shift_log_number=int(row['ShiftLogNumber']),
                shift_logbook_url=row.get('ShiftLogbookURL', ''),
                shift_title=row.get('ShiftTitle', ''),
                shift_datetime=row.get('ShiftDateTime', ''),
                fragment_link=row.get('FragmentLink', ''),
                verification_status=row.get('verification_status', '')
            )
            extracted_faults.append(fault)
    
    return extracted_faults


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    # Lowercase, remove extra whitespace, punctuation
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text


def calculate_description_similarity(desc1: str, desc2: str) -> float:
    """
    Calculate similarity between two fault descriptions.
    Uses both exact matching and fuzzy matching.
    """
    norm1 = normalize_text(desc1)
    norm2 = normalize_text(desc2)
    
    # Exact match after normalization
    if norm1 == norm2:
        return 1.0
    
    # Partial match using SequenceMatcher
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    
    # Also check for keyword overlap
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    if len(words1) > 0 and len(words2) > 0:
        overlap = len(words1 & words2) / max(len(words1), len(words2))
        # Combine ratio and overlap
        combined = 0.6 * ratio + 0.4 * overlap
        return combined
    
    return ratio


def calculate_run_number_match(gt_run: Optional[str], ext_run: Optional[str]) -> float:
    """Calculate run number match score."""
    if gt_run is None and ext_run is None:
        return 1.0
    if gt_run is None or ext_run is None:
        return 0.5  # Partial credit for missing run number
    
    # Normalize run numbers (remove "Run " prefix if present)
    gt_run = re.sub(r'run\s*', '', str(gt_run), flags=re.IGNORECASE).strip()
    ext_run = re.sub(r'run\s*', '', str(ext_run), flags=re.IGNORECASE).strip()
    
    if gt_run == ext_run:
        return 1.0
    
    # Try to extract just the number
    gt_num = re.search(r'\d+', gt_run)
    ext_num = re.search(r'\d+', ext_run)
    
    if gt_num and ext_num:
        if gt_num.group() == ext_num.group():
            return 0.9  # Small formatting difference
    
    return 0.0


def calculate_tag_match(gt_tag: str, ext_tag: str) -> float:
    """Calculate tag match score."""
    if gt_tag.lower() == ext_tag.lower():
        return 1.0
    
    # Partial match for similar tags
    gt_norm = normalize_text(gt_tag)
    ext_norm = normalize_text(ext_tag)
    
    if gt_norm in ext_norm or ext_norm in gt_norm:
        return 0.7
    
    return 0.0


def match_faults(ground_truth: List[GroundTruthFault], 
                 extracted: List[ExtractedFault],
                 description_threshold: float = 0.7) -> MatchResult:
    """
    Match ground truth faults to extracted faults.
    
    A match occurs when:
    - Same shift log number
    - Description similarity >= threshold
    - Run number matches (if present)
    
    Returns MatchResult with true positives, false negatives, false positives, and partial matches.
    """
    result = MatchResult()
    
    # Track which extracted faults have been matched
    matched_extracted: Set[int] = set()
    
    for gt_fault in ground_truth:
        best_match = None
        best_score = 0.0
        
        for idx, ext_fault in enumerate(extracted):
            # Must be from same shift
            if ext_fault.shift_log_number != gt_fault.shift_log_number:
                continue
            
            # Calculate description similarity
            desc_sim = calculate_description_similarity(gt_fault.description, ext_fault.description)
            
            if desc_sim < description_threshold:
                continue
            
            # Calculate run number match (if applicable)
            run_match = calculate_run_number_match(gt_fault.run_number, ext_fault.run_number)
            
            # Calculate tag match
            tag_match = calculate_tag_match(gt_fault.tag, ext_fault.tag)
            
            # Combined score (description is most important)
            total_score = 0.6 * desc_sim + 0.25 * run_match + 0.15 * tag_match
            
            if total_score > best_score:
                best_score = total_score
                best_match = (idx, ext_fault, total_score)
        
        if best_match is not None:
            idx, ext_fault, score = best_match
            if score >= description_threshold:
                result.true_positives.append((gt_fault, ext_fault, score))
            else:
                result.partial_matches.append((gt_fault, ext_fault, score))
            matched_extracted.add(idx)
        else:
            result.false_negatives.append(gt_fault)
    
    # Any extracted faults not matched are false positives
    for idx, ext_fault in enumerate(extracted):
        if idx not in matched_extracted:
            result.false_positives.append(ext_fault)
    
    return result


def calculate_scores(result: MatchResult, partial_weight: float = 0.5) -> Dict[str, float]:
    """
    Calculate precision, recall, and F1 score.
    
    partial_weight: How much to count partial matches (0.0 = ignore, 1.0 = full credit)
    """
    # True positives: full matches + weighted partial matches
    tp = len(result.true_positives) + partial_weight * len(result.partial_matches)
    
    # False negatives: missed ground truth faults
    fn = len(result.false_negatives)
    
    # False positives: hallucinated faults
    fp = len(result.false_positives)
    
    # Precision: TP / (TP + FP)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    
    # Recall: TP / (TP + FN)
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    # F1: harmonic mean of precision and recall
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'true_positives': len(result.true_positives),
        'partial_matches': len(result.partial_matches),
        'false_negatives': len(result.false_negatives),
        'false_positives': len(result.false_positives),
        'total_ground_truth': len(result.true_positives) + len(result.partial_matches) + len(result.false_negatives),
        'total_extracted': len(result.true_positives) + len(result.partial_matches) + len(result.false_positives)
    }


def generate_report(scores: Dict[str, float], 
                   result: MatchResult,
                   output_file: Optional[str] = None) -> str:
    """Generate a detailed accuracy report."""
    lines = []
    lines.append("=" * 70)
    lines.append("FAULT EXTRACTION PIPELINE ACCURACY REPORT")
    lines.append("=" * 70)
    lines.append("")
    
    lines.append("OVERALL SCORES")
    lines.append("-" * 40)
    lines.append(f"Precision:  {scores['precision']:.4f} ({scores['precision']*100:.2f}%)")
    lines.append(f"Recall:     {scores['recall']:.4f} ({scores['recall']*100:.2f}%)")
    lines.append(f"F1 Score:   {scores['f1']:.4f} ({scores['f1']*100:.2f}%)")
    lines.append("")
    
    lines.append("DETAILED BREAKDOWN")
    lines.append("-" * 40)
    lines.append(f"Total Ground Truth Faults:    {scores['total_ground_truth']}")
    lines.append(f"Total Extracted Faults:       {scores['total_extracted']}")
    lines.append(f"True Positives (full match):  {scores['true_positives']}")
    lines.append(f"Partial Matches:              {scores['partial_matches']}")
    lines.append(f"False Negatives (missed):     {scores['false_negatives']}")
    lines.append(f"False Positives (hallucinated): {scores['false_positives']}")
    lines.append("")
    
    # False negatives details
    if result.false_negatives:
        lines.append("MISSED FAULTS (False Negatives)")
        lines.append("-" * 40)
        for i, fault in enumerate(result.false_negatives, 1):
            lines.append(f"{i}. Shift #{fault.shift_log_number}")
            lines.append(f"   Timestamp: {fault.timestamp}")
            lines.append(f"   Description: {fault.description[:80]}...")
            lines.append(f"   Tag: {fault.tag}")
            if fault.run_number:
                lines.append(f"   Run: {fault.run_number}")
            lines.append("")
    
    # False positives details
    if result.false_positives:
        lines.append("HALLUCINATED FAULTS (False Positives)")
        lines.append("-" * 40)
        for i, fault in enumerate(result.false_positives, 1):
            lines.append(f"{i}. Shift #{fault.shift_log_number}")
            lines.append(f"   Timestamp: {fault.timestamp}")
            lines.append(f"   Description: {fault.description[:80]}...")
            lines.append(f"   Tag: {fault.tag}")
            if fault.run_number:
                lines.append(f"   Run: {fault.run_number}")
            lines.append("")
    
    # Partial matches details
    if result.partial_matches:
        lines.append("PARTIAL MATCHES")
        lines.append("-" * 40)
        for i, (gt, ext, score) in enumerate(result.partial_matches, 1):
            lines.append(f"{i}. Shift #{gt.shift_log_number} (match score: {score:.2f})")
            lines.append(f"   Ground Truth:  {gt.description[:60]}...")
            lines.append(f"   Extracted:     {ext.description[:60]}...")
            lines.append(f"   GT Run: {gt.run_number}, Ext Run: {ext.run_number}")
            lines.append(f"   GT Tag: {gt.tag}, Ext Tag: {ext.tag}")
            lines.append("")
    
    lines.append("=" * 70)
    
    report = "\n".join(lines)
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report saved to: {output_file}")
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate fault extraction pipeline accuracy'
    )
    parser.add_argument(
        '--ground-truth', '-g',
        required=True,
        help='Path to ground truth shift summaries CSV'
    )
    parser.add_argument(
        '--faults', '-f',
        required=True,
        help='Path to ground truth faults CSV (companion to ground-truth file)'
    )
    parser.add_argument(
        '--extracted', '-e',
        required=True,
        help='Path to extracted faults CSV from pipeline'
    )
    parser.add_argument(
        '--output', '-o',
        help='Path to save detailed report (optional)'
    )
    parser.add_argument(
        '--description-threshold', '-t',
        type=float,
        default=0.7,
        help='Similarity threshold for description matching (default: 0.7)'
    )
    parser.add_argument(
        '--partial-weight', '-p',
        type=float,
        default=0.5,
        help='Weight for partial matches in scoring (default: 0.5)'
    )
    
    args = parser.parse_args()
    
    # Validate input files exist
    if not os.path.exists(args.ground_truth):
        print(f"Error: Ground truth file not found: {args.ground_truth}")
        return 1
    
    if not os.path.exists(args.faults):
        print(f"Error: Ground truth faults file not found: {args.faults}")
        return 1
    
    if not os.path.exists(args.extracted):
        print(f"Error: Extracted faults file not found: {args.extracted}")
        return 1
    
    print("Loading ground truth data...")
    ground_truth_by_shift = parse_ground_truth_summaries(args.ground_truth, args.faults)
    
    print("Loading extracted faults...")
    extracted_faults = parse_extracted_faults(args.extracted)
    
    # Aggregate all ground truth faults
    all_ground_truth = []
    for shift_num, faults in ground_truth_by_shift.items():
        all_ground_truth.extend(faults)
    
    print(f"Found {len(all_ground_truth)} ground truth faults across {len(ground_truth_by_shift)} shifts")
    print(f"Found {len(extracted_faults)} extracted faults")
    
    print("\nMatching faults...")
    result = match_faults(all_ground_truth, extracted_faults, args.description_threshold)
    
    print("Calculating scores...")
    scores = calculate_scores(result, args.partial_weight)
    
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Precision:  {scores['precision']:.4f} ({scores['precision']*100:.2f}%)")
    print(f"Recall:     {scores['recall']:.4f} ({scores['recall']*100:.2f}%)")
    print(f"F1 Score:   {scores['f1']:.4f} ({scores['f1']*100:.2f}%)")
    print("=" * 70)
    print(f"\nTrue Positives:  {scores['true_positives']}")
    print(f"Partial Matches: {scores['partial_matches']}")
    print(f"False Negatives: {scores['false_negatives']} (missed faults)")
    print(f"False Positives: {scores['false_positives']} (hallucinated faults)")
    
    # Generate detailed report
    report = generate_report(scores, result, args.output)
    
    # Also save JSON results for programmatic access
    if args.output:
        json_output = args.output.rsplit('.', 1)[0] + '.json'
        with open(json_output, 'w', encoding='utf-8') as f:
            json.dump({
                'scores': scores,
                'summary': {
                    'precision': scores['precision'],
                    'recall': scores['recall'],
                    'f1': scores['f1'],
                    'true_positives': scores['true_positives'],
                    'partial_matches': scores['partial_matches'],
                    'false_negatives': scores['false_negatives'],
                    'false_positives': scores['false_positives']
                }
            }, f, indent=2)
        print(f"\nJSON results saved to: {json_output}")
    
    return 0


if __name__ == '__main__':
    exit(main())
