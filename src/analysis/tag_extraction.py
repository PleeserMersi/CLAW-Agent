"""
Tag extraction and classification for faults.
Uses ChromaDB vector database for semantic similarity search to find relevant tags.
"""
import json
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
# ChromaDB import is lazy to handle SQLite version issues
# import chromadb  # Imported only when needed in get_or_create_chroma_client()
# from chromadb.config import Settings  # Imported only when needed

from config import AGENT_NAME, BASE_DIR
from utils.llm_utils import call_llm, PROMPT_TEMPLATES
from utils.logging_utils import logger
from utils.shutdown import is_shutdown_requested

stdlib_json = json


TAG_DB_DIR = BASE_DIR / "tag_db"
TAG_DB_PATH = TAG_DB_DIR / "tags.json"
CHROMA_DB_PATH = TAG_DB_DIR / "chroma_db"


def load_tag_database() -> List[Dict[str, Any]]:
    """
    Load the tag database from JSON file.
    
    Returns:
        List of tag dictionaries
    """
    if not TAG_DB_PATH.exists():
        logger.warning(f"Tag database not found at {TAG_DB_PATH}")
        return []
    
    try:
        with open(TAG_DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load tag database: {e}")
        return []


def get_or_create_chroma_client():
    """
    Get or create a ChromaDB client with persistent storage.
    
    Returns:
        ChromaDB client or None if ChromaDB is unavailable
    """
    try:
        import chromadb
    except RuntimeError as e:
        logger.warning(f"ChromaDB unavailable: {e}. Using keyword-based tagging only.")
        return None
    
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    return client


def ensure_tag_collection(client, tags: List[Dict[str, Any]]):
    """
    Ensure the tag collection exists and is populated with tag embeddings.
    Creates embeddings if the collection is empty.
    
    Args:
        client: ChromaDB client
        tags: List of tag dictionaries
        
    Returns:
        ChromaDB collection with tags, or None if client is unavailable
    """
    if client is None:
        logger.warning("ChromaDB client is None - cannot create collection")
        return None
    
    from chromadb.config import Settings
    collection = client.get_or_create_collection(name="fault_tags")
    
    # Check if collection is empty
    if collection.count() == 0 and tags:
        logger.info("Initializing tag vector database with embeddings...")
        
        # Prepare documents and metadata for embedding
        documents = []
        metadatas = []
        ids = []
        
        for tag_info in tags:
            tag_name = tag_info.get('name', '')
            keywords = tag_info.get('keywords', [])
            description = tag_info.get('description', '')
            
            # Create a rich document for embedding
            # Combine tag name, keywords, and description
            doc_text = f"{tag_name}: {' '.join(keywords)} {description}".strip()
            
            if not doc_text:
                continue
            
            # Generate unique ID
            tag_id = hashlib.md5(tag_name.encode()).hexdigest()[:12]
            
            documents.append(doc_text)
            metadatas.append({
                "tag_name": tag_name,
                "keywords": ",".join(keywords),
                "description": description
            })
            ids.append(tag_id)
        
        if documents:
            # Add documents to collection
            # ChromaDB will use its default embedding function
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Initialized tag database with {len(documents)} tag embeddings")
        else:
            logger.warning("No valid tag documents found for embedding")
    
    return collection


def get_candidate_tags(description: str, top_k: int = 5) -> List[str]:
    """
    Get candidate tags for a fault description using vector similarity search.
    
    Uses ChromaDB to find semantically similar tags based on the fault description.
    
    Args:
        description: Fault description text
        top_k: Number of top candidates to return
        
    Returns:
        List of candidate tag names (at least "Other" if no matches)
    """
    tags = load_tag_database()
    
    if not tags:
        return ["Other"]
    
    try:
        client = get_or_create_chroma_client()
        if client is None:
            # ChromaDB unavailable, use keyword matching directly
            logger.debug("ChromaDB unavailable, using keyword-based tagging")
            return get_candidate_tags_keyword(description, top_k)
        
        collection = ensure_tag_collection(client, tags)
        if collection is None:
            # Collection creation failed, use keyword matching
            logger.debug("ChromaDB collection unavailable, using keyword-based tagging")
            return get_candidate_tags_keyword(description, top_k)
        
        # Query the collection for similar tags
        results = collection.query(
            query_texts=[description],
            n_results=min(top_k, collection.count()),
            include=["metadatas", "distances"]
        )
        
        # Extract tag names from results
        candidate_tags = []
        if results["metadatas"] and results["metadatas"][0]:
            for metadata in results["metadatas"][0]:
                tag_name = metadata.get("tag_name")
                if tag_name and tag_name not in candidate_tags:
                    candidate_tags.append(tag_name)
        
        # Ensure we have at least one candidate
        if not candidate_tags:
            return ["Other"]
        
        return candidate_tags[:top_k]
        
    except Exception as e:
        logger.error(f"Vector search failed: {e}. Falling back to keyword matching.")
        # Fallback to keyword matching
        return get_candidate_tags_keyword(description, top_k)


def get_candidate_tags_keyword(description: str, top_k: int = 5) -> List[str]:
    """
    Fallback keyword-based tag matching if vector search fails.
    
    Args:
        description: Fault description
        top_k: Number of top candidates to return
        
    Returns:
        List of candidate tag names
    """
    tags = load_tag_database()
    
    if not tags:
        return ["Other"]
    
    description_lower = description.lower()
    
    scored_tags = []
    for tag_info in tags:
        tag_name = tag_info.get('name', '')
        keywords = tag_info.get('keywords', [])
        
        score = 0
        for keyword in keywords:
            if keyword.lower() in description_lower:
                score += 1
        
        if score > 0:
            scored_tags.append((tag_name, score))
    
    # Sort by score and return top_k
    scored_tags.sort(key=lambda x: x[1], reverse=True)
    return [tag[0] for tag in scored_tags[:top_k]] or ["Other"]


def rebuild_tag_database() -> None:
    """
    Rebuild the tag vector database from the JSON tag database.
    Useful after updating tags.json with new tags or descriptions.
    """
    tags = load_tag_database()
    
    if not tags:
        logger.warning("No tags found in tag database")
        return
    
    try:
        client = get_or_create_chroma_client()
        
        # Delete existing collection if it exists
        try:
            client.delete_collection(name="fault_tags")
            logger.info("Deleted existing tag collection")
        except Exception:
            pass  # Collection might not exist
        
        # Recreate with new embeddings
        collection = ensure_tag_collection(client, tags)
        logger.info(f"Rebuilt tag database with {collection.count()} tag embeddings")
        
    except Exception as e:
        logger.error(f"Failed to rebuild tag database: {e}")


def _classify_single_fault(row: pd.Series, candidates: List[str], agent: str = None) -> Tuple[int, str]:
    """
    Worker function to classify a single fault's tag.
    Thread-safe for use in ThreadPoolExecutor.
    
    Args:
        row: DataFrame row with fault data
        candidates: List of candidate tag names
        agent: openclaw agent name
        
    Returns:
        Tuple of (row_index, selected_tag)
    """
    # Check for shutdown at start of work
    if is_shutdown_requested():
        raise KeyboardInterrupt("Shutdown requested")
    
    idx = row.name  # Get the row index
    description = row.get('description', '')
    
    if not candidates:
        return idx, "Other"
    
    tag_options = "\n".join(f"- {tag}" for tag in candidates)
    
    prompt = PROMPT_TEMPLATES["tagger_prompt"].format(
        description=description,
        tag_options=tag_options
    )
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        selected_tag = reply.strip()
        if selected_tag in candidates:
            return idx, selected_tag
    
    return idx, "Other"


def classify_faults_batch(batch_data: List[Tuple[int, int, str, List[str]]], agent: str = None) -> List[Tuple[int, str]]:
    """
    Classify multiple faults in a single batched LLM call.
    
    Args:
        batch_data: List of (local_idx, original_row_idx, description, candidates) tuples
        agent: openclaw agent name
        
    Returns:
        List of (original_row_idx, selected_tag) tuples
    """
    if not batch_data:
        return []
    
    # Get unique candidates across all faults in batch
    all_candidates = set()
    for _, _, _, candidates in batch_data:
        all_candidates.update(candidates)
    
    if not all_candidates:
        return [(orig_idx, "Other") for _, orig_idx, _, _ in batch_data]
    
    tag_options = "\n".join(f"- {tag}" for tag in sorted(all_candidates))
    
    # Build the faults block with local indices
    faults_block = ""
    for local_idx, orig_idx, description, candidates in batch_data:
        faults_block += f"--- FAULT {local_idx} (original row {orig_idx}) ---\nDescription: {description}\nCandidates: {', '.join(candidates)}\n\n"
    
    if not faults_block.strip():
        return [(orig_idx, "Other") for _, orig_idx, _, _ in batch_data]
    
    prompt = PROMPT_TEMPLATES["tagger_batch"].format(
        tag_options=tag_options,
        faults_block=faults_block
    )
    
    response = call_llm(prompt=prompt, agent=agent)
    
    if not response:
        logger.warning("No response from LLM for batch tagging")
        return [(orig_idx, "Other") for _, orig_idx, _, _ in batch_data]
    
    logger.debug(f"Batch tagging response (first 500 chars): {response[:500]}")
    
    # Parse the batched response
    results = {}
    
    try:
        # Try to extract JSON array
        json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.warning("No JSON array found in batch tagging response")
            return [(orig_idx, "Other") for _, orig_idx, _, _ in batch_data]
        
        json_str = json_match.group(0)
        batch_data_parsed = stdlib_json.loads(json_str)
        
        if not isinstance(batch_data_parsed, list):
            logger.warning(f"Expected list, got {type(batch_data_parsed)}")
            return [(orig_idx, "Other") for _, orig_idx, _, _ in batch_data]
        
        # Create a map of local_idx to original_row_idx
        local_to_orig = {local_idx: orig_idx for local_idx, orig_idx, _, _ in batch_data}
        
        # Process each result
        for item in batch_data_parsed:
            if not isinstance(item, dict):
                continue
            
            local_idx = item.get("index")
            selected_tag = item.get("tag", "Other")
            
            if local_idx is None:
                continue
            
            # Map local index to original row index
            if local_idx in local_to_orig:
                orig_idx = local_to_orig[local_idx]
                results[orig_idx] = (orig_idx, selected_tag)
            else:
                logger.warning(f"Invalid local index in batch response: {local_idx}")
        
        # Return results in order of original batch_data
        return [results.get(orig_idx, (orig_idx, "Other")) for _, orig_idx, _, _ in batch_data]
        
    except Exception as e:
        logger.error(f"Failed to parse batch tagging response: {e}")
        logger.warning(f"Full response: {response}")
        return [(orig_idx, "Other") for _, orig_idx, _, _ in batch_data]


def classify_fault_with_tags(
    description: str,
    candidate_tags: List[str],
    agent: str = None
) -> str:
    """
    Classify a fault using candidate tags and LLM.
    
    Args:
        description: Fault description
        candidate_tags: List of candidate tag names
        agent: openclaw agent name
        
    Returns:
        Selected tag name
    """
    if not candidate_tags:
        return "Other"
    
    tag_options = "\n".join(f"- {tag}" for tag in candidate_tags)
    
    prompt = PROMPT_TEMPLATES["tagger_prompt"].format(
        description=description,
        tag_options=tag_options
    )
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        selected_tag = reply.strip()
        if selected_tag in candidate_tags:
            return selected_tag
    
    return "Other"


def main_tagger(faults_df: pd.DataFrame, start_time: float = None, agent: str = None, max_workers: int = 4, batch_size: int = None) -> pd.DataFrame:
    """
    Add tags to all faults in the DataFrame using vector similarity search and parallel processing.
    Supports both single-item processing and batched processing.
    
    Args:
        faults_df: DataFrame with faults
        start_time: Optional start time for logging
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        DataFrame with tags added
    """
    if faults_df is None or len(faults_df) == 0:
        return faults_df
    
    if agent is None:
        agent = AGENT_NAME
    
    # Pre-initialize the vector database
    try:
        tags = load_tag_database()
        client = get_or_create_chroma_client()
        collection = ensure_tag_collection(client, tags)
        logger.info(f"Vector database ready with {collection.count()} tag embeddings")
    except Exception as e:
        logger.error(f"Failed to initialize vector database: {e}")
    
    if batch_size and batch_size > 1:
        logger.info(f"Starting tag classification with batching (size={batch_size}, workers={max_workers})...")
        return _tag_faults_batched(faults_df, batch_size, max_workers, agent)
    
    logger.info(f"Starting tag classification for {len(faults_df)} faults with {max_workers} parallel workers...")
    
    # Create a copy to avoid modifying the original during iteration
    faults_df = faults_df.copy()
    
    # Pre-compute candidates for all faults (vector search is fast, no need to parallelize)
    logger.info("Pre-computing candidate tags for all faults...")
    candidates_map = {}
    skipped_indices = set()
    
    for idx, row in faults_df.iterrows():
        description = row.get('description', '')
        current_tag = row.get('tag', '')
        
        # Skip if already tagged (not 'Other')
        if current_tag and current_tag != 'Other':
            skipped_indices.add(idx)
            continue
        
        # Get candidate tags using vector similarity
        try:
            candidates = get_candidate_tags(description, top_k=5)
            candidates_map[idx] = candidates
        except Exception as e:
            logger.warning(f"Vector search failed for fault {idx}: {e}")
            candidates = get_candidate_tags_keyword(description, top_k=5)
            candidates_map[idx] = candidates
    
    # Filter to only faults that need tagging and have multiple candidates
    rows_to_tag = []
    for idx, candidates in candidates_map.items():
        if len(candidates) > 1:
            rows_to_tag.append((idx, faults_df.iloc[idx], candidates))
        else:
            skipped_indices.add(idx)
    
    if not rows_to_tag:
        logger.info(f"No faults need tagging. All skipped or already tagged.")
        logger.info(f"Tag classification completed: 0 newly tagged, {len(skipped_indices)} skipped, total: {len(faults_df)} faults")
        return faults_df
    
    logger.info(f"Classifying {len(rows_to_tag)} faults with LLM...")
    
    # Process in parallel
    tagged_count = 0
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_classify_single_fault, row, candidates, agent): idx
            for idx, (_, row, candidates) in enumerate(rows_to_tag)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Tag classification interrupted by shutdown request")
                break
            try:
                row_idx, selected_tag = future.result()
                faults_df.at[row_idx, 'tag'] = selected_tag
                tagged_count += 1
                logger.info(f"Progress: [{completed + 1}/{len(rows_to_tag)}] Tagged with: {selected_tag}")
            except KeyboardInterrupt:
                logger.info("Tag classification interrupted")
                break
            except Exception as e:
                row_idx = futures[future]
                logger.error(f"Tagging failed for row {row_idx}: {e}")
                # On error, keep as Other
                faults_df.at[row_idx, 'tag'] = 'Other'
    
    logger.info(f"Tag classification completed: {tagged_count} newly tagged, {len(skipped_indices)} skipped, total: {len(faults_df)} faults")
    
    return faults_df


def _tag_faults_batched(faults_df: pd.DataFrame, batch_size: int, max_workers: int, agent: str = None) -> pd.DataFrame:
    """
    Add tags to faults in batches for improved throughput.
    
    Args:
        faults_df: DataFrame with faults
        batch_size: Number of faults per batch
        max_workers: Number of parallel batch workers
        agent: openclaw agent name
        
    Returns:
        DataFrame with tags added
    """
    if agent is None:
        agent = AGENT_NAME
    
    faults_df = faults_df.copy()
    
    # Pre-compute candidates for all faults
    logger.info("Pre-computing candidate tags for all faults...")
    candidates_map = {}
    skipped_indices = set()
    
    for idx, row in faults_df.iterrows():
        description = row.get('description', '')
        current_tag = row.get('tag', '')
        
        # Skip if already tagged (not 'Other')
        if current_tag and current_tag != 'Other':
            skipped_indices.add(idx)
            continue
        
        # Get candidate tags using vector similarity
        try:
            candidates = get_candidate_tags(description, top_k=5)
            candidates_map[idx] = candidates
        except Exception as e:
            logger.warning(f"Vector search failed for fault {idx}: {e}")
            candidates = get_candidate_tags_keyword(description, top_k=5)
            candidates_map[idx] = candidates
    
    # Filter to only faults that need tagging and have multiple candidates
    rows_to_tag = []
    for idx, candidates in candidates_map.items():
        if len(candidates) > 1:
            rows_to_tag.append((idx, faults_df.iloc[idx], candidates))
        else:
            skipped_indices.add(idx)
    
    if not rows_to_tag:
        logger.info(f"No faults need tagging. All skipped or already tagged.")
        logger.info(f"Tag classification completed: 0 newly tagged, {len(skipped_indices)} skipped, total: {len(faults_df)} faults")
        return faults_df
    
    logger.info(f"Processing {len(rows_to_tag)} faults in batches of up to {batch_size}...")
    
    # Split into batches
    batches = []
    for i in range(0, len(rows_to_tag), batch_size):
        batch = rows_to_tag[i:i + batch_size]
        # Format: List of (local_idx, original_row_idx, description, candidates)
        batch_data = [(local_idx, idx, row.get('description', ''), candidates) 
                      for local_idx, (idx, row, candidates) in enumerate(batch)]
        batches.append(batch_data)
    
    logger.info(f"Created {len(batches)} batches")
    
    # Process batches in parallel
    tagged_count = 0
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(classify_faults_batch, batch_data, agent): idx
            for idx, batch_data in enumerate(batches)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Batch tag classification interrupted by shutdown request")
                break
            try:
                results = future.result()
                
                for orig_idx, selected_tag in results:
                    if selected_tag != "Other":
                        faults_df.at[orig_idx, 'tag'] = selected_tag
                        tagged_count += 1
                        logger.info(f"Batch {completed}/{len(batches)}: Fault {orig_idx + 1} tagged with: {selected_tag}")
                    else:
                        # Keep as Other (already the default)
                        pass
                    
            except KeyboardInterrupt:
                logger.info("Batch tag classification interrupted")
                break
            except Exception as e:
                logger.error(f"Batch {completed}/{len(batches)} failed: {e}")
                # On error, keep faults as "Other"
    
    logger.info(f"Batched tag classification completed: {tagged_count} newly tagged, {len(skipped_indices)} skipped, total: {len(faults_df)} faults")
    
    return faults_df
