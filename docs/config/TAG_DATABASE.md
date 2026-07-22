# Tag Database Reference

Complete reference for all fault categories in CLAW-Agent.

---

## Overview

The tag database contains 16 fault categories used for semantic classification. Each category has a name, keywords, and description.

**Location**: `tag_db/tags.json`

---

## Tag Categories

### 1. Accelerator
- **Keywords**: accelerator, rf, beam, klystron, cavity, linac, injector, cebaf, srf, superconducting, arc, lerf, beamline, trim card, box supply
- **Description**: Issues related to CEBAF or LERF accelerator systems, SRF cavities, RF zones, and linac components.

### 2. Injector / Source
- **Keywords**: injector, electron source, polarized source, photocathode, gun, drive laser, gun high voltage
- **Description**: Issues with polarized electron source and injector.

### 3. Beam Diagnostics
- **Keywords**: bpm, bcm, harp, superharp, wire scanner, viewer, unser monitor, beam position, beam current, profile monitor
- **Description**: Faults in beam instrumentation (BPMs, BCMs, harps, viewers).

### 4. Halls
- **Keywords**: detector, calorimeter, spectrometer, halls, hall a, hall b, hall c, hall d, clas12, gluex, shms, hms, bigbite
- **Description**: Experimental detectors and hall-specific subsystems.

### 5. Cryogenics
- **Keywords**: cryo, cryogenic, helium, nitrogen, cold, temperature, cooling, chiller, chl, esr, hdr, cryomodule
- **Description**: Cryogenic system issues (CHL, ESR, HDR).

### 6. Vacuum
- **Keywords**: vacuum, pressure, leak, pump, ion pump, turbo, valve, vgc, cold cathode
- **Description**: Vacuum system problems (leaks, pumps, valves).

### 7. Magnets
- **Keywords**: power supply, quadrupole, dipole, corrector, steering magnet, trip
- **Description**: Magnet systems and power supplies.

### 8. Targets
- **Keywords**: target, cryotarget, polarized target, liquid hydrogen, lh2, ld2
- **Description**: Experimental target issues.

### 9. EPICS
- **Keywords**: epics, ioc, medm, edm, phoebus, css, striptool, mya, archiver
- **Description**: EPICS control system issues.

### 10. Power
- **Keywords**: power, voltage, current, trip, breaker, fuse, electrical, psu
- **Description**: Electrical power issues.

### 11. Safety
- **Keywords**: safety, alarm, alarm trip, interlock, esh, pss, mps, odh
- **Description**: Safety system issues (PSS, MPS, ODH).

### 12. Radiation Control (RadCon)
- **Keywords**: radcon, radiation, dosimetry, radiation monitor, beam loss, activation
- **Description**: Radiation control and monitoring.

### 13. Network
- **Keywords**: network, ethernet, connection, timeout, latency, switch, router, cc, scicomp
- **Description**: Network connectivity and DAQ networking.

### 14. CODA
- **Keywords**: software, crash, error, bug, coda, roc, eb, ts, rol, evio, trigger
- **Description**: Software bugs and CODA system anomalies.

### 15. Mechanical
- **Keywords**: mechanical, motor, pump, valve, actuator, lcw, low conductivity water, hvac
- **Description**: Mechanical infrastructure and LCW systems.

### 16. MCC
- **Keywords**: mcc, machine control, control room, crew chief, operator, ops, bteam
- **Description**: Machine Control Center operations.

---

## Adding New Tags

### Edit tags.json

```json
[
  ...
  {
    "name": "New Category",
    "keywords": ["keyword1", "keyword2"],
    "description": "Detailed description"
  }
]
```

### Rebuild ChromaDB

```bash
# Delete old embeddings
rm -rf tag_db/chroma_db

# Run pipeline - will auto-rebuild
./scripts/run_pipeline.sh
```

---

## Usage Examples

### List All Tags

```python
from src.analysis.tag_extraction import load_tag_database

tags = load_tag_database()
for tag in tags:
    print(f"{tag['name']}: {tag['keywords'][:3]}...")
```

### Search Tags by Keyword

```python
def find_tags_by_keyword(keyword: str):
    tags = load_tag_database()
    matches = []
    
    for tag in tags:
        if any(keyword.lower() in k.lower() for k in tag['keywords']):
            matches.append(tag['name'])
    
    return matches

print(find_tags_by_keyword("rf"))
# Output: ['Accelerator']
```

---

## Related Documentation

- [Tagging Pipeline](./PIPELINE_TAGGING.md) - Tag classification process
- [Dashboard](./DASHBOARD.md) - Tag visualization

---

*For tagging implementation, see [PIPELINE_TAGGING.md](./PIPELINE_TAGGING.md).*