import logging
import os
import asyncio
import time
import json
import uuid
from dotenv import load_dotenv

# CRITICAL: Load environment variables BEFORE importing config or other modules
# This ensures that config.py reads the correct values from .env
load_dotenv(override=True)

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.agents.llm import function_tool, ChatContext, ChatMessage, ChatChunk, FunctionTool
from livekit.agents import llm
from livekit.agents.voice import MetricsCollectedEvent
from livekit.agents import ModelSettings
from livekit.plugins import deepgram, openai, silero, elevenlabs, google
from livekit.plugins.elevenlabs.tts import TTS, VoiceSettings
from livekit.agents.llm import FallbackAdapter
from typing import AsyncIterable
#from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.plugins import noise_cancellation, inworld

# Import RAG modules
from rag_hq import query_rag, ensure_rag_initialized, enrich_with_rag as rag_enrich_with_rag
import rag_hq.initialization  # Import to access internal state flags
from rag_qa.query import query_qa_rag, ensure_qa_initialized, init_qa_rag

# Import RAG configuration
from config import (
    RAG_ENABLED, RAG_MODE, RAG_DEBUG_MODE, RAG_DEBUG_PRINT_FULL,
    RAG_NUM_RESULTS, RAG_CONTEXT_BUDGET_TOKENS, RAG_ROLLING_BUDGET,
    DOCUMENT_SERVER_ENABLED, DOCUMENT_SERVER_BASE_URL,
    RAG_QUERY_LOG_ENABLED, RAG_QUERY_LOG_FILE
)

# Import RAG query logger
from custom_components.rag_query_logger import RAGQueryLogger

# Import RAG orchestrator
from custom_components.rag_worker.rag_orchestrator import automatic_rag_enrichment

logger = logging.getLogger("rag-agent")
logger.setLevel(logging.INFO)
# logger.setLevel(logging.ERROR) # Re-enabling INFO logs for debugging

# Load API keys from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")

# RAG state tracking
rag_enabled = RAG_ENABLED
rag_initialized = False
qa_rag_initialized = False
rag_query_logger = None

def check_rag_enabled_hot():
    """
    Check environment variable RAG_ENABLED setting with hot-reloading.
    Reading from env vars is fast and allows runtime switching without file I/O.
    """
    # Reload environment variable from .env file to allow hot-switching via file edit
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    is_enabled = os.getenv("RAG_ENABLED", "false").lower() == "true"
    return is_enabled

# Custom FallbackAdapter met betere logging en preflight check
class SafeFallbackAdapter(FallbackAdapter):
    def __init__(self, models):
        # Set attempt_timeout to 15.0s to satisfy Gemini's 10s minimum deadline
        super().__init__(models, attempt_timeout=15.0)
        self.current_index = 0

    @property
    def current_model(self):
        return self.models[self.current_index].model

    async def safe_chat(self, chat_ctx, **kwargs):
        """Attempt chat on each model until one succeeds"""
        num_models = len(self.models)
        start_index = self.current_index
        for attempt in range(num_models):
            model = self.models[self.current_index]
            try:
                logger.info(f"Trying LLM [{self.current_index}]: {model.model}")
                # Using stream or chat call depending on API
                result_chunks = []
                async for chunk in model.stream(chat_ctx, **kwargs):
                    result_chunks.append(chunk)
                    yield chunk  # stream out
                logger.info(f"✓ LLM [{self.current_index}] succeeded: {model.model}")
                return  # success, exit
            except Exception as e:
                logger.error(
                    f"✗ LLM [{self.current_index}] failed: {model.model}\nError: {e}",
                    exc_info=True
                )
                # switch to next LLM
                self.current_index = (self.current_index + 1) % num_models
        # all LLMs failed
        logger.critical("‼️ All LLMs failed, no model available")
        raise RuntimeError("All LLMs unavailable")

    async def preflight_check(self):
        """Ping all models before starting sessions"""
        for i, model in enumerate(self.models):
            try:
                logger.info(f"Preflight: Testing LLM [{i}] {model.model}")
                # Set timeout to 15s to satisfy Gemini's 10s minimum requirement
                await model.chat("Ping test", settings=ModelSettings(timeout=15.0))
                logger.info(f"✓ LLM [{i}] reachable")
            except Exception as e:
                logger.warning(f"✗ LLM [{i}] failed preflight: {e}", exc_info=True)

# Instantiate safe fallback
fallback_llm = SafeFallbackAdapter(
    [
        google.LLM(
            model="gemini-3-flash-preview",
            api_key=GOOGLE_API_KEY,
        ),
        openai.LLM(
            model="llama-3.3-70b-versatile", # using this as a backup.
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        ),
        # openai.LLM(
        #     model="moonshotai/kimi-k2-instruct-0905",
        #     api_key=GROQ_API_KEY,
        #     base_url="https://api.groq.com/openai/v1",
        # ),
    ]
)

# Helper function to estimate token count
def estimate_tokens(text: str) -> int:
    """Estimate token count using word count and character-based heuristics."""
    import re
    if not text:
        return 0
    words = re.findall(r'\b\w+\b|\d+|[^\w\s]', text)
    special_chars = len(re.findall(r'\n|  +', text))
    estimated_tokens = int((len(words) * 1.3) + special_chars)
    return estimated_tokens


# RAG enrichment wrapper for LiveKit 1.0 Agent
async def automatic_rag_enrichment_wrapper(agent, chat_ctx: ChatContext):
    """Wrapper to call the automatic_rag_enrichment function with all required parameters"""
    logger.info("🔍 RAG_ENRICHMENT_WRAPPER - Starting RAG enrichment")
    try:
        await automatic_rag_enrichment(
            agent, chat_ctx,
            # RAG state
            rag_enabled=rag_enabled,
            rag_mode=RAG_MODE,
            qa_rag_initialized=qa_rag_initialized,
            rag_initialized=rag_initialized,
            # Query functions
            query_qa_rag_func=query_qa_rag,
            query_rag_func=query_rag,
            # Config values
            rag_num_results=RAG_NUM_RESULTS,
            rag_context_budget_tokens=RAG_CONTEXT_BUDGET_TOKENS,
            rag_rolling_budget=RAG_ROLLING_BUDGET,
            rag_debug_mode=RAG_DEBUG_MODE,
            rag_debug_print_full=RAG_DEBUG_PRINT_FULL,
            document_server_enabled=DOCUMENT_SERVER_ENABLED,
            document_server_base_url=DOCUMENT_SERVER_BASE_URL,
            # Helper functions
            estimate_tokens_func=estimate_tokens,
            rag_query_logger=rag_query_logger,
            llm_module=llm,  # Pass llm module for ChatMessage creation
            logger=logger
        )
        logger.info("✅ RAG_ENRICHMENT_WRAPPER - Completed successfully")
    except RuntimeError as e:
        # Handle event loop errors that can occur during timeouts
        if "Event loop" in str(e) or "closed" in str(e).lower():
            logger.warning(f"⚠️  RAG_ENRICHMENT_WRAPPER - Event loop error (likely timeout): {e}")
            # Reset HTTP session to prevent further issues
            try:
                from rag_hq.state import state
                if state.http_session:
                    state.http_session = None
                    state.http_session_pid = None
            except Exception:
                pass
        else:
            logger.error(f"❌ RAG_ENRICHMENT_WRAPPER - Runtime error: {e}", exc_info=True)
    except asyncio.TimeoutError:
        logger.warning("⚠️  RAG_ENRICHMENT_WRAPPER - Timeout error (RAG server too slow)")
        # Reset HTTP session to prevent "Unclosed client session" errors
        try:
            from rag_hq.state import state
            if state.http_session:
                state.http_session = None
                state.http_session_pid = None
        except Exception:
            pass
    except Exception as e:
        logger.error(f"❌ RAG_ENRICHMENT_WRAPPER - Error: {e}", exc_info=True)
        # Ensure worker doesn't crash - log and continue


# Import system instructions (hot-reloadable from text file)
from instructions import get_combined_instructions

# Create initial chat context
initial_chat_ctx = ChatContext.empty()


class MyAgent(Agent):
    def __init__(self, room: rtc.Room, user_id: str = "unknown", room_name: str = "unknown") -> None:
        # Hot-reload instructions from files each time agent is created
        instructions = get_combined_instructions()
        
        super().__init__(
            instructions=instructions,
            chat_ctx=initial_chat_ctx
        )
        
        self.room = room
        # Store metadata for RAG logging
        self.user_id = user_id
        self.room_name = room_name
        self.log_dir = os.getcwd()

    async def llm_node(
        self,
        chat_ctx: ChatContext,
        tools: list[FunctionTool],
        model_settings: ModelSettings,
    ) -> AsyncIterable[ChatChunk]:
        """Override LLM node to add RAG enrichment before LLM call"""
        global rag_enabled, rag_initialized, qa_rag_initialized
        
        # Hot-reload RAG_ENABLED setting from .env file
        rag_enabled = check_rag_enabled_hot()
        
        # Log the incoming chat context
        messages = getattr(chat_ctx, "messages", None)
        if messages is None:
            messages = getattr(chat_ctx, "items", [])
            
        if messages:
            last_msg = messages[-1]
            content_str = str(last_msg.content)
            # Clean up content string if it's a list representation
            if content_str.startswith("['") and content_str.endswith("']"):
                content_str = content_str[2:-2]
            logger.info(f"👤 User message: '{content_str}'")

        if rag_enabled:
            # Check for database updates on disk (Hot-Reload Index)
            try:
                from rag_hq.state import state
                from rag_hq.config import VECTOR_DB_PATH
                # Use absolute path to ensure we're looking at the right file
                abs_vdb_path = os.path.abspath(VECTOR_DB_PATH)
                if os.path.exists(abs_vdb_path):
                    disk_mtime = int(os.stat(abs_vdb_path).st_mtime)
                    if disk_mtime > state.last_db_modified_time:
                        logger.info(f"🔄 RAG database update detected: {disk_mtime} > {state.last_db_modified_time}")
                        await perform_rag_initialization()
                else:
                    logger.warning(f"⚠️ RAG hot-reload: File not found at {abs_vdb_path}")
            except Exception as e:
                logger.error(f"⚠️ Error checking for RAG database updates: {e}")

            # If RAG is enabled but systems aren't initialized, try initializing now
            if not rag_initialized and not qa_rag_initialized:
                logger.info("🔄 RAG toggled ON mid-session - Initializing...")
                await perform_rag_initialization()

            if rag_initialized or qa_rag_initialized:
                logger.info("🔍 LLM_NODE - Starting RAG enrichment")
                # Enrich chat context with RAG
                await automatic_rag_enrichment_wrapper(self, chat_ctx)
                logger.info("✅ LLM_NODE - RAG enrichment complete")
            else:
                logger.warning("⚠️ RAG enrichment skipped: Systems failed to initialize")
        else:
            logger.info("⏭️ LLM_NODE - RAG enrichment disabled, skipping")
        
        # Ensure timeout is at least 15s for Gemini (minimum allowed is 10s)
        if model_settings:
            model_settings.timeout = 15.0
            
        # Capture the full response to send it as a chat message
        full_response = ""
        msg_id = str(uuid.uuid4())
        last_publish_time = 0
        
        # Call the default LLM node with enriched context
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            # Collect text content for chat response
            content = None
            if isinstance(chunk, str):
                content = chunk
            elif hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content'):
                    content = delta.content
            elif hasattr(chunk, 'delta') and chunk.delta:
                if hasattr(chunk.delta, 'content'):
                    content = chunk.delta.content
            
            if content:
                full_response += content
                
                # Stream to chat every 100ms to avoid overwhelming the network
                current_time = time.time()
                if current_time - last_publish_time > 0.1:
                    try:
                        if self.room:
                            timestamp = int(current_time * 1000)
                            msg_payload = json.dumps({
                                "id": msg_id,
                                "message": full_response,
                                "timestamp": timestamp
                            })
                            await self.room.local_participant.publish_data(
                                payload=msg_payload,
                                topic="lk-chat-topic",
                                reliable=True
                            )
                            last_publish_time = current_time
                    except Exception:
                        pass # Ignore intermittent stream errors
            
            yield chunk
            
        logger.info(f"🤖 Agent response: '{full_response}'")
        
        # Final publish to ensure the complete message is received
        if full_response:
            try:
                # Use local participant to publish chat message
                if self.room:
                    # Frontend sends on 'lk-chat-topic' with JSON, so we respond in kind
                    timestamp = int(time.time() * 1000)
                    msg_payload = json.dumps({
                        "id": msg_id,
                        "message": full_response,
                        "timestamp": timestamp
                    })
                    
                    # Publish to the topic observed in debug logs ('lk-chat-topic')
                    await self.room.local_participant.publish_data(
                        payload=msg_payload,
                        topic="lk-chat-topic",
                        reliable=True
                    )
                    logger.info(f"💬 Published final response to chat")
                else:
                    logger.warning("⚠️ Cannot publish chat: Room not available")
            except Exception as e:
                logger.error(f"❌ Error publishing chat message: {e}")
        else:
            logger.warning("⚠️ No response generated to publish")

    async def on_enter(self):
        """Called when the agent enters the session"""
        logger.info("=== AGENT ON_ENTER - Starting ===")
        
        # Generate initial reply (RAG will be called automatically via llm_node)
        self.session.generate_reply()
        logger.info("✅ AGENT ON_ENTER - Completed")

def prewarm(proc: JobProcess):
    """Preload models and initialize RAG systems - RUNS ONCE before any jobs"""
    logger.info("=" * 60)
    logger.info("PREWARM: Initializing worker (runs once before jobs)")
    logger.info("=" * 60)
    
    # Log environment configuration
    logger.info("=" * 60)
    logger.info("ENVIRONMENT CONFIGURATION:")
    logger.info("=" * 60)
    livekit_url = os.getenv("LIVEKIT_URL", "NOT SET")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY", "NOT SET")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET", "NOT SET")
    eleven_api_key = os.getenv("ELEVEN_API_KEY", "NOT SET")
    groq_api_key = os.getenv("GROQ_API_KEY", "NOT SET")
    inworld_api_key = os.getenv("INWORLD_API_KEY", "NOT SET")
    
    # Mask secrets (show only first 8 chars)
    def mask_secret(value):
        if value == "NOT SET" or not value:
            return "NOT SET"
        return f"{value[:8]}..." if len(value) > 8 else "***"
    
    logger.info(f"LIVEKIT_URL: {livekit_url}")
    logger.info(f"LIVEKIT_API_KEY: {mask_secret(livekit_api_key)}")
    logger.info(f"LIVEKIT_API_SECRET: {mask_secret(livekit_api_secret)}")
    logger.info(f"ELEVEN_API_KEY: {mask_secret(eleven_api_key)}")
    logger.info(f"GROQ_API_KEY: {mask_secret(groq_api_key)}")
    logger.info(f"INWORLD_API_KEY: {mask_secret(inworld_api_key)}")
    logger.info("=" * 60)
    
    # No VAD model needed for text-only mode
    logger.info("ℹ️ TEXT_MODE active: VAD disabled")
    proc.userdata["vad"] = None
    
    # NOTE: RAG initialization moved to entrypoint() 
    # Each child process needs its own RAG initialization due to multiprocessing
    logger.info("=" * 60)
    logger.info("PREWARM: Skipping RAG init (will initialize in each child process)")
    logger.info(f"RAG MODE configured: {RAG_MODE}")
    logger.info("=" * 60)

async def perform_rag_initialization():
    """Core RAG initialization logic, can be called at startup or on-the-fly."""
    global rag_initialized, qa_rag_initialized
    
    logger.info(f"🔧 Process PID: {os.getpid()} - Performing RAG initialization")
    
    # FORCE RESET initialization state to ensure it runs
    rag_hq.initialization._is_initialized = False
    rag_hq.initialization._init_task = None
    
    # Check database files
    from rag_hq.config import VECTOR_DB_PATH, METADATA_PATH, VECTOR_DB_FOLDER
    
    # Check if files exist
    db_file_exists = os.path.exists(VECTOR_DB_PATH)
    meta_file_exists = os.path.exists(METADATA_PATH)
    map_file_path = VECTOR_DB_PATH + '.map'
    map_file_exists = os.path.exists(map_file_path)
    
    if not (db_file_exists and meta_file_exists and map_file_exists):
        logger.error("❌ REQUIRED DATABASE FILES ARE MISSING - Initialization aborted")
        return False, False
    
    # Initialize Chunk-based RAG if needed
    chunk_success = False
    if RAG_MODE in ["chunk", "both"]:
        try:
            await ensure_rag_initialized()
            from rag_hq.state import state
            if state.annoy_index is None:
                chunk_success = False
                logger.error("❌ RAG initialization completed but state.annoy_index is still None!")
            else:
                chunk_success = True
                logger.info("✓ Chunk RAG system initialized")
        except Exception as e:
            logger.error(f"✗ Error initializing Chunk RAG: {e}")
    
    # Initialize Q&A RAG if needed
    qa_success = False
    if RAG_MODE in ["qa", "both"]:
        try:
            init_qa_rag()
            qa_success = True
            logger.info("✓ Q&A RAG system initialized")
        except Exception as e:
            logger.error(f"✗ Error initializing Q&A RAG: {e}")
    
    # Update global flags
    if RAG_MODE == "chunk":
        rag_initialized = chunk_success
        qa_rag_initialized = False
    elif RAG_MODE == "qa":
        rag_initialized = False
        qa_rag_initialized = qa_success
    elif RAG_MODE == "both":
        rag_initialized = chunk_success
        qa_rag_initialized = qa_success
        
    return rag_initialized, qa_rag_initialized

async def entrypoint(ctx: JobContext):
    """Main entrypoint for each job - Initialize RAG in THIS child process"""
    
    # CRITICAL: Each child process needs its own RAG initialization
    # Multiprocessing creates fresh state - can't rely on parent process initialization
    global rag_initialized, qa_rag_initialized, rag_query_logger
    
    logger.info(f"🔧 Process PID: {os.getpid()} - Starting entrypoint")
    
    # Always initialize RAG systems in the child process.
    # The RAG_ENABLED switch in .env now only controls if it is used during chat enrichment.
    # This allows hot-switching ON instantly without waiting for init mid-session.
    await perform_rag_initialization()
    
    # Initialize RAG query logger
    log_dir = os.getcwd()
    log_file_path = os.path.join(log_dir, RAG_QUERY_LOG_FILE)
    rag_query_logger = RAGQueryLogger(log_file_path, enabled=RAG_QUERY_LOG_ENABLED)
    logger.info(f"✓ RAG query logging: {RAG_QUERY_LOG_ENABLED} → {log_file_path}")
    
    # Parse room info for user tracking
    room_name = ctx.room.name
    user_id = room_name.split("_")[0] if "_" in room_name else "unknown"
    
    # each log entry will include these fields
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "user_id": user_id,
    }

    logger.info("ℹ️ STARTING AGENT IN TEXT-ONLY MODE (Audio disabled)")
    # Configure session for text only
    # We only need to provide the LLM. VAD, STT, and TTS default to None.
    session = AgentSession(
        llm=fallback_llm,
    )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    # @session.on("metrics_collected")
    # def _on_metrics_collected(ev: MetricsCollectedEvent):
    #     metrics.log_metrics(ev.metrics)
    #     usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)

    # Create agent instance with metadata for RAG
    my_agent = MyAgent(room=ctx.room, user_id=user_id, room_name=room_name)
    logger.info("✅ Agent created with RAG enrichment via llm_node override")
    
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect()

    # DEBUG: Listen for raw data packets to verify connectivity
    @ctx.room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket):
        try:
            decoded = data_packet.data.decode('utf-8')
        except:
            decoded = f"<binary: {len(data_packet.data)} bytes>"
        logger.info(f"📨 RAW DATA RECEIVED - Topic: {data_packet.topic}, Payload: {decoded}")

    # Start the agent session
    await session.start(
        agent=my_agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # Disable audio input to prevent tracks being published/subscribed
            audio_enabled=False,
            text_enabled=True,  # Enable text/chat input support
        ),
        room_output_options=RoomOutputOptions(
            # Disable audio output to prevent tracks being published
            audio_enabled=False,
            # Disable transcription as we are doing chat manually
            transcription_enabled=False,
        ),
    )
    
    logger.info(f"Agent started for user {user_id} in room {room_name}")
    # text_enabled=True handles chat automatically - no custom handler needed

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, job_memory_warn_mb=1200,port=3007))
