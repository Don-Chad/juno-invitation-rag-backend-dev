import asyncio
import os
import importlib
from datetime import datetime
from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm, JobProcess, vad
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, elevenlabs, silero, turn_detector, playht
from custom_components.worker_logging_helper import UserLogger, LoggingConfig
from custom_components.worker_character_configs import CHARACTER_CONFIGS
from custom_components.firebase_transcription import TranscriptionManager, TranscriptionConfig
from distutils.util import strtobool
from custom_components.worker_agent_helpers_new import (
    setup_logging,  # Here
    parse_room_info,
    setup_log_directory,
    estimate_tokens, 
    ensure_directory_permissions,
    prewarm,
    debug_and_truncate_context
)


from pathlib import Path
import json
from custom_components.worker_helper_costs import setup_metrics_collection, log_session_cost
import platform
from livekit.plugins.playht import Voice  # Add this import at the top



load_dotenv(dotenv_path=".env.local", override=True)
print(os.getenv("ELEVEN_API_KEY"))

# note: the multi_agent needs to run on render.com. use files, directories accordingly.

# Replace the existing logger setup with:
logger = setup_logging()

# dg_model = "nova-2-conversationalai" # the old STT model
dg_model = "nova-2-phonecall"
DEV_MODE = False

# Add after other constants
DEBUG_LLM = bool(strtobool(os.getenv("DEBUG_LLM", "False"))) #set to false for now. Needs to be implemented on deeper level.
MAX_TOKENS = 7000  # Maximum context length in tokens

# Add platform check and credential setup
if platform.system() == 'Windows':
    # Local Windows development credentials
    LIVEKIT_URL = "wss://trump-j6v8q74o.livekit.cloud"
    LIVEKIT_API_KEY = "APImkdnSCXB2uZ9"
    LIVEKIT_API_SECRET = "Qj3WAL6taxzRhFoGe15nXCLNd4FUBWRme0r43hGfMmGB"
    PLAYHT_USER_ID = "PeWUxPedU7gCLvLxpJr4FcSDXlS2"
    PLAYHT_API_KEY = "8b9cbcaf5a6440a3955a521aaeb2b12c"
    
    # Override environment variables
    os.environ['LIVEKIT_URL'] = LIVEKIT_URL
    os.environ['LIVEKIT_API_KEY'] = LIVEKIT_API_KEY
    os.environ['LIVEKIT_API_SECRET'] = LIVEKIT_API_SECRET
    os.environ['PLAYHT_USER_ID'] = PLAYHT_USER_ID
    os.environ['PLAYHT_API_KEY'] = PLAYHT_API_KEY

# not used anymore probably
async def adjust_interrupt_speech_duration(assistant: VoicePipelineAgent, initial_delay=6, target_delay=0.2, duration=5):
    """Gradually adjust the interrupt speech duration"""
    steps = 15
    delay_step = (initial_delay - target_delay) / steps
    for i in range(steps):
        await asyncio.sleep(duration / steps)
        assistant.interrupt_speech_duration = max(target_delay, initial_delay - i * delay_step)
        print(f"Interrupt speech duration set to {assistant.interrupt_speech_duration:.3f}")
    assistant.interrupt_speech_duration = target_delay
    logger.debug(f"Final min_endpointing_delay set to {target_delay:.3f}")

async def adjust_turn_protection(assistant: VoicePipelineAgent, initial_words=12, target_words=3, duration=8):
    print("adjusting turn protection")
    """
    Gradually reduce the interrupt protection after a turn change.
    Starts with high protection (more words required) and reduces over time.
    """
    steps = 10  # Faster adjustment than before
    word_step = (initial_words - target_words) / steps
    
    # Set initial high protection immediately
    assistant.interrupt_min_words = initial_words
    logger.debug(f"Turn protection: Set initial protection to {initial_words} words")
    
    for i in range(steps):
        await asyncio.sleep(duration / steps)
        new_words = max(target_words, initial_words - i * word_step)
        assistant.interrupt_min_words = int(new_words)
        logger.debug(f"Turn protection: Reduced to {assistant.interrupt_min_words} words")
        print(f"Turn protection: Reduced to {assistant.interrupt_min_words} words")
    
    # Set final protection level
    assistant.interrupt_min_words = target_words
    logger.debug(f"Turn protection: Settled at {target_words} words")

async def entrypoint(ctx: JobContext):
    # Use preloaded logger if available
    logger = ctx.proc.userdata.get("logger") or setup_logging()
    
    # Get user_id and speaker from room name
    user_id, speaker = parse_room_info(ctx.room.name, logger)
    logger.info(f"Setting up for user {user_id} with character {speaker}")
    
    # Setup log directory
    log_dir = setup_log_directory(user_id)
    
    # Use preloaded character configs
    character_configs = ctx.proc.userdata.get("character_configs")
    if character_configs:
        config = character_configs.get(speaker.lower())
    else:
        # Fallback to importing if not preloaded
        from custom_components.worker_character_configs import CHARACTER_CONFIGS
        config = CHARACTER_CONFIGS.get(speaker.lower())
           
    character_helper = importlib.import_module("character_and_helper_multi")
    
    # Pass user_id and log_dir to setup_character
    character_helper.setup_character(speaker, user_id, log_dir)
    
    # Now import what we need from the helper
    from custom_components.worker_character_and_helper_multi import (
        AGENT_NAME, VOICE1, replace_words,
        get_greeting,
        SYSTEM_TEXT,
        setup_metrics_collection,
        log_session_cost
    )

    # Setup logging
    logging_config = LoggingConfig(
        user_id=user_id,
        log_directory=log_dir,
        agent_name=AGENT_NAME,
        usage_collector=character_helper.usage_collector
    )
    user_logger = UserLogger(logging_config)
    user_logger.start()

    # Setup transcription manager
    transcription_config = TranscriptionConfig(
        user_id=user_id,
        speaker=AGENT_NAME,
        log_directory=log_dir
    )
    transcription_manager = TranscriptionManager(transcription_config)
    
    # Load chat history
    initial_ctx = await transcription_manager.load_chat_history(SYSTEM_TEXT)
    returning_user = any(message.role == "user" for message in initial_ctx.messages)

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")
    #, 
    # do not just add lines to the VoicePipelineAgent class, since it will not exist in the class! 
    # high quality voice mode tts=elevenlabs.TTS(voice=VOICE1, api_key=os.getenv("ELEVEN_API_KEY"), model="eleven_multilingual_v2"),
    INTERRUPT_PHRASES = {
        "wait", "hold on", "stop", "excuse me", "sorry",
        "one moment", "pause", "hang on", "just a second",
    }

    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model=dg_model),
        llm=openai.LLM(
            model="llama-3.3-70b-specdec",
            api_key=os.getenv("GROQ_API_KEY", ""), 
            base_url="https://api.groq.com/openai/v1", 
        ),
        #tts=elevenlabs.TTS(voice=VOICE1, api_key=os.getenv("ELEVEN_API_KEY", model="eleven_multilingual_v2")),
        tts=playht.TTS(
            voice=Voice(
                id="s3://voice-cloning-zero-shot/baf1ef41-36b6-428c-9bdf-50ba54682bd8/original/manifest.json",
                name="Custom Voice",
                voice_engine="Play3.0-mini"
            ),
            api_key=os.getenv("PLAYHT_API_KEY"),
            user_id="PeWUxPedU7gCLvLxpJr4FcSDXlS2"
        ),
        # tts=playht.TTS(voice=VOICE1),
        min_endpointing_delay=0.00,
        interrupt_speech_duration=0.5,
        interrupt_min_words=2,
        before_tts_cb=replace_words,
        before_llm_cb=debug_and_truncate_context,
        chat_ctx=initial_ctx,
        allow_interruptions=True,
        turn_detector=turn_detector.EOUModel(),
    )

    setattr(assistant, 'INTERRUPT_PHRASES', INTERRUPT_PHRASES)

    setattr(assistant, 'log_dir', log_dir)

    

    assistant.start(ctx.room, participant)

        # Add event handlers after creating the assistant
    # @assistant.vad.on("speech_started")
    # def handle_speech_start():
    #     on_speech_started()

    # @assistant.vad.on("speech_ended")
    # def handle_speech_end():
    #     on_speech_end()

    
    
    greeting = get_greeting(returning_user)
    await assistant.say(greeting, allow_interruptions=True)

    # Handle VAD events to check for interruption phrases as early as possible
    # This allows us to catch interruption attempts before the pipeline's validation
    # @assistant.vad.on("vad_inference_done")
    # def on_vad_inference(ev: vad.VADEvent):
    #     if assistant._playing_speech and assistant._transcribed_interim_text:
    #         text = assistant._transcribed_interim_text.lower().strip()
            
    #         # Check for immediate interruption phrases
    #         if any(phrase in text for phrase in INTERRUPT_PHRASES):
    #             print(f"Detected interruption phrase in VAD: {text}")
    #             # Force enable interruptions and trigger interrupt
    #             assistant._playing_speech._allow_interruptions = True
    #             assistant._playing_speech.interrupt()
    #             return
            
    #         # Check for incomplete sentences (no ending punctuation)
    #         if text and text[-1] not in ".!?":
    #             print(f"Incomplete utterance detected in VAD: {text}")
    #             # Prevent interruption for incomplete sentences
    #             assistant._playing_speech._allow_interruptions = False

    # Optional: Add handler for when user stops speaking to reset state
    # @assistant.on("user_stopped_speaking")
    # def on_user_stopped_speaking():
    #     if assistant._playing_speech:
    #         # Reset interruption state after a short delay
    #         async def reset_interruptions():
    #             await asyncio.sleep(1.0)  # Short delay to ensure we're really done
    #             if assistant._playing_speech:
    #                 assistant._playing_speech._allow_interruptions = True
    #                 print("User stopped speaking: Reset interruptions")
            
            # asyncio.create_task(reset_interruptions())

    @assistant.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        processed_text, _ = character_helper.process_speech_input(msg.content)
        msg.content = processed_text
        asyncio.create_task(transcription_manager.store_message(processed_text, "user"))
        
    @assistant.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        # Log the LLM response
        if DEBUG_LLM:
            log_dir = Path(getattr(assistant, 'log_dir', '/tmp'))
            llm_log_path = log_dir / 'llm.log'
            
            response_log = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'type': 'response',
                'content': msg.content
            }
            
            with open(llm_log_path, 'a', encoding='utf-8') as f:
                f.write('-'*40 + ' RESPONSE ' + '-'*40 + '\n')
                f.write(json.dumps(response_log, ensure_ascii=False, indent=2))
                f.write('\n\n')
        
        # Create async task for storing message
        asyncio.create_task(transcription_manager.store_message(msg.content, "assistant"))
    
    # # Add turn protection handler
    # @assistant.on("agent_started_speaking")
    # def on_agent_started_speaking():
    #     logger.debug("Agent started speaking. Applying turn protection.")
    #     # Create task without awaiting it
    #     asyncio.create_task(adjust_turn_protection(assistant))

    # Create a wrapper function for shutdown
    async def handle_shutdown():
        try:
            # Add disconnect message before logging costs
            await transcription_manager.store_message("(user disconnected from the call)", "system")
            
            # Log the session costs
            await log_session_cost(transcription_manager=transcription_manager)
            
            # Ensure proper shutdown of transcription manager
            await transcription_manager.shutdown()
            logger.info("Session terminated successfully")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    # Register the async shutdown handler
    ctx.add_shutdown_callback(handle_shutdown)

    # Setup metrics collection
    setup_metrics_collection(assistant, transcription_manager)

    # Add confident turn change handler
    # This temporarily disables interruptions when the agent starts speaking
    # After 5.5 seconds, it re-enables interruptions if it's still the same speech playing.
    @assistant.on("agent_started_speaking")
    def on_agent_started_speaking():
        logger.debug("Agent started speaking. Applying confident turn change.")
        current_speech = assistant._playing_speech
        if current_speech:
            current_speech._allow_interruptions = False
            print("Confident turn change: Disabled interruptions")
            
            async def reenable_interruptions():
                await asyncio.sleep(2.5)  # Configurable duration kept in application code
                if current_speech and current_speech == assistant._playing_speech:
                    current_speech._allow_interruptions = True
                    print("Confident turn change: Re-enabled interruptions")
            
            asyncio.create_task(reenable_interruptions())

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
