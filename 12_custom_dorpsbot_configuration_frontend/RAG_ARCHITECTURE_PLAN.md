# RAG Architecture for Dorpsbot - Current State & Plan

## Current Backend Architecture (3 Separate Systems)

### 1. **rag_hq** - General Document RAG (PRIMARY SYSTEM)
- **Location**: `/home/mark/projects/10_livekit_server_dorpsbot_rag_backend/rag_hq/`
- **Source Folder**: `./docs/` (PDF, DOCX, TXT files)
- **Database**: `local_vector_db_enhanced/`
- **Purpose**: Semantic search over document chunks
- **Chunk Size**: 600 tokens with 25% overlap
- **How it works**: 
  - Watches `./docs/` folder every 30 seconds
  - Chunks documents into 600-token pieces
  - Creates embeddings and stores in Annoy index
  - Returns relevant chunks when queried

### 2. **rag_qa** - Auto-Generated Q&A System (SECONDARY)
- **Location**: `/home/mark/projects/10_livekit_server_dorpsbot_rag_backend/rag_qa/`
- **Source Folder**: `./docs/` (same as rag_hq)
- **Database**: `qa_vector_db/`
- **Purpose**: AI-generated Q&A pairs from documents
- **How it works**:
  - Uses Groq AI to generate questions from documents
  - Creates structured Q&A pairs (e.g., `Project Vuursche Energie_qa.json`)
  - Stores in separate vector database
  - Provides exact factual answers

### 3. **User FAQ System** - Manual Q&A (NEW - NEEDS SEPARATION!)
- **Current Implementation** (PROBLEM): 
  - Saves to `./docs/faq_knowledge_base.txt`
  - Gets mixed with regular documents in rag_hq ❌
- **What it should be**:
  - User-curated Q&A pairs entered through web interface
  - Should be kept separate or clearly tagged

---

## THE PROBLEM with Current Implementation

When I save FAQ to `./docs/faq_knowledge_base.txt`:
1. ✅ User enters FAQ in web UI
2. ❌ File goes to `./docs/` (same as regular documents)
3. ❌ `rag_hq` chunks it like a regular document
4. ❌ No way to distinguish user FAQ from document chunks
5. ❌ FAQ might get split across multiple chunks
6. ❌ No special handling for Q&A structure

---

## SOLUTION: Three Options

### Option A: Use rag_qa System for User FAQs (RECOMMENDED)
**Pros:**
- Reuse existing Q&A infrastructure
- FAQ treated as structured Q&A (not chunks)
- Separate database from documents
- Can prioritize FAQ answers

**Implementation:**
```
./docs/                          → rag_hq (document chunks)
./qa_vector_db/user_faq.json    → rag_qa (user FAQ)
./qa_vector_db/auto_generated/  → rag_qa (AI-generated Q&A)
```

**Backend Changes Needed:**
1. Modify `rag_qa/` to accept manual FAQ entries
2. Keep user FAQ separate from auto-generated Q&A
3. Query both systems: rag_qa (FAQ) + rag_hq (documents)

---

### Option B: Separate FAQ Folder with Metadata Tags
**Pros:**
- Simple implementation
- One RAG system (rag_hq)
- FAQ metadata for filtering

**Implementation:**
```
./docs/              → rag_hq (documents)
./docs/user_faq/     → rag_hq (FAQ with special metadata)
```

**Backend Changes Needed:**
1. Add folder-based metadata in rag_hq
2. Tag FAQ chunks with `source: "user_faq"`
3. Can optionally prioritize FAQ results

---

### Option C: Completely Separate FAQ System
**Pros:**
- Total isolation
- Custom FAQ matching logic
- No backend modifications to rag_hq or rag_qa

**Implementation:**
```
./docs/                    → rag_hq
./qa_vector_db/           → rag_qa
./faq_kb/                 → new FAQ system
```

**Backend Changes Needed:**
1. Create new `rag_faq/` module
2. Separate vector database
3. Query 3 systems in agent

---

## RECOMMENDED APPROACH: Option B (Metadata Tags)

This is the simplest and most practical:

### Backend Changes
1. **No changes to running backend** (keep livekit-dorpsbot-rag.service as-is)
2. **Add metadata filtering** to rag_hq (future enhancement)
3. Create subfolder: `./docs/user_faq/`
4. Each FAQ item saved as separate `.txt` file

### Frontend Changes  
1. Update `server.py` to save FAQ items to `./docs/user_faq/`
2. Each FAQ item = one file = one chunk
3. Add clear labels in UI explaining the difference

### File Structure
```
./docs/
├── document1.pdf              (Regular documents)
├── document2.docx
└── user_faq/                  (User-curated FAQ)
    ├── faq_001.txt            (QUESTION: ... ANSWER: ...)
    ├── faq_002.txt
    └── faq_003.txt
```

### How RAG Will Work
1. **User asks question** → Agent queries rag_hq
2. **rag_hq searches** all chunks (documents + FAQ)
3. **FAQ chunks** have consistent Q&A format
4. **Agent sees** both document context AND FAQ answers
5. **One retrieval call** (no complexity)

---

## What the User Sees (Frontend UI)

### Tab 1: Character Configuration
- Configure personality, system prompts, etc.

### Tab 2: RAG Documents  
**Purpose**: Upload reference documents (PDFs, reports, policies)
- Upload files → Goes to `./docs/`
- These become **searchable knowledge chunks**
- Example: "Project Vuursche Energie.pdf"

### Tab 3: FAQ (User-Curated)
**Purpose**: Direct Q&A pairs that you write yourself
- Add question + answer pairs
- Saved to `./docs/user_faq/`
- These are **direct answers** in Q&A format
- Example: "How do I apply?" → "Fill out the form at..."

**Key Difference Explained in UI:**
- 📄 **Documents**: The AI finds relevant passages and synthesizes answers
- ❓ **FAQ**: Direct Q&A pairs you provide - exact answers

---

## Next Steps

1. ✅ Update `server.py` to save FAQ to `./docs/user_faq/`
2. ✅ Update `FAQManager.tsx` to clarify purpose
3. ✅ Add explanatory text in UI
4. ⏳ (Future) Add metadata filtering to rag_hq for FAQ prioritization
5. ⏳ (Future) Add FAQ-first routing in agent logic

---

## Summary

- **rag_hq**: Your main system, handles both documents and FAQ (with folder separation)
- **rag_qa**: Auto-generated Q&A from documents (runs separately)
- **User FAQ**: Manual Q&A saved to `./docs/user_faq/` subfolder
- **No backend changes needed** - just organized file structure
- **Agent queries one system** - simple and fast
