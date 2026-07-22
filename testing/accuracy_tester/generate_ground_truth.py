#!/usr/bin/env python3
"""
Generate ground truth faults files from mock summaries generator.

This script extracts the known faults from the mock_summaries generator
and creates properly formatted ground truth files for accuracy testing.
"""

import csv
import os
import re
import argparse
from datetime import datetime
from typing import List, Dict, Tuple


# Fault templates by difficulty - extracted from generate_summaries.py
EASY_FAULTS = [
    "16:05 Run 24501 started but DAQ crashed immediately after startup.",
    "16:20 Run 24502 ended prematurely due to event rate dropping to zero.",
    "16:35 GEM HV trip detected on crate 2, expert reboot required.",
    "16:50 Beam trip occurred lasting 8 minutes due to MCC injector issue.",
    "17:05 Minor beam fluctuation caused 5 minute data collection pause.",
    "17:20 Run 24503 had corrupted event headers requiring restart.",
    "17:35 Halo counter tripped without beam, required system reset.",
    "17:50 Target position jitter detected causing beam alignment issues.",
    "18:05 GEM clustering failed on 30% of events in run 24504.",
    "18:20 Veto scintillator rate anomaly detected, calibration needed.",
    "18:35 Run 24505 lost 15% live time due to DAQ buffer overflow.",
    "18:50 BPM reading spiked unexpectedly, MCC notified for check.",
    "19:05 Halo counter noise increased, HV adjustment in progress.",
    "19:20 Run 24506 had timing sync issue between GEM and hycal.",
    "19:35 Collimator position drifted during run, required repositioning.",
    "19:50 GEM2 ROC reported high error count, crate monitoring enabled.",
    "20:05 Beam current unstable, fluctuating between 45-55 nA.",
    "20:20 Run 24507 terminated early due to trigger rate anomaly.",
    "20:35 FADC channel 12 showing saturation, hardware check needed.",
    "20:50 Target gas pressure dropped below threshold, refill required.",
]

EASY_NORMAL = [
    "16:00 Shift started, beam delivered at 50 nA on H2 target.",
    "16:10 Run 24501 data collection proceeding normally.",
    "16:40 Beam stable, increasing current to 80 nA.",
    "17:10 Run 24503 completed successfully after 45 minutes.",
    "17:25 Beam returned, resuming data collection.",
    "17:45 Target moved to position B for next run configuration.",
    "18:00 Run 24504 started with stable beam current.",
    "18:15 Data quality plots look good, continuing run.",
    "18:30 Beam current ramped to 100 nA successfully.",
    "18:45 Shift check completed, all systems nominal.",
    "19:00 Run 24508 started after successful configuration change.",
    "19:15 Event rate stable at expected 5kHz level.",
    "19:30 Live time holding at 98%, no issues detected.",
    "19:45 Beam profile looks clean, no tail observed.",
    "20:00 Target position verified, all limits within range.",
    "20:15 GEM gain stable, HV settings confirmed.",
    "20:30 Run 24509 completed with full data quality.",
    "20:45 Beam current increased to 120 nA without issues.",
    "21:00 Data transfer to storage completed successfully.",
    "21:15 Shift handover notes prepared, all systems nominal.",
    "21:30 Run 24510 started with nominal beam parameters.",
    "21:45 Veto counters calibrated, rates within expected range.",
    "22:00 Halo counter readings stable, no anomalies detected.",
    "22:15 Run 24511 completed, data integrity verified.",
    "22:30 Beam optics tuned, profile optimization successful.",
    "22:45 Target gas pressure stable, cell operating normally.",
    "23:00 GEM clustering efficiency at 99%, no issues.",
    "23:15 Run 24512 started, all detectors responding correctly.",
    "23:30 Event monitoring plots displaying correctly.",
    "23:45 Shift end approaching, all runs completed successfully.",
]

MEDIUM_FAULTS = [
    "16:00 DAQ unresponsive for 15 minutes, full system reboot required.",
    "16:25 Event rate dropped to zero, MCC beam tuning needed for 20 minutes.",
    "16:50 Target position stuck at C, expert remote rehome took 25 minutes.",
    "17:15 GEM crate communication lost, MPD reboot and crate reset required.",
    "17:40 Beam halo increased 300%, MCC optics adjustment took 30 minutes.",
    "18:05 Trigger latency errors on hycal4-7, all crates needed reboot.",
    "18:25 IOC communication lost, LabView restart and reconnection required.",
    "18:45 FADC settings not loading correctly, config file update needed.",
    "19:05 BPM fluctuations worsening, injector stability issue reported.",
    "19:25 ADCHYCAL ROC high counts detected (~99), ROC reboot required.",
    "19:45 Run 24608 lost synchronization, full DAQ restart needed.",
    "20:05 Target cell pressure sensor malfunction, manual check required.",
    "20:25 GEM2 MPD0 disconnected during run, hot-swap replacement needed.",
    "20:45 Beam orbit drift exceeded tolerance, MCC correction in progress.",
    "21:05 Veto scintillator gain drifted, recalibration taking 40 minutes.",
    "21:25 hycal trigger threshold unstable, firmware reload required.",
    "21:45 ADCHYCAL5 clock skew detected, crate reinitialization needed.",
    "22:05 Run 24609 terminated due to multiple ROC errors simultaneously.",
    "22:25 Separator magnet power supply fluctuating, engineering notified.",
    "22:45 LabView crashed during data transfer, manual recovery needed.",
]

MEDIUM_NORMAL = [
    "16:00 Shift handover completed, run 24601 in progress at 80 nA.",
    "16:30 Beam tuning completed, rate stabilized at expected levels.",
    "17:00 Target successfully moved to OUT position.",
    "17:30 Expert arrived, began diagnostics on target mechanism.",
    "17:50 Beam returned after tuning, resuming data taking.",
    "18:15 Crate reboot completed, communication restored.",
    "18:35 Optics adjustment successful, beam profile improved.",
    "18:55 IOC reconnected, control systems back online.",
    "19:15 Config file update applied, FADC loading correctly.",
    "19:35 Injector stability restored, BPM readings normal.",
    "19:55 Run 24610 started after successful system recovery.",
    "20:15 Data quality monitoring showing nominal performance.",
    "20:35 Target pressure stabilized, cell operating normally.",
    "20:55 GEM gain recalibrated, all channels within spec.",
    "21:15 Beam orbit corrected, position within tolerance.",
    "21:35 Veto gain calibration completed successfully.",
    "21:55 hycal trigger threshold set and verified.",
    "22:15 ADCHYCAL clock sync restored, no further skew.",
    "22:35 Run 24611 completed with full data integrity.",
    "22:55 Separator magnet stabilized, power supply nominal.",
    "23:10 Run 24612 started after successful diagnostics.",
    "23:25 Event rate stable at 8kHz, no fluctuations.",
    "23:40 Live time holding at 97%, all systems green.",
    "23:55 Target position confirmed, no drift detected.",
    "00:10 GEM HV stable, no trips during run.",
    "00:25 Beam current at 150 nA, ramping smoothly.",
    "00:40 Data acquisition rate nominal, buffer levels OK.",
    "00:55 Run 24613 completed, quality checks passed.",
    "01:10 Halo counter rates within expected range.",
    "01:25 Shift end preparation, all logs updated.",
]

HARD_FAULTS = [
    "16:00 Live time dropped to 2%, run terminated with insufficient data.",
    "16:20 GEM Vpt1 throwing continuous errors, crate reboot failed to fix.",
    "16:40 Event monitoring reference plots missing from display system.",
    "17:00 Beam trip due to injector instability, 35 minutes without beam.",
    "17:25 Beam drift detected, BPM fluctuations increasing continuously.",
    "17:50 Trigger rate fluctuating wildly, possible beam scraping target foil.",
    "18:10 Multiple detector rates elevated simultaneously, alignment suspected.",
    "18:30 Upstream halo counters showing non-zero rates with no beam present.",
    "18:50 DSC scalers below 80% after GEM reboot, unresolved hardware issue.",
    "19:10 Target cell alignment investigation required, expert consultation needed.",
    "19:30 Run 24711 crashed due to memory leak in DAQ software.",
    "19:50 GEM1 crate temperature exceeded limit, cooling system failure.",
    "20:10 Beam loss monitor triggered falsely, safety system lockdown.",
    "20:30 Target rotation mechanism seized, manual intervention required.",
    "20:50 Multiple ROCs reporting CRC errors, network switch suspected.",
    "21:10 Veto coincidence peak disappeared, electronics malfunction.",
    "21:30 hycal energy calibration drifted 15%, full recalibration needed.",
    "21:50 Beam profile shows double peak, separator field instability.",
    "22:10 ADCHYCAL firmware hang, cold reboot of entire system required.",
    "22:30 Run 24712 lost 45 minutes to cascading system failures.",
]

HARD_NORMAL = [
    "16:00 Owl shift takeover, run 24701 ongoing with nominal parameters.",
    "16:15 Attempting run restart after live time issue.",
    "16:35 GEM expert contacted for Vpt1 error diagnosis.",
    "16:55 IT notified about missing event monitoring plots.",
    "17:15 MCC working on injector, no beam currently.",
    "17:40 Beam returned, attempting to stabilize position.",
    "18:05 Trigger system under investigation, rate unstable.",
    "18:25 Detector experts called to assess elevated rates.",
    "18:45 Halo counter investigation started, cause unknown.",
    "19:05 Hardware team assembling to address DSC scaler issue.",
    "19:25 DAQ software restart initiated, memory cleared.",
    "19:45 Cooling system repaired, GEM temperature normalizing.",
    "20:05 Beam loss monitor reset, safety system cleared.",
    "20:25 Target mechanism manually freed, rotation restored.",
    "20:45 Network switch replaced, CRC errors resolved.",
    "21:05 Veto electronics replaced, coincidence peak restored.",
    "21:25 hycal recalibration completed, energy scale corrected.",
    "21:45 Separator field stabilized, beam profile normalized.",
    "22:05 ADCHYCAL system rebooted, all crates online.",
    "22:25 Run 24713 started after full system recovery.",
    "22:40 Event rate stabilizing at 12kHz, no drops.",
    "22:55 Live time recovering, now at 85% and climbing.",
    "23:10 GEM1 temperature back to nominal 22C.",
    "23:25 Target rotation operating smoothly, no binding.",
    "23:40 Network connectivity verified, no packet loss.",
    "23:55 Veto gain recalibrated, peak at expected channel.",
    "00:10 hycal energy resolution within spec, 3.2% at 1GeV.",
    "00:25 Beam orbit locked, BPM readings stable.",
    "00:40 ADCHYCAL firmware loaded successfully, no hangs.",
    "00:55 Run 24714 completed with full data quality.",
]


def remove_run_numbers(text: str) -> str:
    """
    Remove run numbers from text for comparison.
    The mock generator modifies run numbers (e.g., 24501 -> 245001, 245011, etc.)
    so we need to normalize them for matching.
    """
    # Remove patterns like "Run 245001", "Run 245011", "run 245004", etc.
    # Also handles "run 24504" (without extra digits)
    text = re.sub(r'run\s+24\d{3,}', 'run XXX', text, flags=re.IGNORECASE)
    # Also handle "in run 24504" pattern
    text = re.sub(r'in run\s+24\d{3,}', 'in run XXX', text, flags=re.IGNORECASE)
    return text


def extract_fault_info(description: str) -> Tuple[str, str, str, str]:
    """
    Extract timestamp, run number, tag, and normalized description from fault text.
    
    Returns: (timestamp, run_number, tag, description)
    """
    # Extract timestamp (format: HH:MM at start)
    timestamp_match = re.match(r'^(\d{2}:\d{2})', description)
    timestamp = timestamp_match.group(1) if timestamp_match else ""
    
    # Extract run number
    run_match = re.search(r'Run\s+(\d+)', description, re.IGNORECASE)
    run_number = f"Run {run_match.group(1)}" if run_match else None
    
    # Determine tag based on keywords
    desc_lower = description.lower()
    if any(word in desc_lower for word in ['daq', 'trigger', 'event', 'run']):
        tag = "DAQ"
    elif any(word in desc_lower for word in ['beam', 'mcc', 'injector', 'orbit']):
        tag = "Beam"
    elif any(word in desc_lower for word in ['gem', 'hv', 'crate', 'roc', 'mpd']):
        tag = "GEM"
    elif any(word in desc_lower for word in ['target', 'position', 'cell']):
        tag = "Target"
    elif any(word in desc_lower for word in ['hycal', 'adchycal', 'calibration']):
        tag = "Calorimeter"
    elif any(word in desc_lower for word in ['veto', 'halo', 'counter']):
        tag = "Detectors"
    elif any(word in desc_lower for word in ['fadc', 'timing', 'clock']):
        tag = "Electronics"
    else:
        tag = "Other"
    
    # Use original description
    full_description = description
    
    return timestamp, run_number, tag, full_description


def generate_ground_truth_faults(summary_file: str, output_file: str, fault_type: str):
    """
    Generate ground truth faults file from a mock summaries CSV.
    
    The fault_type indicates which pool was used (easy, medium, hard).
    """
    # Load the appropriate fault pool
    if fault_type == 'easy':
        fault_pool = EASY_FAULTS
    elif fault_type == 'medium':
        fault_pool = MEDIUM_FAULTS
    else:
        fault_pool = HARD_FAULTS
    
    # Normalize fault pool for matching
    normalized_faults = {f.lower().strip(): f for f in fault_pool}
    
    faults = []
    
    with open(summary_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            log_number = int(row['LogNumber'])
            logbook_url = row['LogbookURL']
            title = row['Title']
            datetime_str = row['DateTime']
            
            # Parse content to find faults
            content = row['Content']
            entries = content.strip().split('\n')
            
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                
                # Check if this entry is a fault (matches any fault template)
                # Note: Run numbers may be modified in the actual data, so we match
                # by removing run numbers from both strings before comparing
                entry_normalized = remove_run_numbers(entry.lower())
                
                for normalized_template, original_template in normalized_faults.items():
                    template_normalized = remove_run_numbers(normalized_template)
                    
                    if entry_normalized == template_normalized:
                        # This is a fault!
                        timestamp, run_number, tag, description = extract_fault_info(entry)
                        
                        # Create full timestamp
                        date_part = datetime_str.split(' ')[0]
                        full_timestamp = f"{date_part} {timestamp}:00"
                        
                        fault = {
                            'FullTimestamp': full_timestamp,
                            'timestamp': timestamp,
                            'description': description,
                            'tag': tag,
                            'run_number': run_number if run_number else '',
                            'ShiftLogNumber': log_number,
                            'ShiftLogbookURL': logbook_url,
                            'ShiftTitle': title,
                            'ShiftDateTime': datetime_str,
                            'FragmentLink': f"#entry-{log_number}",
                            'verification_status': 'confirmed'
                        }
                        faults.append(fault)
                        break
    
    # Write output file
    fieldnames = ['FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
                  'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime',
                  'FragmentLink', 'verification_status']
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(faults)
    
    return len(faults)


def main():
    parser = argparse.ArgumentParser(
        description='Generate ground truth faults files from mock summaries'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to mock summaries CSV file'
    )
    parser.add_argument(
        '--output', '-o',
        help='Path to output ground truth faults file (default: <input>_faults.csv)'
    )
    parser.add_argument(
        '--type', '-t',
        choices=['easy', 'medium', 'hard'],
        required=True,
        help='Fault difficulty type used in the summaries'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    if args.output is None:
        base = os.path.splitext(args.input)[0]
        args.output = f"{base}_faults.csv"
    
    print(f"Processing {args.input}...")
    count = generate_ground_truth_faults(args.input, args.output, args.type)
    
    print(f"Generated {count} ground truth faults")
    print(f"Output saved to: {args.output}")
    
    return 0


if __name__ == '__main__':
    exit(main())
