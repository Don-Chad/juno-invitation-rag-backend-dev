#!/bin/bash
#
# Cleanup corrupted RAG database
# Use this if database is corrupted or has issues
#

echo "============================================================"
echo "RAG DATABASE CLEANUP SCRIPT"
echo "============================================================"
echo ""
echo "This will DELETE the current RAG database."
echo "You will need to run 'python ingest_documents.py' after this."
echo ""
read -p "Are you sure you want to continue? (yes/NO): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Removing database files..."

# Remove database files
rm -f local_vector_db_enhanced/vdb_data
rm -f local_vector_db_enhanced/vdb_data.map
rm -f local_vector_db_enhanced/vdb_data.tmp
rm -f local_vector_db_enhanced/vdb_data.tmp.map
rm -f local_vector_db_enhanced/vdb_data.backup
rm -f local_vector_db_enhanced/vdb_data.backup.map

# Remove metadata
rm -f local_vector_db_enhanced/metadata.pkl
rm -f local_vector_db_enhanced/metadata.pkl.tmp
rm -f local_vector_db_enhanced/metadata.pkl.backup

# Remove file history (forces reprocessing)
rm -f local_vector_db_enhanced/file_history.pkl

# Remove embeddings cache (will be rebuilt)
rm -f local_vector_db_enhanced/embeddings_cache.npy.npy
rm -f local_vector_db_enhanced/embeddings_cache.npy.temp.npy
rm -f local_vector_db_enhanced/embeddings_cache.npy.backup.npy

echo "✓ Database files removed"
echo ""
echo "Next steps:"
echo "  1. Run: python ingest_documents.py"
echo "  2. Wait for ingestion to complete"
echo "  3. Start worker: python agent_dev.py start"
echo ""
echo "============================================================"
