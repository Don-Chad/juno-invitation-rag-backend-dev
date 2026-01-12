#!/usr/bin/env python3
"""
Pre-compute embeddings for all Q&A pairs and save to disk.
Run this ONCE after ingesting documents, then the worker loads instantly.
"""
import json
import pickle
from pathlib import Path
import requests
from tqdm import tqdm

QA_JSON_DIR = Path("qa_vector_db/dev_outputs")
EMBEDDINGS_OUTPUT = Path("qa_vector_db/qa_embeddings.pkl")
EMBEDDING_SERVER_URL = "http://localhost:7777/embedding"


def get_embedding(text: str):
    """Get embedding vector for text"""
    try:
        response = requests.post(
            EMBEDDING_SERVER_URL,
            json={"content": text},
            timeout=5.0
        )
        
        if response.status_code == 200:
            result = response.json()
            # Handle nested list format from llama server
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict) and 'embedding' in result[0]:
                    embedding = result[0]['embedding']
                    if isinstance(embedding, list) and len(embedding) > 0:
                        return embedding[0]
            return result
        else:
            print(f"Embedding server error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None


def main():
    print("=" * 80)
    print("PRE-COMPUTING Q&A EMBEDDINGS")
    print("=" * 80)
    
    qa_files = list(QA_JSON_DIR.glob("*.json"))
    print(f"\nFound {len(qa_files)} Q&A files")
    
    all_qa_pairs = []
    
    # Load all Q&A pairs
    print("\nStep 1: Loading Q&A pairs...")
    for json_file in qa_files:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        document_title = data.get('document_title', json_file.stem)
        
        for qa in data.get('qa_pairs', []):
            question = qa.get('question', '')
            answer = qa.get('answer', '')
            context = qa.get('context', answer)
            page_hint = qa.get('page_hint', None)
            
            if question and answer:
                all_qa_pairs.append({
                    'question': question,
                    'answer': answer,
                    'context': context,
                    'source': document_title,
                    'page': page_hint,
                    'embedding': None  # Will compute
                })
    
    print(f"✓ Loaded {len(all_qa_pairs)} Q&A pairs")
    
    # Compute embeddings
    print("\nStep 2: Computing embeddings (this will take a while)...")
    print(f"Estimated time: ~{len(all_qa_pairs) * 0.7 / 60:.1f} minutes")
    
    failed_count = 0
    
    for i, qa in enumerate(tqdm(all_qa_pairs, desc="Computing embeddings")):
        embedding = get_embedding(qa['question'])
        
        if embedding:
            qa['embedding'] = embedding
        else:
            failed_count += 1
            print(f"\n✗ Failed to get embedding for Q&A {i+1}")
    
    # Remove failed embeddings
    all_qa_pairs = [qa for qa in all_qa_pairs if qa['embedding'] is not None]
    
    print(f"\n✓ Computed {len(all_qa_pairs)} embeddings")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count}")
    
    # Save to disk
    print("\nStep 3: Saving embeddings to disk...")
    EMBEDDINGS_OUTPUT.parent.mkdir(exist_ok=True)
    
    with open(EMBEDDINGS_OUTPUT, 'wb') as f:
        pickle.dump(all_qa_pairs, f)
    
    file_size_mb = EMBEDDINGS_OUTPUT.stat().st_size / 1024 / 1024
    print(f"✓ Saved to {EMBEDDINGS_OUTPUT}")
    print(f"  File size: {file_size_mb:.2f} MB")
    
    print("\n" + "=" * 80)
    print("✅ DONE! Worker will now load instantly.")
    print("=" * 80)


if __name__ == "__main__":
    main()

