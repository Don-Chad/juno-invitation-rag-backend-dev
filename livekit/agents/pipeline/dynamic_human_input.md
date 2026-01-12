# Dynamic Human Input Documentation

## Overview
The `DynamicEndpointingHumanInput` class processes real-time audio with dynamic endpointing to determine when someone has finished speaking.

## Key Features
1. Real-time audio processing from LiveKit room
2. Voice activity detection (VAD)
3. Speech-to-text transcription
4. Dynamic endpointing based on sentence completion

## Events/Triggers
The class emits several events you can listen to:

- `"start_of_speech"`: Triggered when user starts speaking
- `"end_of_speech"`: Triggered when user stops speaking
- `"vad_inference_done"`: Voice activity detection probability updates
- `"final_transcript"`: Complete transcription segments
- `"interim_transcript"`: Partial transcription segments

## Endpointing Delays
- Complete sentences (ending with .!?): 0.2s delay
- Incomplete sentences: 5.0s delay

## Example Usage 

ython
async def handle_turns():
human_input = DynamicEndpointingHumanInput(
room=room,
vad=vad_instance,
stt=stt_instance,
participant=participant,
transcription=True
)
@human_input.on("start_of_speech")
def on_start():
print("User started speaking")
@human_input.on("end_of_speech")
def on_end():
print("User finished speaking")
# Safe to start AI response here
@human_input.on("final_transcript")
def on_transcript(ev):
print(f"User said: {ev.text}")

## Common Use Cases
- Building conversational AI systems
- Natural turn-taking in conversations
- Real-time transcription with intelligent pause detection
- Voice-activated applications
- Detecting when users finish speaking to trigger AI responses