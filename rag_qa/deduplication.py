"""
Q&A deduplication utilities.

Remove semantically duplicate questions while keeping valuable variety.
Uses LLM to intelligently detect truly redundant questions.
"""
import asyncio
import aiohttp
import json
from typing import List, Dict, Tuple
import numpy as np
from groq import Groq
from . import config


async def get_embedding(text: str, session: aiohttp.ClientSession) -> np.ndarray:
    """Get embedding for text from llama server."""
    try:
        async with session.post(
            config.LLAMA_SERVER_URL,
            json={"content": text}
        ) as response:
            if response.status == 200:
                result = await response.json()
                
                # Llama server format: [{"index": 0, "embedding": [[...]]}]
                if isinstance(result, list) and len(result) > 0:
                    first_item = result[0]
                    if isinstance(first_item, dict) and 'embedding' in first_item:
                        embedding = first_item['embedding']
                        # Embedding is nested [[...]], flatten to [...]
                        if isinstance(embedding, list) and len(embedding) > 0:
                            embedding = embedding[0]
                        return np.array(embedding, dtype=np.float32)
                
                print(f"⚠️  Unexpected embedding response format")
                return None
            else:
                print(f"⚠️  Embedding error: HTTP {response.status}")
                return None
    except Exception as e:
        print(f"⚠️  Embedding error: {e}")
        return None


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    if v1 is None or v2 is None:
        return 0.0
    dot_product = np.dot(v1, v2)
    norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm_product == 0:
        return 0.0
    return dot_product / norm_product


async def deduplicate_qa_pairs_llm(qa_pairs: List[Dict], batch_size: int = 30) -> Tuple[List[Dict], List[Dict]]:
    """
    Remove redundant questions using LLM to detect truly duplicate questions.
    
    The LLM understands that similar questions asking for different aspects
    (count vs timing vs location) are VALUABLE, while questions asking the 
    exact same thing in different words are REDUNDANT.
    
    For large lists, processes in batches to avoid token limits.
    
    Returns:
        (unique_qa_pairs, duplicate_qa_pairs)
    """
    
    if len(qa_pairs) <= 1:
        return qa_pairs, []
    
    print(f"\n🤖 LLM-based deduplication of {len(qa_pairs)} Q&A pairs...")
    
    # If too many Q&As, process in batches
    if len(qa_pairs) > batch_size:
        print(f"   Processing in batches of {batch_size}...")
        all_duplicates = []
        remaining_qa_pairs = qa_pairs.copy()
        
        while len(remaining_qa_pairs) > 0:
            batch = remaining_qa_pairs[:batch_size]
            unique_batch, dup_batch = await _deduplicate_batch_llm(batch)
            
            # Keep unique ones, track duplicates
            all_duplicates.extend(dup_batch)
            remaining_qa_pairs = remaining_qa_pairs[batch_size:]
        
        # Now all batches are internally deduplicated
        # Re-index and build final result
        all_unique_questions = {qa['question'] for qa in qa_pairs if qa not in all_duplicates}
        final_unique = [qa for qa in qa_pairs if qa['question'] in all_unique_questions]
        
        print(f"\n   ✓ Kept {len(final_unique)} unique Q&As")
        print(f"   ✗ Removed {len(all_duplicates)} redundant Q&As")
        
        return final_unique, all_duplicates
    else:
        return await _deduplicate_batch_llm(qa_pairs)


async def _deduplicate_batch_llm(qa_pairs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Process a single batch of Q&A pairs for deduplication."""
    
    if len(qa_pairs) <= 1:
        return qa_pairs, []
    
    # Extract questions with indices
    questions_with_idx = [
        {"idx": i, "question": qa['question']} 
        for i, qa in enumerate(qa_pairs)
    ]
    
    # Create prompt for LLM
    prompt = f"""Je bent een expert in het identificeren van redundante vragen in een kennisbank.

TAAK: Analyseer de volgende {len(questions_with_idx)} vragen en identificeer welke vragen ECHT REDUNDANT zijn.

BELANGRIJK:
- Vragen die HETZELFDE vragen maar anders geformuleerd = REDUNDANT ❌
  Voorbeeld: "Hoeveel kernreactoren?" vs "Wat is het aantal kernreactoren?"
  
- Vragen over VERSCHILLENDE ASPECTEN van hetzelfde onderwerp = WAARDEVOL ✓
  Voorbeeld: "Hoeveel kernreactoren?" vs "Wanneer zijn de reactoren operationeel?"
  
- Vragen die gaan over:
  * Aantal vs timing = VERSCHILLEND ✓
  * Aantal vs locatie = VERSCHILLEND ✓
  * Aantal vs kosten = VERSCHILLEND ✓
  * Proces vs resultaat = VERSCHILLEND ✓
  * Wat vs hoe vs waarom = VERSCHILLEND ✓

VRAGEN:
{json.dumps(questions_with_idx, ensure_ascii=False, indent=2)}

OUTPUT: Geef een JSON lijst met indices van vragen die REDUNDANT zijn (duplicaten van eerdere vragen).
Formaat:
{{
  "redundant_indices": [3, 7, 12],
  "reasoning": "Vraag 3 is hetzelfde als vraag 1, alleen anders geformuleerd. Vraag 7 vraagt hetzelfde als vraag 2..."
}}

Wees CONSERVATIEF - behoud vragen tenzij ze ECHT hetzelfde vragen.
"""

    try:
        # Use Groq with small model for deduplication
        client = Groq(api_key=config.GROQ_API_KEY)
        
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",  # Fast, cheap model for deduplication
            messages=[
                {"role": "system", "content": "Je bent een expert in het identificeren van redundante vragen. Answer in JSON mode. Output alleen geldige JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_completion_tokens=4096,  # Groq requires max_completion_tokens, not max_tokens
            response_format={"type": "json_object"},
            stream=False
        )
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        redundant_indices = set(result.get('redundant_indices', []))
        reasoning = result.get('reasoning', '')
        
        print(f"   LLM identified {len(redundant_indices)} redundant questions")
        if reasoning:
            print(f"   Reasoning: {reasoning[:200]}{'...' if len(reasoning) > 200 else ''}")
        
        # Build result lists
        unique_qa_pairs = [qa for i, qa in enumerate(qa_pairs) if i not in redundant_indices]
        duplicate_qa_pairs = [qa for i, qa in enumerate(qa_pairs) if i in redundant_indices]
        
        # Show removed questions
        if duplicate_qa_pairs:
            print(f"\n   ⚠️  Removed as redundant:")
            for i, qa in enumerate(duplicate_qa_pairs[:5], 1):
                print(f"      [{i}] {qa['question'][:80]}...")
            if len(duplicate_qa_pairs) > 5:
                print(f"      ... and {len(duplicate_qa_pairs) - 5} more")
        
        print(f"\n   ✓ Kept {len(unique_qa_pairs)} unique Q&As")
        print(f"   ✗ Removed {len(duplicate_qa_pairs)} redundant Q&As")
        
        return unique_qa_pairs, duplicate_qa_pairs
        
    except Exception as e:
        print(f"   ⚠️  LLM deduplication failed: {e}")
        print(f"   Keeping all Q&As without deduplication")
        return qa_pairs, []


async def deduplicate_qa_pairs(qa_pairs: List[Dict], similarity_threshold: float = 0.95) -> Tuple[List[Dict], List[Dict]]:
    """
    Remove semantically duplicate questions from Q&A pairs.
    
    Args:
        qa_pairs: List of Q&A dictionaries
        similarity_threshold: Cosine similarity threshold for duplicates (0.92 = very similar)
    
    Returns:
        (unique_qa_pairs, duplicate_qa_pairs)
    """
    
    if len(qa_pairs) <= 1:
        return qa_pairs, []
    
    print(f"\n🔍 Deduplicating {len(qa_pairs)} Q&A pairs...")
    print(f"   Similarity threshold: {similarity_threshold}")
    
    # Extract questions for embedding
    questions = [qa['question'] for qa in qa_pairs]
    
    # Get embeddings for all questions
    embeddings = []
    async with aiohttp.ClientSession() as session:
        # Batch process with small delays
        for i, question in enumerate(questions):
            if i > 0 and i % 10 == 0:
                await asyncio.sleep(0.1)  # Small delay every 10 requests
            
            embedding = await get_embedding(question, session)
            embeddings.append(embedding)
            
            if i % 20 == 0:
                print(f"   Embedded {i}/{len(questions)} questions...")
    
    print(f"   ✓ Embedded {len(embeddings)} questions")
    
    # Find duplicates using cosine similarity
    unique_indices = []
    duplicate_indices = []
    
    for i in range(len(qa_pairs)):
        if embeddings[i] is None:
            unique_indices.append(i)
            continue
        
        is_duplicate = False
        
        # Compare with all previous unique questions
        for j in unique_indices:
            if embeddings[j] is None:
                continue
            
            similarity = cosine_similarity(embeddings[i], embeddings[j])
            
            if similarity >= similarity_threshold:
                # This is a duplicate
                is_duplicate = True
                duplicate_indices.append(i)
                
                # Show duplicate info in dev mode
                print(f"\n   ⚠️  Duplicate found (similarity: {similarity:.3f}):")
                print(f"      Original [{j+1}]: {questions[j][:80]}...")
                print(f"      Duplicate [{i+1}]: {questions[i][:80]}...")
                break
        
        if not is_duplicate:
            unique_indices.append(i)
    
    # Build result lists
    unique_qa_pairs = [qa_pairs[i] for i in unique_indices]
    duplicate_qa_pairs = [qa_pairs[i] for i in duplicate_indices]
    
    print(f"\n   ✓ Kept {len(unique_qa_pairs)} unique Q&As")
    print(f"   ✗ Removed {len(duplicate_qa_pairs)} duplicates")
    
    return unique_qa_pairs, duplicate_qa_pairs

