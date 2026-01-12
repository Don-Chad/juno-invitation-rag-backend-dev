"""
Error handling and retry logic for Q&A generation.
"""
import time
import asyncio
from typing import Callable, Any, Optional
from groq import RateLimitError, APIError, APIConnectionError


class RetryConfig:
    """Configuration for retry logic."""
    max_retries: int = 3
    initial_backoff: float = 1.0  # seconds
    max_backoff: float = 60.0  # seconds
    exponential_base: float = 2.0


async def retry_with_backoff(
    func: Callable,
    *args,
    retry_config: Optional[RetryConfig] = None,
    operation_name: str = "Operation",
    **kwargs
) -> tuple[Any, dict]:
    """
    Execute function with exponential backoff retry logic.
    
    Args:
        func: Async function to call
        *args: Function arguments
        retry_config: Optional retry configuration
        operation_name: Name for logging
        **kwargs: Function keyword arguments
    
    Returns:
        (result, metadata) where metadata includes retry info
    """
    if retry_config is None:
        retry_config = RetryConfig()
    
    last_error = None
    backoff = retry_config.initial_backoff
    
    for attempt in range(retry_config.max_retries):
        try:
            result = await func(*args, **kwargs)
            
            metadata = {
                'success': True,
                'attempts': attempt + 1,
                'total_backoff_time': sum(
                    retry_config.initial_backoff * (retry_config.exponential_base ** i) 
                    for i in range(attempt)
                )
            }
            
            if attempt > 0:
                print(f"✓ {operation_name} succeeded after {attempt + 1} attempts")
            
            return result, metadata
            
        except RateLimitError as e:
            last_error = e
            error_type = "Rate limit"
            print(f"⚠️  {error_type} hit on attempt {attempt + 1}/{retry_config.max_retries}")
            
        except APIConnectionError as e:
            last_error = e
            error_type = "Connection error"
            print(f"⚠️  {error_type} on attempt {attempt + 1}/{retry_config.max_retries}")
            
        except APIError as e:
            last_error = e
            error_type = "API error"
            print(f"⚠️  {error_type} on attempt {attempt + 1}/{retry_config.max_retries}: {str(e)[:100]}")
            
        except Exception as e:
            last_error = e
            error_type = "Unexpected error"
            print(f"⚠️  {error_type} on attempt {attempt + 1}/{retry_config.max_retries}: {str(e)[:100]}")
        
        # Don't sleep after last attempt
        if attempt < retry_config.max_retries - 1:
            sleep_time = min(backoff, retry_config.max_backoff)
            print(f"   Retrying in {sleep_time:.1f} seconds...")
            await asyncio.sleep(sleep_time)
            backoff *= retry_config.exponential_base
    
    # All retries exhausted
    metadata = {
        'success': False,
        'attempts': retry_config.max_retries,
        'error': str(last_error),
        'error_type': type(last_error).__name__
    }
    
    print(f"✗ {operation_name} failed after {retry_config.max_retries} attempts")
    print(f"   Final error: {str(last_error)[:200]}")
    
    return None, metadata

