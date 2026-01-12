"""
Main entry point for testing the RAG HQ module.

Usage:
    python -m rag_hq                    # Run test query
    python -m rag_hq --health          # Run health check
    python -m rag_hq --health --quick  # Quick health check
"""
import asyncio
import sys
from .initialization import initialize_rag, cleanup_rag
from .query import query_rag
from .health_check import run_health_check, quick_check


async def main():
    """Test the RAG module with a sample query or run health check."""
    
    # Check for health check flag
    if '--health' in sys.argv:
        if '--quick' in sys.argv:
            result = await quick_check()
            sys.exit(0 if result else 1)
        else:
            result = await run_health_check()
            sys.exit(0 if result['overall_status'] in ['healthy', 'degraded'] else 1)
    
    # Normal test mode
    print("=" * 60)
    print("RAG HQ TEST MODE")
    print("=" * 60)
    
    # Initialize
    await initialize_rag()
    
    # Test query
    test_query = "Tell me about the documents"
    print(f"\n🔍 Testing query: {test_query}")
    results = await query_rag(test_query, num_results=5)
    print(f"\n📊 Results:\n{results}\n")
    
    # Keep running to test periodic updates
    try:
        print("=" * 60)
        print("RAG module is running. Press Ctrl+C to stop...")
        print("Tip: Run 'python -m rag_hq --health' for health check")
        print("=" * 60)
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        await cleanup_rag()
        print("\n✓ Stopped gracefully")


if __name__ == "__main__":
    asyncio.run(main())
