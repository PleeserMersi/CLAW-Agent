#!/bin/bash
# Clean temporary CSV, JSON, and backup files from the data folder
# Also cleans __pycache__ directories, tag_db/chroma_db, and testing pipeline output (including graphs and mock summaries)
# Keeps only files in data/final_output/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"

echo "Cleaning temporary files in $DATA_DIR..."
echo "Also cleaning __pycache__ directories, tag_db/chroma_db, and testing output (including graphs and mock summaries)..."
echo "Preserving: data/final_output/"
echo

# Count files to be deleted in data/
count=0
while IFS= read -r -d '' file; do
    ((count++))
done < <(find "$DATA_DIR" \( -name "*.csv" -o -name "*.json" -o -name "*.JSON" -o -name "*.backup" \) -type f ! -path "$DATA_DIR/final_output/*" -print0)

# Count __pycache__ directories (excluding venv)
pycache_count=$(find "$PROJECT_DIR" -path "$PROJECT_DIR/venv" -prune -o -type d -name "__pycache__" -print | grep -v "^$" | wc -l)

# Check for chroma_db directory
chroma_db_path="$PROJECT_DIR/tag_db/chroma_db"
if [ -d "$chroma_db_path" ]; then
    chroma_db_exists=1
else
    chroma_db_exists=0
fi

# Check for testing tag_db directory
testing_tag_db_path="$PROJECT_DIR/testing/tag_db"
if [ -d "$testing_tag_db_path" ]; then
    testing_tag_db_exists=1
else
    testing_tag_db_exists=0
fi

# Count testing pipeline output files (all files in pipeline_output, including graphs and mock summaries)
# Also includes SUMMARY.txt in mock_summaries
testing_count=0
while IFS= read -r -d '' file; do
    ((testing_count++))
done < <(find "$PROJECT_DIR/testing" \( -name "*.csv" -o -name "*.json" -o -name "*.png" -o -path "$PROJECT_DIR/testing/pipeline_output/*" -o -name "SUMMARY.txt" -path "$PROJECT_DIR/testing/mock_summaries/*" \) -type f \
    ! -name "accuracy_report_medium_vs_real.csv.json" \
    -print0)

total_count=$((count + pcache_count + chroma_db_exists + testing_tag_db_exists + testing_count))

if [ $total_count -eq 0 ]; then
    echo "No temporary files, __pycache__ directories, chroma_db, or testing output found to delete."
    exit 0
fi

echo "Found $count temporary file(s) to delete in data/:"
find "$DATA_DIR" \( -name "*.csv" -o -name "*.json" -o -name "*.JSON" -o -name "*.backup" \) -type f ! -path "$DATA_DIR/final_output/*" -print | sed 's|^|  |'

if [ $pycache_count -gt 0 ]; then
    echo ""
    echo "Found $pycache_count __pycache__ directory/directories to delete:"
    find "$PROJECT_DIR" -path "$PROJECT_DIR/venv" -prune -o -type d -name "__pycache__" -print | grep -v "^$" | sed 's|^|  |'
fi

if [ $chroma_db_exists -eq 1 ]; then
    echo ""
    echo "Found chroma_db directory to delete:"
    echo "  $chroma_db_path"
fi

if [ $testing_tag_db_exists -eq 1 ]; then
    echo ""
    echo "Found testing tag_db directory to delete:"
    echo "  $testing_tag_db_path"
fi

if [ $testing_count -gt 0 ]; then
    echo ""
    echo "Found $testing_count testing output file(s) to delete:"
    find "$PROJECT_DIR/testing" \( -name "*.csv" -o -name "*.json" -o -name "*.png" -o -path "$PROJECT_DIR/testing/pipeline_output/*" -o -name "SUMMARY.txt" -path "$PROJECT_DIR/testing/mock_summaries/*" \) -type f \
        ! -name "accuracy_report_medium_vs_real.csv.json" \
        -print | sed 's|^|  |'
fi
echo

# Ask for confirmation
read -p "Delete these files? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Delete the files in data/
find "$DATA_DIR" \( -name "*.csv" -o -name "*.json" -o -name "*.JSON" -o -name "*.backup" \) -type f ! -path "$DATA_DIR/final_output/*" -delete

# Delete __pycache__ directories (excluding venv)
find "$PROJECT_DIR" -path "$PROJECT_DIR/venv" -prune -o -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Delete chroma_db directory
if [ $chroma_db_exists -eq 1 ]; then
    rm -rf "$chroma_db_path"
fi

# Delete testing tag_db directory
if [ $testing_tag_db_exists -eq 1 ]; then
    rm -rf "$testing_tag_db_path"
fi

# Delete testing pipeline output files (all files in pipeline_output, including graphs and mock summaries)
# Also deletes SUMMARY.txt in mock_summaries
if [ $testing_count -gt 0 ]; then
    find "$PROJECT_DIR/testing" \( -name "*.csv" -o -name "*.json" -o -name "*.png" -o -path "$PROJECT_DIR/testing/pipeline_output/*" -o -name "SUMMARY.txt" -path "$PROJECT_DIR/testing/mock_summaries/*" \) -type f \
        ! -name "accuracy_report_medium_vs_real.csv.json" \
        -delete
fi

echo "Deleted $count temporary file(s), $pycache_count __pycache__ directory/directories, chroma_db, testing tag_db, and $testing_count testing output file(s)."
echo ""
echo "Preserved files in data/final_output/:"
find "$DATA_DIR/final_output" -name "*.csv" -type f -print | sed 's|^|  |'