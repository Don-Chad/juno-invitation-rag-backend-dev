# Dorpsbot RAG Architecture - Implementation Summary

## ✅ What We Built

A configuration interface for Dorpsbot with **3 separate knowledge sources** that work together:

---

## 📊 The Three Knowledge Systems

### 1. **General Documents** (Tab: "RAG Documents")
- **Location**: `/home/mark/projects/10_livekit_server_dorpsbot_rag_backend/docs/`
- **Files**: PDF, DOCX, TXT documents
- **How it works**: 
  - rag_hq chunks documents into 600-token pieces
  - AI searches and **synthesizes answers** from passages
  - Example: Upload "Project Vuursche Energie.pdf" → AI can answer questions about the project
- **UI**: Upload, view, delete documents
- **Ingestion**: Automatic every 30 seconds by rag_hq

### 2. **User FAQ** (Tab: "FAQ") ✨ NEW
- **Location**: `/home/mark/projects/10_livekit_server_dorpsbot_rag_backend/docs/user_faq/`
- **Files**: Individual `.txt` files (one per FAQ item)
- **How it works**:
  - Each Q&A pair is saved as a separate file
  - Each file = one RAG chunk (not split)
  - AI retrieves your **exact answers**
  - Example: "How do I apply?" → "Fill out form at..."
- **UI**: Add/edit/delete Q&A pairs with categories
- **Ingestion**: Automatic (same rag_hq system, but separate folder)

### 3. **Auto-Generated Q&A** (Backend only - not exposed in UI)
- **Location**: `/home/mark/projects/10_livekit_server_dorpsbot_rag_backend/qa_vector_db/`
- **How it works**: AI reads documents and generates Q&A pairs automatically
- **Not managed through this interface** (runs separately)

---

## 🔄 How RAG Query Works

When a user asks Dorpsbot a question:

```
1. User: "How do I join the cooperative?"

2. rag_hq searches ALL chunks:
   ✓ General documents (./docs/*.pdf)
   ✓ User FAQ (./docs/user_faq/*.txt)

3. Returns top 3-5 most relevant chunks (might include both sources)

4. Agent receives context and formulates answer
```

**Key Point**: It's **one unified search** across both documents and FAQ. The folder separation is organizational, not functional (yet).

---

## 🎨 Frontend Features

### Tab 1: Character Configuration
- System prompts, personality, conversation settings
- (Existing functionality retained)

### Tab 2: RAG Documents
- **Purpose**: Reference materials for AI to interpret
- Upload PDF/DOCX/TXT files
- View loaded documents with sizes and dates
- Delete unwanted files
- Live system health indicator
- Duplicate file warning

### Tab 3: FAQ Knowledge Base
- **Purpose**: Direct Q&A pairs you provide
- Add question/answer pairs with categories
- Search through existing FAQ items
- Rollback unsaved changes
- Individual file-per-item storage

---

## 🔧 Technical Implementation

### Backend Proxy (`server.py`)
- FastAPI service on port 3001
- Provides REST API for:
  - `/api/documents` - List, upload, delete documents
  - `/api/faq` - Get, save FAQ items
  - `/api/health` - RAG system health check
- **No changes to rag_hq backend** - only file system operations

### Frontend (Vite + React)
- Port 3004
- Proxies API calls to backend (port 3001)
- Three-tab interface
- Real-time document polling (every 10s)

### Service Architecture
```
systemd: dorpsbot-config.service
  ├─ start-service.sh
  │   ├─ server.py (port 3001) ← Backend proxy
  │   └─ npm run preview (port 3004) ← Frontend
  │
  └─ Proxies /api → localhost:3001
```

---

## 📁 File Structure After Setup

```
/home/mark/projects/10_livekit_server_dorpsbot_rag_backend/
├── docs/
│   ├── document1.pdf              ← General documents (RAG Documents tab)
│   ├── document2.docx
│   ├── report.pdf
│   └── user_faq/                  ← User FAQ (FAQ tab)
│       ├── _faq_metadata.json     ← Master FAQ list
│       ├── faq_001.txt            ← "How do I apply?"
│       ├── faq_002.txt            ← "What are the costs?"
│       └── faq_003.txt            ← "When is the meeting?"
│
├── local_vector_db_enhanced/      ← RAG database (both sources)
│   ├── vdb_data                   ← Vector index
│   ├── metadata.pkl               ← Chunk metadata
│   └── ...
│
└── qa_vector_db/                  ← Auto-generated Q&A (separate system)
    └── dev_outputs/
        └── *.qa.json
```

---

## 🚀 Users & Access

**Created via `/init-user` page:**

1. **Standard User**
   - Email: `focabaas@gmail.com`
   - Password: `945hasfkl034ok%`
   - Can configure character, upload documents, manage FAQ

2. **Admin User**
   - Email: `mark@dopamine.amterdam`
   - Password: `jsdfkksfd405al`
   - Full access (no difference in current UI, but role marked)

---

## ⚙️ Installation Commands

```bash
# Build the frontend
cd /home/mark/projects/12_custom_dorpsbot_configuration_frontend/pulse-robot-template-57736-32260
npm run build

# Install the systemd service
sudo cp dorpsbot-config.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dorpsbot-config
sudo systemctl start dorpsbot-config

# Check status
sudo systemctl status dorpsbot-config

# View logs
sudo journalctl -u dorpsbot-config -f
```

---

## 🔮 Future Enhancements (Not Implemented Yet)

### Priority Handling
- FAQ results could be prioritized over document chunks
- Requires agent logic changes

### Metadata Filtering
- Tag FAQ chunks with `source: "user_faq"`
- Allow filtering by source type
- Requires rag_hq backend modifications

### Separate FAQ System
- Dedicated FAQ retrieval with exact matching
- Would query both rag_hq and FAQ system
- More complex but more control

---

## 📝 Summary

**What changed:**
- ✅ Frontend now has 3 tabs: Character / Documents / FAQ
- ✅ FAQ items saved to separate folder: `docs/user_faq/`
- ✅ Each FAQ item = one file = one RAG chunk
- ✅ Clear UI labels explaining difference between Documents and FAQ
- ✅ Backend proxy (server.py) to interface with RAG file system
- ✅ User initialization page for creating accounts
- ✅ System health monitoring
- ✅ Duplicate file warnings

**What stayed the same:**
- ✅ No changes to rag_hq backend code
- ✅ No changes to running livekit-dorpsbot-rag.service
- ✅ Same ingestion process (rag_hq monitors docs/ folder)
- ✅ Same vector database (both sources in one index)

**Result:**
- Users can now upload documents AND curate FAQ through one interface
- Both sources are searchable by the AI
- Clean separation of concerns
- No backend disruption
