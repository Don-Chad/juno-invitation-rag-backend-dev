# Project Overview: Juno The Invitation RAG Backend

This document provides a high-level overview of the services, directories, and key files involved in the Juno RAG backend project.

## System Services
The backend is managed via systemd services. The primary development service is:
- **Juno Worker (Dev)**: `juno-worker-dev.service`
  - **Port**: `3010` (internal AgentServer port)
  - **Main Script**: `agent_1_0_rag.py`
  - **Environment**: Managed via `.env` file in the project root.

## Project Structure & Key Files

### Root Directory
- `agent_1_0_rag.py`: The main entry point for the LiveKit agent. Handles session initialization, RAG enrichment, and chat publishing.
- `config.py`: Central configuration file for RAG settings, feature flags, and file paths.
- `instructions.py`: Manages the loading and hot-reloading of system prompts and instructions.
- `.env`: Contains API keys (Google, Groq, LiveKit) and feature toggles (RAG_ENABLED, etc.).

### `custom_components/`
This directory contains modular components used by the agent:
- `opener_manager.py`: Manages the initial greetings (openers) sent to new users. Currently uses a static list of curated Dutch openers.
- `firebase_user_manager.py`: Handles user authentication, session creation, and persistent chat history storage in Firestore.
- `memory_manager.py`: Responsible for extracting and storing "memories" from conversations to provide long-term user context.
- `rag_query_logger.py`: Logs all RAG queries and results to `rag_query_log.txt` for debugging and optimization.
- `rag_worker/`: Contains the logic for orchestrating RAG enrichment during the LLM generation process.

### `rag_hq/` & `rag_qa/`
These directories house the core RAG (Retrieval-Augmented Generation) engine:
- `rag_hq/`: Handles vector database operations, embeddings, and document retrieval.
- `rag_qa/`: Specialized logic for Q&A style RAG processing.

## Key Workflows
1. **Agent Entry (`on_enter`)**: When a user joins, the agent checks for history in Firebase. If new, it picks a random opener from `opener_manager.py`. If returning, it generates a warm reconnection greeting.
2. **RAG Enrichment**: Every user message triggers a RAG lookup (if enabled) via `automatic_rag_enrichment`. The retrieved context is injected into the LLM prompt.
3. **Chat Publishing**: Responses are streamed to the LiveKit room via the `lk-chat-topic` and simultaneously stored in Firebase for persistence.
