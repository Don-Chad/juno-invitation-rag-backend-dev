# important context:
I work on windows. deploy to render.com linux/ubuntu. give terminal commands for windows.
# - the multi_agent.py file is the main file that runs the voice agent.
# - the character_and_helper_multi.py file contains the character configuration and helper functions.
# - the agent_helpers_new.py file contains even more helper functions for the voice agent.
# - all new helper functions should get their own file named helper_<name>.py and be placed in the custom_components directory.
# - the voice agent will run on render.com. use files, directories accordingly.
# - when creating file paths or identifiers, ensure they work on both Windows and Linux systems
#   - avoid using colons or other special characters in filenames/paths
#   - use os.path.join() for path construction
#   - test locally on Windows, but remember the production environment is Linux-based on render.com

# Development Mode:
# - Set DEV_MODE=True (defaults to True) for development
# - In dev mode:
#   - Uses Tesla configuration by default
#   - Uses persistent room "dev_room_tesla" for consistent chat history
#   - Logs are stored in platform-appropriate locations

# Deployment Procedure for Local Packages:
# the docker file must be updated for local packages to copy these
# - When deploying applications that use local packages (like livekit-agents):
#   1. Ensure local packages are copied to the container before pip install
#   2. Copy packages in the correct order:
#      - Copy requirements.txt first
#      - Copy all local package directories needed for installation
#      - Run pip install
#      - Copy remaining application code
#   3. In requirements.txt, use relative paths matching the container structure:
#      - Use './agents/package-name' format
#      - Or use '-e ./agents/package-name' for editable installs
#   4. Ensure correct file permissions when copying (use --chown in Docker)\

(-e for livekit agents does not work)  install this withoiut. 

# Pronunciation Rules:
# - Store pronunciations in custom_components/pronunciations.json
# - JSON structure for each entry:
#   ```json
#   {
#       "word": "example",
#       "phonetic": "ɪgˈzæmpəl",  # IPA format
#       "common_mistakes": ["exampel", "exemple"]
#   }
#   ```
# - Eleven Labs API Guidelines:
#   - Use only supported SSML tags
#   - Use basic IPA phonetic transcriptions without emphasis markers
#   - Wrap phonetic values in SSML when sending to API:
#     <phoneme alphabet="ipa">phonetic_value</phoneme>
#   - Do not use custom emphasis levels or unsupported attributes
#   - Alternative pronunciation control methods:
#     - Alternative spellings (e.g., "trapezIi" vs "trapezii")
#     - Strategic use of punctuation (capital letters, dashes)

# Event Emission Guidelines:
# - When an event is not triggering as expected, consider manually emitting the event.
# - To manually emit an event, use the `emit` method within the relevant class or method.
# - Example for manual event emission:
#   ```python
#   def _on_final_transcript(ev: stt.SpeechEvent) -> None:
#       new_transcript = ev.alternatives[0].text
#       if not new_transcript:
#           return
#       logger.debug(
#           "received user transcript",
#           extra={"user transcription": new_transcript},
#       )
#       # Manually emit the final_transcript event
#       self.emit("final_transcript", ev)
#   ```
# - Ensure that the event is registered and handled appropriately in the relevant classes.
