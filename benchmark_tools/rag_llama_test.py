import asyncio
import sys
import logging
import numpy as np
import requests
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rag-llama-test")

# Import the RAG module
sys.path.append('/root/workerv12_grace')
import rag_module_hq_enhanced as rag

async def test_embeddings():
    """Test the embeddings generation with llama-server"""
    logger.info("Testing embeddings generation...")
    
    test_texts = [
        "What is the weather like today?",
        "How do neural networks work?",
        "Tell me about document retrieval systems.",
        "What's the capital of France?"
    ]
    
    for text in test_texts:
        logger.info(f"Testing embedding for: '{text}'")
        
        # Measure time
        start_time = time.time()
        
        # Get embedding
        embedding = await rag.create_embeddings(text)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Log results
        if embedding is not None and isinstance(embedding, np.ndarray):
            logger.info(f"Successfully generated embedding: shape={embedding.shape}, dimension={len(embedding)}")
            logger.info(f"Time taken: {elapsed_ms:.2f} ms")
            logger.info(f"Sample values: {embedding[:5]}...")
        else:
            logger.error(f"Failed to generate embedding. Type: {type(embedding)}")
    
    return True

async def test_rag_system():
    """Test the complete RAG system integration"""
    logger.info("Testing RAG system initialization...")
    
    # Initialize the system
    await rag.initialize()
    
    # Test a simple query
    test_query = "What is in the documents?"
    logger.info(f"Testing RAG query: '{test_query}'")
    
    start_time = time.time()
    results = await rag.query_rag(test_query, num_results=3)
    elapsed_ms = (time.time() - start_time) * 1000
    
    logger.info(f"Query completed in {elapsed_ms:.2f} ms")
    logger.info(f"Results:\n{results}")
    
    return True

async def main():
    """Main test function"""
    logger.info("Starting llama-server RAG integration tests")
    
    # Test server connectivity
    try:
        response = requests.get(rag.LLAMA_SERVER_URL.rsplit('/', 1)[0], timeout=5)
        logger.info(f"Llama-server connection test: status={response.status_code}")
    except Exception as e:
        logger.error(f"Llama-server is not accessible: {e}")
        return False
    
    # Run tests
    await test_embeddings()
    await test_rag_system()
    
    logger.info("Tests completed")
    return True

if __name__ == "__main__":
    asyncio.run(main()) 