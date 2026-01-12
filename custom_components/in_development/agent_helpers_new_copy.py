import logging
import os
import sys
import re
import os
import json
from datetime import datetime
from distutils.util import strtobool
from livekit.plugins import silero, openai#, rag
from livekit.agents import JobProcess, llm
from pathlib import Path
from custom_components.worker_character_configs import CHARACTER_CONFIGS
from livekit.agents.tokenize.basic import WordTokenizer
import pickle
import time
from custom_components.stop_words import STOP_WORDS
import asyncio
#from custom_components.setup_logging import setup_logging
from custom_components.config import DEV_MODE, SPEAKER_OVERRIDE, LOGGING_LEVEL

RAG = False  # Global switch for RAG functionality


def setup_logging():
    """Setup logging to console only"""
    # Set root logger to config level
    root_logger = logging.getLogger()
    root_logger.setLevel(LOGGING_LEVEL if 'LOGGING_LEVEL' in globals() else logging.DEBUG)
    
    # Set voice-agent logger
    logger = logging.getLogger("voice-agent")
    logger.setLevel(LOGGING_LEVEL if 'LOGGING_LEVEL' in globals() else logging.DEBUG)
    
    # Set livekit.agents logger to same level
    livekit_logger = logging.getLogger("livekit.agents")
    livekit_logger.setLevel(LOGGING_LEVEL if 'LOGGING_LEVEL' in globals() else logging.DEBUG)
    
    class MetricsFilter(logging.Filter):
        def filter(self, record):
            return not record.getMessage().startswith("Pipeline STT metrics:")
    
    class DuplicateFilter(logging.Filter):
        """Filter out duplicate log messages."""
        def __init__(self):
            super().__init__()
            self.last_log = None

        def filter(self, record):
            current_log = (record.levelno, record.getMessage())
            if current_log != self.last_log:
                self.last_log = current_log
                return True
            return False
    
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(detailed_formatter)
    console_handler.setLevel(LOGGING_LEVEL if 'LOGGING_LEVEL' in globals() else logging.DEBUG)
    
    # Add filters to the logger
    livekit_logger.addFilter(MetricsFilter())
    logger.addFilter(DuplicateFilter())
    
    # Check if the handler already exists
    if not any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers):
        logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

def prewarm(proc: JobProcess):
    """Preload models and initialize components"""
    proc.userdata["vad"] = silero.VAD.load()
    
    from custom_components.worker_character_configs import CHARACTER_CONFIGS
    proc.userdata["character_configs"] = CHARACTER_CONFIGS
    
    # Add: Pre-initialize logging
    logger = setup_logging()
    proc.userdata["logger"] = logger
    
    try:
        import custom_components.worker_system_text as worker_system_text
        proc.userdata["system_text"] = worker_system_text
    except ImportError as e:
        logger.error(f"Failed to preload system_text: {e}")

    # Load the Annoy index and paragraph data
    try:
        embeddings_dimension = 1536
        annoy_index = rag.annoy.AnnoyIndex.load("vdb_data")
        with open("vdb_data\metadata.pkl", "rb") as f:
            paragraphs_by_uuid = pickle.load(f)
        proc.userdata["annoy_index"] = annoy_index
        proc.userdata["paragraphs_by_uuid"] = paragraphs_by_uuid
    except Exception as e:
        logger.error(f"Failed to preload Annoy index or paragraph data: {e}")

def parse_room_info(room_name: str, logger: logging.Logger) -> tuple[str, str]:
    """Parse room name to extract user ID and speaker name."""
    # Now just use DEV_MODE directly from config
    if DEV_MODE:
        dev_room = "room::RYDZFr2zpXezXdOYO45qE8PoGsm2::tesla::7ea263f4-8204-4d91-92dd-c871ca440155"
        logger.info("Running in dev mode - using Tesla configuration with persistent room")
        parts = dev_room.split('::')
        
        # Use SPEAKER_OVERRIDE if defined, otherwise fallback to "terence"
        speaker = SPEAKER_OVERRIDE if 'SPEAKER_OVERRIDE' in globals() else "terence"
        logger.info(f"Using speaker: {speaker} in dev mode")
        
        return parts[1], speaker

    try:
        if room_name.startswith('room::'):
            parts = room_name.split('::')
            if len(parts) >= 3:
                user_id = parts[1]
                speaker = parts[2].lower()
                
                logger.info(f"Parsed speaker name: {speaker}")
                logger.info(f"Available configs: {list(CHARACTER_CONFIGS.keys())}")
                logger.info(f"Normalized configs: {list({k.lower(): k for k in CHARACTER_CONFIGS}.keys())}")
                
                normalized_configs = {k.lower(): k for k in CHARACTER_CONFIGS}
                if speaker not in normalized_configs:
                    logger.warning(f"Invalid speaker name: {speaker}, using terence")
                    return user_id, "terence"

                return user_id, normalized_configs[speaker] 

        if room_name.startswith('playground-'):
            logger.warning(f"Legacy room name format: {room_name}")
            return create_unidentified_session()

        logger.warning(f"Invalid room name format: {room_name}")
        return create_unidentified_session()

    except Exception as e:
        logger.error(f"Error parsing room name: {e}")
        return create_unidentified_session()

def create_unidentified_session() -> tuple[str, str]:
    """Create a unique session ID for unidentified users"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"UNIDENTIFIED_{timestamp}"
    return session_id, "tesla" # default is terence

def get_base_log_dir():
    """Get the base logging directory"""
    if DEV_MODE:
        # Development mode: Use current working directory
        base_dir = os.path.join(os.getcwd(), "tmp", "dev_logs")
    else:
        # Production mode: Use /tmp
        base_dir = os.path.join("/tmp", "voice_agent_logs")
    
    os.makedirs(base_dir, exist_ok=True)
    return base_dir

def setup_log_directory(user_id: str) -> str:
    """Setup and return the path to the user's log directory"""
    base_dir = get_base_log_dir()
    
    if DEV_MODE:
        return base_dir
    
    # For production, create user-specific directories
    if user_id.startswith("UNIDENTIFIED"):
        user_dir = os.path.join(base_dir, "unidentified", user_id)
    else:
        user_dir = os.path.join(base_dir, "identified", user_id)
    
    # Create subdirectories
    for subdir in ["chat", "costs"]:
        full_path = os.path.join(user_dir, subdir)
        os.makedirs(full_path, exist_ok=True)
    
    return user_dir

def estimate_tokens(text: str) -> int:
    """Estimate token count using word count and character-based heuristics."""
    if not text:
        return 0
        
    words = re.findall(r'\b\w+\b|\d+|[^\w\s]', text)
    special_chars = len(re.findall(r'\n|  +', text))
    estimated_tokens = int((len(words) * 1.3) + special_chars)
    
    return estimated_tokens

def ensure_directory_permissions(path: str):
    """Ensure directory exists and has correct permissions"""
    try:
        os.makedirs(path, exist_ok=True)
        os.chmod(path, 0o755)
    except PermissionError as e:
        logger.error(f"Permission error creating directory {path}: {e}")
        fallback_path = os.path.join("/tmp", os.path.basename(path))
        os.makedirs(fallback_path, exist_ok=True)
        return fallback_path
    return path 

# # Load the Annoy index and paragraph data
# annoy_index = rag.annoy.AnnoyIndex.load("vdb_data")
# embeddings_dimension = 1536
# with open("my_data.pkl", "rb") as f:
#     paragraphs_by_uuid = pickle.load(f)

# async def load_rag_augmentation(chat_ctx: llm.ChatContext, logger: logging.Logger):
#     """Load RAG augmentation for the chat context."""
#     start_time = time.time()
#     embeddings_dimension = 1536
    
#     # Initialize Annoy index and paragraph data
#     try:
#         annoy_index = rag.annoy.AnnoyIndex.load("vdb_data")
#         with open("vdb_data/metadata.pkl", "rb") as f:
#             paragraphs_by_uuid = pickle.load(f)
        
#         # Log the type of paragraphs_by_uuid to ensure it's a dictionary
#         logger.info(f"Type of paragraphs_by_uuid: {type(paragraphs_by_uuid)}")
        
#     except Exception as e:
#         logger.error(f"Failed to load Annoy index or paragraph data: {e}")
#         return
    
#     try:
#         # Locate the last user message and use it to query the RAG model
#         user_msg = chat_ctx.messages[-1]
        
#         # Measure time for embedding creation
#         embedding_start_time = time.time()
#         user_embedding = await openai.create_embeddings(
#             input=[user_msg.content],
#             model="text-embedding-3-small",
#             dimensions=embeddings_dimension,
#         )
#         logger.info(f"Embedding creation took {time.time() - embedding_start_time:.2f} seconds")
        
#         if not user_embedding or not user_embedding[0].embedding:
#             logger.error("Failed to receive embedding from OpenAI")
#             return
        
#         # Query the Annoy index
#         result = annoy_index.query(user_embedding[0].embedding, n=1)[0]
        
#         # Access the correct attribute from the result
#         paragraph_uuid = result.userdata  # Ensure this is the correct attribute
        
#         # Use a method or attribute to access the paragraph from _FileData
#         paragraph = paragraphs_by_uuid.get_paragraph_by_uuid(paragraph_uuid)  # Hypothetical method
        
#         if paragraph:
#             logger.info(f"Enriching with RAG: {paragraph}")
#             rag_msg = llm.ChatMessage.create(
#                 text="Context:\n" + paragraph,
#                 role="assistant",
#             )
#             # Replace last message with RAG, and append user message at the end
#             chat_ctx.messages[-1] = rag_msg
#             chat_ctx.messages.append(user_msg)
#         else:
#             logger.warning("No paragraph found for the given embedding result")
    
#     except Exception as e:
#         logger.error(f"Error during RAG augmentation: {e}")
    
#     logger.info(f"RAG augmentation completed in {time.time() - start_time:.2f} seconds")

async def handle_final_transcript_event(assistant, chat_ctx: llm.ChatContext):
    """Handle the final transcript event and check for stop words."""
    # Initialize buffer for processed words
    if not hasattr(assistant, '_processed_words_buffer'):
        assistant._processed_words_buffer = []
        print("[Transcription] Initialized processed words buffer")

    new_transcript = chat_ctx.messages[-1].content if chat_ctx.messages else ""
    if not new_transcript:
        logger.error("Received empty transcript in final_transcript event")
        return
    
    print(f"[Transcription] Processing new message: {new_transcript}")
    print(f"[Transcription] DEV_MODE is: {DEV_MODE}")
    
    # Save transcript
    try:
        base_dir = get_base_log_dir()
        transcripts_dir = os.path.join(base_dir, "transcripts")
        os.makedirs(transcripts_dir, exist_ok=True)
        
        log_file = os.path.join(transcripts_dir, 'transcription.log')
        print(f"[Transcription] Writing to log file: {log_file}")
        
        # Check if this is the first entry
        is_first_entry = not os.path.exists(log_file) or os.path.getsize(log_file) == 0
        
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if is_first_entry:
                f.write(f"=== New Transcription Session Started at {timestamp} ===\n")
                print("[Transcription] Created new transcription session")
                
            log_entry = f"[{timestamp}] {new_transcript}\n"
            f.write(log_entry)
            print(f"[Transcription] Successfully wrote transcript: {new_transcript[:30]}...")
            
    except Exception as e:
        print(f"[Transcription] Failed to write transcript: {str(e)}")
        logger.error(f"Failed to write transcript: {e}")

async def debug_and_truncate_context(assistant, chat_ctx: llm.ChatContext):
    """Debug and truncate context before sending to LLM."""
    start_time = time.time()
    
    await handle_final_transcript_event(assistant, chat_ctx)
    
    if RAG:
        await load_rag_augmentation(chat_ctx, logger)
        print(f"RAG augmentation loaded in {time.time() - start_time:.2f} seconds")
    
    # Initialize the tokenizer
    tokenizer = WordTokenizer(ignore_punctuation=True)
    
    # Always truncate if the total token count exceeds 6000
    max_tokens = 6000
    initial_system_prompt = chat_ctx.messages[0]  # Assuming the first message is the system prompt
    truncated_messages = [initial_system_prompt] + chat_ctx.messages[1:]
    
    # Calculate the total tokens
    total_tokens = sum(len(tokenizer.tokenize(msg.content)) for msg in truncated_messages)
    
    # Truncate messages if necessary
    while total_tokens > max_tokens and len(truncated_messages) > 1:
        removed_message = truncated_messages.pop(1)  # Remove the oldest non-system message
        total_tokens = sum(len(tokenizer.tokenize(msg.content)) for msg in truncated_messages)
        logger.info(f"Message removed due to token limit: {removed_message.role} - {removed_message.text[:30]}...")
    
    print(f"Context truncation completed in {time.time() - start_time:.2f} seconds")
    
    if bool(strtobool(os.getenv("DEBUG_LLM", "False"))):
        base_dir = get_base_log_dir()
        debug_dir = os.path.join(base_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        
        llm_log_path = os.path.join(debug_dir, 'llm.log')
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        request_log = {
            'timestamp': timestamp,
            'type': 'request',
            'raw_context': [{'role': msg.role, 'content': getattr(msg, 'text', '<missing text>')} 
                           for msg in truncated_messages]
        }
        
        with open(llm_log_path, 'a', encoding='utf-8') as f:
            f.write('\n' + '='*80 + '\n')
            f.write(json.dumps(request_log, ensure_ascii=False, indent=2))
            f.write('\n')