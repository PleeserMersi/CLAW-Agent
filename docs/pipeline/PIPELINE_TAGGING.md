# Tag Classification Pipeline

Detailed documentation for the semantic tagging stage of CLAW-Agent.

---

## Overview

The tagging stage classifies extracted faults into 16 predefined categories using ChromaDB vector search for semantic similarity and LLM-based final classification.

**Module**: `src/analysis/tag_extraction.py`

**Input**: Faults DataFrame with descriptions (from extraction stage)

**Output**: Faults DataFrame with assigned tags

---

## Tag Categories

CLAW-Agent uses 16 fault categories, each with keywords and descriptions:

### 1. Accelerator
**Keywords**: accelerator, rf, beam, klystron, cavity, linac, injector, cebaf, srf, superconducting, arc, lerf, beamline, trim card, box supply

**Description**: Issues related to CEBAF or LERF accelerator systems, SRF cavities, RF zones, and linac components.

### 2. Injector / Source
**Keywords**: injector, electron source, polarized source, photocathode, gun, drive laser, gun high voltage

**Description**: Issues with polarized electron source and injector, including photocathode, drive laser, and electron gun HV systems.

### 3. Beam Diagnostics
**Keywords**: bpm, bcm, harp, superharp, wire scanner, viewer, unser monitor, beam position, beam current, profile monitor

**Description**: Faults in beam instrumentation for measurement and tuning (BPMs, BCMs, harps, viewers, Unser monitors).

### 4. Halls
**Keywords**: detector, calorimeter, spectrometer, halls, hall a, hall b, hall c, hall d, focal plane, clas12, gluex, shms, hms, bigbite, superbigbite, cherenkov, drift chamber

**Description**: Problems with experimental detectors and hall-specific subsystems (CLAS12, GlueX, HMS/SHMS, BigBite).

### 5. Cryogenics
**Keywords**: cryo, cryogenic, helium, nitrogen, cold, temperature, cooling, chiller, chl, chl1, chl2, esr, hdr, cryomodule, 4k, 2k

**Description**: Cryogenic system issues (CHL1/CHL2, ESR, HDR, cryomodule cooling, 2K/4K regulation).

### 6. Vacuum
**Keywords**: vacuum, pressure, leak, pump, ion pump, turbo, valve, vgc, cold cathode, roughing pump, beamline vacuum

**Description**: Vacuum system problems (UHV leaks, ion pumps, turbo pumps, gauge/valve failures).

### 7. Magnets
**Keywords**: power supply, quadrupole, dipole, corrector, steering magnet, trip

**Description**: Magnet system faults (dipoles, quadrupoles, correctors) or power supply issues.

### 8. Targets
**Keywords**: target, cryotarget, polarized target, liquid hydrogen, lh2, ld2, scattering chamber, target ladder

**Description**: Experimental target issues (cryogenic targets, polarized targets, cell health).

### 9. EPICS
**Keywords**: epics, ioc, medm, edm, phoebus, css, striptool, mya, archiver, scada, softioc

**Description**: EPICS control system issues (IOC crashes, GUI errors, MYA archiver gaps).

### 10. Power
**Keywords**: power, voltage, current, trip, breaker, fuse, electrical, psu, power supply

**Description**: Electrical power issues (voltage/current trips, main supplies, breakers).

### 11. Safety
**Keywords**: safety, alarm, alarm trip, interlock, esh, pss, mps, odh, controlled access, access control

**Description**: Safety system issues (PSS, MPS, ODH monitoring/alarms).

### 12. Radiation Control (RadCon)
**Keywords**: radcon, radiation, dosimetry, radiation monitor, beam loss, activation, survey

**Description**: Radiation control issues (area monitoring, dosimetry, beam-loss activation).

### 13. Network
**Keywords**: network, ethernet, connection, timeout, latency, bandwidth, switch, router, cc, scicomp, halog

**Description**: Network connectivity, DAQ networking, Computer Center resources, EL access.

### 14. CODA
**Keywords**: software, crash, error, bug, glitch, program, application, process, coda, roc, eb, ts, rol, evio, trigger, trigger supervisor

**Description**: Software bugs, online computing, CODA system anomalies (ROC, EB, TS, ROL).

### 15. Mechanical
**Keywords**: mechanical, motor, pump, valve, actuator, motorized, positioner, lcw, low conductivity water, hvac, valve box

**Description**: Mechanical infrastructure, motorized positioning, valves, LCW cooling loops.

### 16. MCC
**Keywords**: mcc, machine control, control room, crew chief, operator, ops, bteam, program deputy

**Description**: Machine Control Center operations, shift handovers, operational coordination.

---

## Tagging Architecture

### Two-Stage Process

```
Fault Description
       │
       ▼
┌─────────────────────┐
│ ChromaDB Search     │
│ (Semantic Similarity)
│ Top 5 candidates    │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ LLM Classification  │
│ (Select 1 from 5)   │
└─────────────────────┘
       │
       ▼
Assigned Tag
```

### Why Two Stages?

**ChromaDB**:
- Fast semantic search against 16 tag embeddings
- Reduces LLM prompt size by pre-filtering
- Uses sentence-transformers for embeddings

**LLM**:
- Makes final decision from top candidates
- Handles edge cases and ambiguity
- Returns exact tag name or "Other"

---

## ChromaDB Implementation

### Vector Database Setup

**Location**: `tag_db/chroma_db/`

**Collection Name**: `fault_tags`

**Persistence**: Data persists across runs

**Initialization**:
```python
def get_or_create_chroma_client() -> chromadb.ClientAPI:
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    return client
```

### Tag Embedding

**Document Construction**:
```python
for tag_info in tags:
    tag_name = tag_info['name']
    keywords = tag_info['keywords']
    description = tag_info['description']
    
    # Combine for rich embedding
    doc_text = f"{tag_name}: {' '.join(keywords)} {description}"
    
    # Example: "Accelerator: accelerator rf beam klystron cavity... 
    #          Issues related to CEBAF or LERF accelerator systems..."
```

**Embedding Model**: ChromaDB default (typically sentence-transformers/all-MiniLM-L6-v2)

**Embedding Dimension**: 384 dimensions

### Collection Management

**Check if Empty**:
```python
collection = client.get_or_create_collection(name="fault_tags")

if collection.count() == 0:
    # Initialize with tag embeddings
    ensure_tag_collection(client, tags)
```

**Add Tags**:
```python
collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids  # MD5 hash of tag name
)
```

---

## Semantic Search

### Query Process

**Function**: `get_candidate_tags(description, top_k=5)`

```python
def get_candidate_tags(description: str, top_k: int = 5) -> List[str]:
    # Load tags
    tags = load_tag_database()
    
    # Get ChromaDB client
    client = get_or_create_chroma_client()
    collection = ensure_tag_collection(client, tags)
    
    # Query for similar tags
    results = collection.query(
        query_texts=[description],
        n_results=min(top_k, collection.count()),
        include=["metadatas", "distances"]
    )
    
    # Extract tag names from metadata
    candidates = [meta['tag_name'] for meta in results['metadatas'][0]]
    
    return candidates if candidates else ["Other"]
```

### Example Query

**Input**:
```
description = "RF cavity trip caused beam loss"
```

**ChromaDB Returns** (top 5 candidates):
- Accelerator
- Beam Diagnostics  
- Power
- Safety
- Vacuum

**LLM Prompt**:
```
Fault description: RF cavity trip caused beam loss
Candidate tags: Accelerator, Beam Diagnostics, Power, Safety, Vacuum
```

**LLM Response**: `Accelerator` (or "Other" if none fit)

---

## LLM Classification

### Prompt Template

```
You are classifying a fault from a Jefferson Lab shift summary log.

You have been given a fault description and a list of candidate tags retrieved from a knowledge base.
Choose the single most appropriate tag for this fault.
If none of the candidates clearly fit, respond with: Other

Fault description: {description}

Candidate tags: {tag_options}

Respond with only the tag name, exactly as written above. No explanation.
```

### Batch Processing

**Batch Size**: Configurable via `--batch-size` parameter

**Batch Processing Flow**:
1. Pre-compute candidates for all faults (vector search)
2. Group faults into batches of size N
3. For each batch, collect unique candidates across all faults
4. Send single LLM call with all faults and their candidates
5. Parse JSON response with index/tag pairs

**Batch Prompt Format**:
```
Candidate tags: [all unique tags from batch]

Faults:
--- FAULT 0 (original row 123) ---
Description: RF cavity trip caused beam loss
Candidates: Accelerator, Beam Diagnostics, Power

--- FAULT 1 (original row 124) ---
Description: Vacuum leak in sector 2
Candidates: Vacuum, Mechanical, Power
...
```

**Expected Response**:
```json
[
  {"index": 0, "tag": "Accelerator"},
  {"index": 1, "tag": "Vacuum"}
]
```

**Note**: Local indices (0, 1, 2...) map to original DataFrame row indices for correct placement.

---

## Batch Implementation

### Batch Processing Implementation

**Key Steps**:
1. **Pre-compute candidates**: Vector search run once per fault (fast, not parallelized)
2. **Filter**: Only faults with >1 candidate need LLM classification
3. **Batch**: Group filtered faults into batches of size N
4. **Parallel**: Process batches with ThreadPoolExecutor
5. **Map results**: Use local index → original row index mapping

**Batch Data Format**:
```python
# Each batch item: (local_idx, original_row_idx, description, candidates)
batch_data = [
    (0, 123, "RF cavity trip", ["Accelerator", "Beam Diagnostics", "Power"]),
    (1, 124, "Vacuum leak", ["Vacuum", "Mechanical"]),
    ...
]
```

**Parallel Execution**:
```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {
        executor.submit(classify_faults_batch, batch_data, agent): batch_idx
        for batch_idx, batch_data in enumerate(batches)
    }
    
    for future in as_completed(futures):
        results = future.result()
        # results: [(orig_idx, tag), ...]
        for orig_idx, selected_tag in results:
            faults_df.at[orig_idx, 'tag'] = selected_tag
```

---

## Output Schema

### Added Column

**`tag`**: Assigned tag name (string)

**Example**:
```python
faults_df['tag'] = faults_df.apply(
    lambda row: classify_fault(row['description']),
    axis=1
)
```

### Complete Output

The `tag` column is added to the input DataFrame:

| Column | Type | Description |
|--------|------|-------------|
| All input columns | - | Preserved from input |
| `tag` | str | Assigned tag name or "Other" |

**Default Value**: If no classification occurs, tag remains as-is (typically "Other")

---

## Edge Cases

### "Other" Tag

**When Used**:
- ChromaDB returns no candidates (empty collection, search failure)
- LLM determines none of the candidates fit
- Fault is too ambiguous for confident classification
- Single candidate exists but LLM rejects it

**Implementation**:
```python
# If no candidates from ChromaDB
if not candidates:
    return ["Other"]

# LLM can respond "Other" even with candidates
# If LLM response not in candidates, return "Other"
if selected_tag not in candidates:
    return "Other"
```

### Single Tag Selection

**Resolution**: LLM must choose exactly one tag

**Prompt Guidance**:
```
Choose the single most appropriate tag for this fault.
If none of the candidates clearly fit, respond with: Other
```

**Note**: Even if multiple tags seem valid, the LLM selects the best match.

### Fallback Mechanisms

**Keyword Matching**: If ChromaDB search fails, fallback to keyword-based matching:

```python
def get_candidate_tags_keyword(description: str, top_k: int = 5) -> List[str]:
    # Match keywords from tag definitions against description
    # Score by number of matching keywords
    # Return top-k by score, or ["Other"] if no matches
```

**Causes for fallback**:
- ChromaDB collection empty/not initialized
- Vector search exception
- No results returned

---

## Performance

### Time Complexity

**Per Fault**:
- ChromaDB search: O(log n) where n = 16 tags
- LLM call: O(1) (constant for fixed candidates)

**Batched**: O(m/b) LLM calls where m = faults, b = batch size

**Parallel**: O(m/(b*w)) with w workers

### Typical Latencies

### Performance Characteristics

**Pre-computation Phase**:
- ChromaDB search: O(log n) where n = 16 tags (very fast)
- Runs once per fault, not parallelized
- Typically <10ms per fault

**LLM Classification Phase**:
- Batched: O(m/b) LLM calls where m = faults, b = batch_size
- Parallel: O(m/(b*w)) with w workers
- Dominates total runtime

**Typical Performance**:
- 100 faults, batch_size=10, workers=4: ~5-15 seconds
- 1000 faults, batch_size=10, workers=4: ~50-150 seconds

**Token Usage (approximate)**:
- Per fault: ~150-250 input tokens, ~5 output tokens
- Per batch (10 faults): ~1500-2500 input tokens, ~50 output tokens
- Depends on candidate list size and fault descriptions

---

## Quality Assurance

### Tag Distribution

**Note**: Actual tag distribution depends on input data. No expected percentages are guaranteed.

**Validation**:
```python
def validate_tag_distribution(df):
    tag_counts = df['tag'].value_counts()
    
    # Check for unexpected tags
    valid_tags = [tag['name'] for tag in load_tag_database()]
    valid_tags.append("Other")
    
    for tag in tag_counts.index:
        assert tag in valid_tags, f"Invalid tag: {tag}"
```

### Accuracy Checks

**Manual Review Process**:
1. Sample 50-100 tagged faults
2. Compare assigned tags against fault descriptions
3. Calculate accuracy rate
4. Identify systematic errors

**Improvement Strategies**:
- Update tag descriptions in `tags.json`
- Add missing keywords
- Refine LLM prompts
- Rebuild ChromaDB embeddings after tag changes

---

## Usage Examples

### Basic Tagging

```python
from src.analysis.tag_extraction import main_tagger

# Tag extracted faults
faults_df = main_tagger(
    faults_df=faults_df,
    start_time=start_time,
    agent="fault_analyst",
    max_workers=5,
    batch_size=10
)

print(f"Tagged {len(faults_df)} faults")
print(f"Tag distribution:\n{faults_df['tag'].value_counts()}")
```

### Direct Candidate Retrieval

```python
from src.analysis.tag_extraction import get_candidate_tags

candidates = get_candidate_tags("RF cavity trip", top_k=5)
print(f"Candidates: {candidates}")
# Output: ['Accelerator', 'Beam Diagnostics', 'Power', ...]
```

### Manual Classification

```python
from src.analysis.tag_extraction import load_tag_database, get_or_create_chroma_client, ensure_tag_collection

tags = load_tag_database()
client = get_or_create_chroma_client()
collection = ensure_tag_collection(client, tags)

# Query
results = collection.query(
    query_texts=["Vacuum leak in sector"],
    n_results=3,
    include=["metadatas", "distances"]
)

for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
    print(f"{meta['tag_name']}: distance={dist:.3f}")
```

---

## Testing

### Unit Tests

**Test Candidate Retrieval**:
```python
def test_get_candidate_tags():
    candidates = get_candidate_tags("RF cavity trip", top_k=3)
    
    assert len(candidates) == 3
    assert "Accelerator" in candidates
```

**Test Tag Database Loading**:
```python
def test_load_tag_database():
    tags = load_tag_database()
    
    assert len(tags) == 16
    assert tags[0]['name'] == "Accelerator"
    assert 'keywords' in tags[0]
    assert 'description' in tags[0]
```

### Integration Tests

**Test Full Tagging**:
```python
def test_tagging_integration():
    faults_df = pd.DataFrame({
        'description': ['RF cavity trip', 'Vacuum leak', 'BPM signal lost']
    })
    
    tagged_df = main_tagger(faults_df, start_time=time.time(), 
                            agent="fault_analyst", max_workers=2, batch_size=2)
    
    assert 'tag' in tagged_df.columns
    assert len(tagged_df) == 3
    assert all(tag in valid_tags for tag in tagged_df['tag'])
```

---

## Troubleshooting

### "No tags in database"

**Cause**: ChromaDB collection not initialized

**Fix**:
```python
# Force re-initialization
import shutil
from pathlib import Path

chroma_path = Path("tag_db/chroma_db")
if chroma_path.exists():
    shutil.rmtree(chroma_path)

# Run tagging again - will auto-initialize
```

### "All tags classified as 'Other'"

**Cause**: ChromaDB search not finding matches

**Fix**:
1. Check tag database loading
2. Verify ChromaDB collection has documents
3. Test query manually

**Debug**:
```python
tags = load_tag_database()
print(f"Loaded {len(tags)} tags")

client = get_or_create_chroma_client()
collection = client.get_collection("fault_tags")
print(f"Collection has {collection.count()} documents")

# Test query manually
results = collection.query(query_texts=["RF trip"], n_results=3)
print(f"Query results: {[m['tag_name'] for m in results['metadatas'][0]]}")
```

**Rebuild collection**:
```python
# Force rebuild if collection corrupted
from src.analysis.tag_extraction import rebuild_tag_database
rebuild_tag_database()
```

### "Wrong tags assigned"

**If tags are consistently wrong**:

**Fix**:
1. Improve tag descriptions in `tags.json`
2. Add more keywords
3. Adjust prompt for better LLM guidance

**Step 2**: Rebuild ChromaDB collection:

```bash
# Delete old ChromaDB data
rm -rf tag_db/chroma_db
# Run pipeline - will auto-rebuild
```

**Step 3**: Verify:
```python
client = get_or_create_chroma_client()
collection = client.get_collection("fault_tags")
print(f"Collection now has {collection.count()} documents")  # Should be 17
```

---

## Extending Tag Database

### Adding New Tags

**Step 1**: Edit `tag_db/tags.json`:

```json
{
  "name": "New Category",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "description": "Detailed description for semantic search"
}
```

**Step 2**: Rebuild ChromaDB collection:

```python
# Option A: Use built-in rebuild function
from src.analysis.tag_extraction import rebuild_tag_database
rebuild_tag_database()

# Option B: Delete and let auto-initialize
import shutil
from pathlib import Path

shutil.rmtree("tag_db/chroma_db")
# Next run will auto-rebuild
```

**Step 3**: Verify:
```python
client = get_or_create_chroma_client()
collection = client.get_collection("fault_tags")
print(f"Collection now has {collection.count()} documents")  # Should be 17
```

---

## Related Documentation

- [Tag Database](./TAG_DATABASE.md) - Complete tag reference
- [Fault Extraction](./PIPELINE_FAULT_EXTRACTION.md) - Previous stage
- [LLM Utilities](./UTILS_LLM.md) - LLM call implementation
- [Architecture](./ARCHITECTURE.md) - Overall system design

---

*For verification details, see [PIPELINE_VERIFICATION.md](./PIPELINE_VERIFICATION.md).*