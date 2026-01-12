#!/usr/bin/env python3
"""
Real-time Embedding Performance Monitor

This script monitors embedding generation performance in real-time
to help identify when and why performance degrades.
"""

import asyncio
import time
import aiohttp
import statistics
from datetime import datetime
from collections import deque

# Configuration
LLAMA_SERVER_URL = "http://localhost:7777/embedding"
MONITOR_INTERVAL = 1  # seconds between tests
HISTORY_SIZE = 20  # number of recent measurements to keep

class PerformanceMonitor:
    def __init__(self):
        self.history = deque(maxlen=HISTORY_SIZE)
        self.baseline = None
        
    async def measure_performance(self):
        """Measure current embedding performance."""
        test_texts = [
            "Short query",
            "Medium length query with more words",
            "This is a longer query to test performance scaling"
        ]
        
        measurements = []
        
        async with aiohttp.ClientSession() as session:
            for text in test_texts:
                start = time.perf_counter()
                try:
                    async with session.post(
                        LLAMA_SERVER_URL,
                        json={"content": text, "embedding": True},
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        await response.json()
                        elapsed = (time.perf_counter() - start) * 1000
                        measurements.append(elapsed)
                except Exception as e:
                    print(f"Error: {e}")
                    return None
        
        return statistics.mean(measurements) if measurements else None
    
    async def monitor(self):
        """Run continuous monitoring."""
        print("Starting embedding performance monitor...")
        print("Press Ctrl+C to stop\n")
        
        while True:
            try:
                # Measure performance
                perf = await self.measure_performance()
                
                if perf is not None:
                    self.history.append(perf)
                    
                    # Set baseline on first measurement
                    if self.baseline is None:
                        self.baseline = perf
                    
                    # Calculate statistics
                    avg = statistics.mean(self.history)
                    if len(self.history) > 1:
                        std = statistics.stdev(self.history)
                        min_val = min(self.history)
                        max_val = max(self.history)
                    else:
                        std = 0
                        min_val = max_val = perf
                    
                    # Display results
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    change = ((perf - self.baseline) / self.baseline * 100) if self.baseline else 0
                    
                    # Color coding for terminal
                    if change > 50:
                        status = "🔴"  # Red - significant slowdown
                    elif change > 20:
                        status = "🟡"  # Yellow - moderate slowdown
                    else:
                        status = "🟢"  # Green - normal
                    
                    print(f"[{timestamp}] {status} Current: {perf:.1f}ms | "
                          f"Avg: {avg:.1f}ms | Range: {min_val:.1f}-{max_val:.1f}ms | "
                          f"Change from baseline: {change:+.1f}%")
                    
                    # Alert on significant degradation
                    if change > 100:
                        print("⚠️  WARNING: Performance degraded by more than 100%!")
                
                # Wait before next measurement
                await asyncio.sleep(MONITOR_INTERVAL)
                
            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
                break
            except Exception as e:
                print(f"Monitor error: {e}")
                await asyncio.sleep(MONITOR_INTERVAL)

async def main():
    monitor = PerformanceMonitor()
    await monitor.monitor()

if __name__ == "__main__":
    asyncio.run(main()) 