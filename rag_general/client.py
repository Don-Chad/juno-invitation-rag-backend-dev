#!/usr/bin/env python3
import asyncio
import sys
import argparse
from rag_module import query_rag, initialize

async def run_query(query, num_results=3):
    """Run a query against the RAG database and print results."""
    print(f"Initializing RAG database...")
    await initialize()
    
    print(f"\nQuerying: '{query}'")
    print("-" * 60)
    
    results = await query_rag(query, num_results)
    
    print("\nResults:")
    print("-" * 60)
    print(results)
    print("-" * 60)

async def interactive_mode():
    """Run an interactive session to query the RAG database."""
    print("Initializing RAG database...")
    await initialize()
    print("\nRAG Query Client - Interactive Mode")
    print("Enter 'exit' or 'quit' to end the session")
    
    while True:
        try:
            query = input("\nEnter query: ")
            if query.lower() in ['exit', 'quit']:
                break
            
            num_results = 3
            if ' -n ' in query:
                query, num_part = query.split(' -n ', 1)
                try:
                    num_results = int(num_part.strip())
                except ValueError:
                    print(f"Invalid number of results, using default: {num_results}")
            
            results = await query_rag(query, num_results)
            
            print("\nResults:")
            print("-" * 60)
            print(results)
            print("-" * 60)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG Query Client")
    parser.add_argument("query", nargs="?", help="Query string for RAG database")
    parser.add_argument("-n", "--num-results", type=int, default=3, 
                        help="Number of results to return (default: 3)")
    parser.add_argument("-i", "--interactive", action="store_true", 
                        help="Run in interactive mode")
    
    args = parser.parse_args()
    
    if args.interactive:
        asyncio.run(interactive_mode())
    elif args.query:
        asyncio.run(run_query(args.query, args.num_results))
    else:
        parser.print_help()
        sys.exit(1)