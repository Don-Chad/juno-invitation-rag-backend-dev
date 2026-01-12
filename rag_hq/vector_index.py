"""
Enhanced Annoy index wrapper for vector similarity search.
"""
import asyncio
import numpy as np
from annoy import AnnoyIndex
import pickle
import aiofiles
import aiofiles.os
import logging

from .config import VECTOR_DIM, USE_FP16_EMBEDDINGS

logger = logging.getLogger("rag-assistant-enhanced")


class EnhancedAnnoyIndex:
    """Enhanced Annoy index with UUID mapping and async operations."""
    
    def __init__(self, dim):
        self.index = AnnoyIndex(dim, 'angular')
        self.uuid_map = {}
        self.next_id = 0
        
    def add_item(self, uuid_str, vector):
        """Add an item to the index with a UUID as userdata."""
        # Normalize vector for cosine similarity
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        self.uuid_map[self.next_id] = uuid_str
        self.index.add_item(self.next_id, vector)
        self.next_id += 1
        
    def build(self, n_trees):
        """Build the index with the specified number of trees."""
        self.index.build(n_trees)
        
    async def save_async(self, file_path, executor):
        """Save the index to a file asynchronously."""
        loop = asyncio.get_running_loop()
        
        # Save index in thread pool
        await loop.run_in_executor(executor, self.index.save, file_path)
        
        # Save uuid map
        map_path = file_path + '.map'
        async with aiofiles.open(map_path, 'wb') as f:
            await f.write(pickle.dumps(self.uuid_map))
            
    @classmethod
    async def load_async(cls, file_path, executor):
        """Load the index from a file asynchronously."""
        if not await aiofiles.os.path.exists(file_path):
            raise FileNotFoundError(f"Index file not found: {file_path}")
            
        map_path = file_path + '.map'
        if not await aiofiles.os.path.exists(map_path):
            raise FileNotFoundError(f"UUID map file not found: {map_path}")
            
        async with aiofiles.open(map_path, 'rb') as f:
            uuid_map = pickle.loads(await f.read())
            
        index = cls(VECTOR_DIM)
        
        # Load index with memory mapping
        index.index = AnnoyIndex(VECTOR_DIM, 'angular')
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, 
                                 lambda: index.index.load(file_path, prefault=False))
        
        index.uuid_map = uuid_map
        index.next_id = max(uuid_map.keys()) + 1 if uuid_map else 0
        return index
        
    async def query_async(self, vector, n, executor):
        """Query the index for the closest matches using cosine similarity."""
        # Normalize query vector
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        loop = asyncio.get_running_loop()
        
        def _query_index():
            return self.index.get_nns_by_vector(vector, n, include_distances=True)
        
        result = await loop.run_in_executor(executor, _query_index)
        
        # Handle different return formats
        if isinstance(result, tuple) and len(result) == 2:
            indices, distances = result
        else:
            indices = self.index.get_nns_by_vector(vector, n)
            distances = [0.5] * len(indices)
        
        results = []
        for idx, dist in zip(indices, distances):
            if idx in self.uuid_map:
                # Convert angular distance to cosine similarity
                cosine_sim = 1 - (dist ** 2) / 2
                result = type('QueryResult', (), {
                    'userdata': self.uuid_map[idx], 
                    'distance': dist,
                    'cosine_similarity': cosine_sim
                })
                results.append(result)
        return results


async def validate_index(index, metadata):
    """Validate that index and metadata are consistent and functional."""
    try:
        if index.index.get_n_items() == 0:
            return False, "Index is empty"
        
        if len(index.uuid_map) != index.index.get_n_items():
            return False, f"UUID map size mismatch: {len(index.uuid_map)} vs {index.index.get_n_items()}"
        
        # Test query functionality with a random vector
        test_vector = np.random.rand(VECTOR_DIM).astype(np.float16 if USE_FP16_EMBEDDINGS else np.float32)
        norm = np.linalg.norm(test_vector)
        if norm > 0:
            test_vector = test_vector / norm
        
        from .state import state
        results = await index.query_async(test_vector, n=1, executor=state.executor)
        
        # Verify metadata exists for returned items
        if results:
            for result in results:
                if result.userdata not in metadata:
                    return False, f"Metadata missing for UUID {result.userdata}"
        
        logger.info(f"Index validation passed: {index.index.get_n_items()} items, {len(metadata)} metadata entries")
        return True, "Validation passed"
    except Exception as e:
        return False, f"Validation failed with exception: {e}"


async def copy_index_efficiently(old_index, new_index, batch_size=500):
    """Copy index in batches to reduce memory usage."""
    total_items = old_index.index.get_n_items()
    if total_items == 0:
        logger.info("No items to copy from old index")
        return 0, 0
    
    logger.info(f"Copying {total_items:,} items from existing index in batches of {batch_size:,}...")
    copied = 0
    errors = 0
    
    for i in range(0, total_items, batch_size):
        end = min(i + batch_size, total_items)
        
        for j in range(i, end):
            try:
                vector = old_index.index.get_item_vector(j)
                uuid_str = old_index.uuid_map.get(j)
                if uuid_str:
                    new_index.add_item(uuid_str, vector)
                    copied += 1
            except Exception as e:
                logger.error(f"Error copying item {j}: {e}")
                errors += 1
        
        progress = (end / total_items) * 100
        logger.info(f"Copy progress: {progress:.1f}% ({end:,}/{total_items:,})")
        
        await asyncio.sleep(0.01)
    
    logger.info(f"Index copy completed: {copied:,} items copied, {errors} errors")
    return copied, errors
