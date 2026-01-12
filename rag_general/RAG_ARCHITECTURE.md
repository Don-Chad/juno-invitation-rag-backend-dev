# RAG System Architecture for LiveKit Workers

## The Problem: Process-Per-Call Architecture

### How LiveKit Workers Work:

```
┌──────────────────────────────────────────────────────────┐
│  MAIN WORKER PROCESS (Parent)                            │
│  - Starts once when worker launches                      │
│  - Runs prewarm() function ONCE                          │
│  - Waits for calls                                       │
└──────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   ┌────────┐       ┌────────┐      ┌────────┐
   │ Call 1 │       │ Call 2 │      │ Call 3 │
   │Process │       │Process │      │Process │
   └────────┘       └────────┘      └────────┘
   entrypoint()     entrypoint()    entrypoint()
```

### The Problem (OLD WAY):

If we initialize RAG in `entrypoint()`:

```python
async def entrypoint(ctx: JobContext):
    await initialize_rag_system()  # ❌ BAD!
    # ...rest of call handling
```

**This causes:**
- ❌ Each call loads the ENTIRE database into memory
- ❌ Each call might try to ingest documents
- ❌ 3 calls = 3x memory usage for the same data!
- ❌ Slow startup for every single call
- ❌ Potential race conditions if multiple calls ingest at once

**Example:**
```
Call 1: Loads 500MB RAG database into memory
Call 2: Loads 500MB RAG database into memory (duplicate!)
Call 3: Loads 500MB RAG database into memory (duplicate!)
Total: 1.5GB for the same data! ❌
```

## The Solution: Initialize in Prewarm

### The Correct Way:

Initialize RAG in `prewarm()` - runs ONCE in parent process:

```python
def prewarm(proc: JobProcess):
    """Runs ONCE when worker starts"""
    # Load models
    proc.userdata["vad"] = silero.VAD.load()
    
    # Initialize RAG ONCE here
    rag_success = asyncio.run(ensure_rag_initialized())
    proc.userdata["rag_initialized"] = rag_success
```

Then in `entrypoint()`, just CHECK if it's ready:

```python
async def entrypoint(ctx: JobContext):
    """Runs for EACH call"""
    # Just check if RAG is ready (no re-initialization!)
    rag_initialized = ctx.proc.userdata.get("rag_initialized", False)
    
    if rag_initialized:
        logger.info("✓ RAG ready - using parent process database")
    # ...rest of call handling
```

### Benefits:

```
PARENT PROCESS (prewarm):
  Loads 500MB RAG database ONCE ✓

CHILD PROCESSES (calls):
  Call 1: Uses parent's RAG (shared memory)
  Call 2: Uses parent's RAG (shared memory)  
  Call 3: Uses parent's RAG (shared memory)
  
Total: 500MB for all calls! ✓
```

**Advantages:**
- ✅ Database loaded ONCE, shared by all calls
- ✅ Document ingestion happens ONCE
- ✅ Fast call startup (no database loading)
- ✅ Efficient memory usage
- ✅ No race conditions
- ✅ RAG always ready before any call arrives

## Process Flow

### 1. Worker Startup (ONCE):
```
[Worker Starts]
      ↓
[prewarm() runs]
      ↓
[Load VAD model]
      ↓
[Initialize RAG system] ← THIS IS WHERE RAG LOADS
      ↓
  - Load vector database
  - Load metadata
  - Load embeddings cache
  - Start periodic update task
      ↓
[RAG Ready - mark in proc.userdata]
      ↓
[Wait for calls...]
```

### 2. Call Arrives (PER CALL):
```
[Call 1 arrives]
      ↓
[Spawn new process]
      ↓
[entrypoint() runs]
      ↓
[Check proc.userdata["rag_initialized"]] ← Just CHECK, don't load!
      ↓
[Use RAG for context enrichment]
      ↓
[Handle conversation]
      ↓
[Call ends, process dies]

[RAG in parent process continues running]
```

## Code Changes Made

### 1. Modified `prewarm()` in `worker_agent_helpers_new.py`:

**Before:**
```python
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
    # That's it
```

**After:**
```python
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
    
    # NEW: Initialize RAG ONCE in parent process
    from rag_hq import ensure_rag_initialized
    
    async def _init_rag():
        await ensure_rag_initialized()
        return True
    
    rag_success = asyncio.run(_init_rag())
    proc.userdata["rag_initialized"] = rag_success
```

### 2. Modified `entrypoint()` in `agent_dev.py`:

**Before:**
```python
async def entrypoint(ctx: JobContext):
    # Initialize RAG for this call
    await initialize_rag_system()  # ❌ Loads database every call!
    
    # ...rest of code
```

**After:**
```python
async def entrypoint(ctx: JobContext):
    # Just check if RAG is ready (initialized in parent)
    global rag_initialized
    rag_initialized = ctx.proc.userdata.get("rag_initialized", False)
    
    if rag_initialized:
        logger.info("✓ RAG ready (from parent process)")
    
    # ...rest of code - RAG is ready to use!
```

## What You'll See in Logs

### At Worker Startup (prewarm):
```
============================================================
PREWARM: Initializing worker (runs once before calls)
============================================================
============================================================
PREWARM: Initializing RAG system (ONCE for all calls)
============================================================
🔍 RAG | 10:30:15 | INFO | INITIALIZING ENHANCED RAG MODULE
🔍 RAG | 10:30:16 | INFO | ✓ Successfully loaded vector database:
🔍 RAG | 10:30:16 | INFO |   - 1,234 vectors in index
🔍 RAG | 10:30:17 | INFO | ✅ RAG MODULE FULLY OPERATIONAL
✓ RAG system initialized successfully in prewarm
  All spawned call processes will share this RAG instance
============================================================
PREWARM: Complete (RAG: ✓ Ready)
============================================================
```

### At Each Call (entrypoint):
```
✓ RAG system ready (initialized in parent process)
[...rest of call handling...]
```

**Notice:**
- No database loading messages during calls
- No "INITIALIZING RAG" during calls
- Just a quick "ready" check

## Key Points

1. **prewarm() = Parent Process = RAG Initialization**
   - Runs ONCE when worker starts
   - Loads database ONCE
   - All calls share this instance

2. **entrypoint() = Child Process = RAG Usage**
   - Runs for EACH call
   - Just uses the already-loaded RAG
   - No re-initialization

3. **Memory Efficiency**
   - Old way: N calls × 500MB = 1.5GB+ 
   - New way: 1 × 500MB = 500MB (shared)

4. **Document Ingestion**
   - Happens in parent process (prewarm)
   - Only ONE process tries to ingest at a time
   - No race conditions

5. **Performance**
   - Calls start instantly (no database loading wait)
   - RAG always ready before first call arrives

## Testing

To verify it's working correctly:

```bash
# Start worker
python agent_dev.py start

# Look for prewarm logs:
# "PREWARM: Initializing RAG system (ONCE for all calls)"
# "✓ RAG system initialized successfully in prewarm"

# Then make a call and look for:
# "✓ RAG system ready (initialized in parent process)"
# (NOT "INITIALIZING RAG MODULE" during the call!)
```

## Troubleshooting

### If RAG not initializing:
1. Check prewarm logs for errors
2. Verify llama-server is running
3. Check `./docs/` folder has documents

### If each call seems to reload RAG:
- ❌ You're initializing in entrypoint() instead of prewarm()
- ✅ Move initialization to prewarm()

### If memory usage is high:
- Check how many concurrent calls you have
- Each call uses some memory, but they share the RAG database
- Main memory is in the parent process

## Summary

```
OLD (Wrong):
  prewarm():     Load VAD
  entrypoint():  Load RAG ❌  (every call!)
  Result:        Multiple database copies in memory

NEW (Correct):
  prewarm():     Load VAD + Load RAG ✓  (once!)
  entrypoint():  Check RAG ready ✓  (just check!)
  Result:        One database, all calls share it
```

**The key insight:** LiveKit spawns processes per call, so we must initialize shared resources (like RAG) in the parent process (prewarm), not in the per-call handler (entrypoint).
