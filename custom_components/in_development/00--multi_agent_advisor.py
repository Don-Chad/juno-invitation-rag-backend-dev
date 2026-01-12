import tracemalloc

# Start tracing memory allocations
tracemalloc.start()


import asyncio
import os
import importlib
from datetime import datetime
from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm, JobProcess, vad
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, elevenlabs, silero #turn_detector
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
import time



load_dotenv(dotenv_path=".env.local", override=True)
print(os.getenv("ELEVEN_API_KEY"))

# note: the multi_agent needs to run on render.com. use files, directories accordingly.

# Replace the existing logger setup with:
logger = setup_logging()

# dg_model = "nova-2-conversationalai" # the old STT model
dg_model = "nova-2-phonecall"
DEV_MODE = True


#this does not have the right RAG system yetr, nor the webcam. 

# Add after other constants
DEBUG_LLM = bool(strtobool(os.getenv("DEBUG_LLM", "True"))) #set to false for now. Needs to be implemented on deeper level.
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

    # fallback to Azure if OpenAI goes down
    fallback_llm = llm.FallbackAdapter(
        [
            openai.LLM(
            model="llama-3.3-70b-versatile", # specdec is not working well.
            api_key=os.getenv("GROQ_API_KEY", ""), 
            base_url="https://api.groq.com/openai/v1", 
        ),
            openai.LLM(
            model="accounts/fireworks/models/llama-v3p1-8b-instruct",
            api_key=os.getenv("FIREWORKS_API_KEY"), 
            base_url="https://api.fireworks.ai/inference/v1", 
        ),
        ]
    )

    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model=dg_model, language="nl"),
        llm=fallback_llm,
        
        tts=elevenlabs.TTS(voice=VOICE1, api_key=os.getenv("ELEVEN_API_KEY")),
        min_endpointing_delay=0.00,
        interrupt_speech_duration=0.5,
        interrupt_min_words=2,
        before_tts_cb=replace_words,
        before_llm_cb=debug_and_truncate_context,
        chat_ctx=initial_ctx,
        allow_interruptions=True,
        # turn_detector=turn_detector.EOUModel(),
    )

    setattr(assistant, 'INTERRUPT_PHRASES', INTERRUPT_PHRASES)

    setattr(assistant, 'log_dir', log_dir)

    

    assistant.start(ctx.room, participant)

    
    
    # greeting = get_greeting(returning_user)
   # await assistant.say(greeting, allow_interruptions=True)

   # Send a greeting message to the user
    chat_ctx = assistant.chat_ctx.copy()
    chat_ctx.append(role="user", text="(begroet de gebruiker. start met een korte reactie, en vraag of de gebruiker klaar is voor het gesprek.)")
    stream = assistant.llm.chat(chat_ctx=chat_ctx)
    await assistant.say(stream)


    @assistant.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        processed_text, _ = character_helper.process_speech_input(msg.content)
        print(f"user speech committed !! \n\n\n\n\n: {processed_text}")
        msg.content = processed_text
        asyncio.create_task(transcription_manager.store_message(processed_text, "user"))
    
    # for the transcription manager
    @assistant.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        # Log the LLM response
        
        # Create async task for storing message
        asyncio.create_task(transcription_manager.store_message(msg.content, "assistant"))
    

    # Create a wrapper function for shutdown
    async def handle_shutdown():
        try:
            # Add disconnect message before logging costs
            snapshot = tracemalloc.take_snapshot()
            await transcription_manager.store_message("(user disconnected from the call)", "system")
              # Display the top 10 memory-consuming lines
            top_stats = snapshot.statistics('lineno')
            print("[ Top 10 ]")
            for stat in top_stats[:10]:
                print(stat)
            
            # Log the session costs
            await log_session_cost(transcription_manager=transcription_manager)
            
            # Ensure proper shutdown of transcription manager
            await transcription_manager.shutdown()
            logger.info("Session terminated successfully")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


    # # # # silence monitoring reaction
    # Define user_started_speaking, silence_monitoring_task, and silence_threshold as global variables.
    global user_started_speaking, silence_monitoring_task, silence_threshold, silence_start_time
    user_started_speaking = False
    silence_monitoring_task = None
    silence_threshold = 8  # Initial silence threshold in seconds
    silence_start_time = None

    # Silence monitoring
    @assistant.on("user_started_speaking")
    def on_user_started_speaking():
        global user_started_speaking
        user_started_speaking = True

    @assistant.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        global user_started_speaking, silence_monitoring_task
        user_started_speaking = False
        if not silence_monitoring_task:
            silence_monitoring_task = asyncio.create_task(monitor_silence())

    # Start the silence timer when the agent stops speaking
    @assistant.on("agent_stopped_speaking")
    def on_agent_stopped_speaking():
        global silence_start_time
        silence_start_time = time.time()  # Start the silence timer
        print("agent stopped speaking")

    # Reset silence monitoring when the agent starts speaking
    @assistant.on("agent_started_speaking")
    def on_agent_started_speaking():
        global silence_start_time
        silence_start_time = None  # Reset the silence timer

    async def monitor_silence():
        global user_started_speaking, silence_start_time, silence_threshold

        while True:
            if silence_start_time is not None and not user_started_speaking:
                if time.time() - silence_start_time >= silence_threshold:
                    print(f"Silence detected for {silence_threshold} seconds after speech committed.")
                    chat_ctx = assistant.chat_ctx.copy()
                    chat_ctx.append(role="user", text="(indication: user has been non responsive for over 8 seconds - shortly check if user is still there in a brief message. start your message with '...', for any second user check, make it really short (like: hello <name?)")
                    stream = assistant.llm.chat(chat_ctx=chat_ctx)
                    await assistant.say(stream, allow_interruptions=True)
                    
                    # Increase the silence threshold progressively
                    silence_threshold = min(silence_threshold * 2, 30)  # Cap the threshold at 30 seconds
                    silence_start_time = time.time()  # Reset the timer
            else:
                silence_start_time = None  # Reset the timer if user starts speaking

            await asyncio.sleep(0.1)  # Check every 100ms











    # Register the async shutdown handler
    ctx.add_shutdown_callback(handle_shutdown)

    # Setup metrics collection
    setup_metrics_collection(assistant, transcription_manager)

    # Add confident turn change handler
    # This temporarily disables interruptions when the agent starts speaking
    @assistant.on("agent_started_speaking")
    def on_agent_started_speaking():
        logger.debug("Agent started speaking. Applying confident turn change.")
        current_speech = assistant._playing_speech
        if current_speech:
            current_speech._allow_interruptions = False
            print("Confident turn change: Disabled interruptions")
            
            async def reenable_interruptions():
                await asyncio.sleep(2.0)  # Configurable duration kept in application code
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
