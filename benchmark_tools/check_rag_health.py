#!/usr/bin/env python3
"""
Standalone script to check RAG system health.

Usage:
    python check_rag_health.py              # Full health check
    python check_rag_health.py --quick      # Quick check only
    python check_rag_health.py --json       # Output as JSON
"""
import asyncio
import sys
import json
import argparse


async def main():
    parser = argparse.ArgumentParser(description='Check RAG system health')
    parser.add_argument('--quick', action='store_true', help='Run quick check only')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--output', '-o', help='Save report to file')
    args = parser.parse_args()
    
    # Import after argument parsing to show help faster
    from rag_hq import run_health_check, quick_check
    
    if args.quick:
        print("Running quick health check...")
        result = await quick_check()
        if args.json:
            print(json.dumps({"status": "ok" if result else "error", "quick_check": result}))
        sys.exit(0 if result else 1)
    else:
        print("Running full health check...")
        result = await run_health_check()
        
        if args.json:
            print(json.dumps(result, indent=2))
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n📄 Report saved to: {args.output}")
        
        # Exit with error code if unhealthy
        sys.exit(0 if result['overall_status'] in ['healthy', 'degraded'] else 1)


if __name__ == "__main__":
    asyncio.run(main())
