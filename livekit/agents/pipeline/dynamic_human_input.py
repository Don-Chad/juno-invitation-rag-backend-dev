from __future__ import annotations

import asyncio
import wave
import os
from typing import Literal, List, Optional
from dataclasses import dataclass
import numpy as np

from livekit import rtc

from .. import stt as speech_to_text
from .. import transcription, utils
from .. import vad as voice_activity_detection
from .log import logger
from .human_input import HumanInput

print("working with local file")
"this migt be of value of we want to use the audio stream to dynamically change the endpointing delay"

@dataclass
class AudioUtterance:
    id: int
    frames: List[bytes]
    
    def save_wav(self, directory: str = "/tmp/audio_utterances"):
        """Save the utterance as a WAV file"""
        os.makedirs(directory, exist_ok=True)
        filename = os.path.join(directory, f"utterance_{self.id}.wav")
        
        # Convert frames to numpy array
        audio_data = b''.join(self.frames)
        
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(audio_data)
        
        return filename

class DynamicEndpointingHumanInput(HumanInput):
    def __init__(
        self,
        *,
        room: rtc.Room,
        vad: voice_activity_detection.VAD,
        stt: speech_to_text.STT,
        participant: rtc.RemoteParticipant,
        transcription: bool,
        min_endpointing_delay: float = 0.2,
        incomplete_delay: float = 5.0,
        save_directory: str = "/tmp/audio_utterances"
    ) -> None:
        super().__init__(
            room=room,
            vad=vad,
            stt=stt,
            participant=participant,
            transcription=transcription
        )
        self._base_delay = min_endpointing_delay
        self._incomplete_delay = incomplete_delay
        self._current_delay = min_endpointing_delay
        
        # Add new attributes for audio utterances
        self._current_utterance: Optional[AudioUtterance] = None
        self._utterances: List[AudioUtterance] = []
        self._utterance_counter = 0
        self._save_directory = save_directory
        
        # Create save directory if it doesn't exist
        os.makedirs(save_directory, exist_ok=True)

    @utils.log_exceptions(logger=logger)
    async def _recognize_task(self, audio_stream: rtc.AudioStream) -> None:
        """
        Receive the frames from the user audio stream and detect voice activity.
        Added dynamic endpointing based on sentence completion.
        """
        vad_stream = self._vad.stream()
        stt_stream = self._stt.stream()

        def _before_forward(
            fwd: transcription.STTSegmentsForwarder, transcription: rtc.Transcription
        ):
            if not self._transcription:
                transcription.segments = []
            return transcription

        stt_forwarder = transcription.STTSegmentsForwarder(
            room=self._room,
            participant=self._participant,
            track=self._subscribed_track,
            before_forward_cb=_before_forward,
        )

        async def _audio_stream_co() -> None:
            async for ev in audio_stream:
                if self._speaking and self._current_utterance is not None:
                    self._current_utterance.frames.append(ev.frame)
                stt_stream.push_frame(ev.frame)
                vad_stream.push_frame(ev.frame)

        async def _vad_stream_co() -> None:
            async for ev in vad_stream:
                if ev.type == voice_activity_detection.VADEventType.START_OF_SPEECH:
                    self._speaking = True
                    if self._current_utterance is None:
                        # Start new utterance
                        self._utterance_counter += 1
                        self._current_utterance = AudioUtterance(
                            id=self._utterance_counter,
                            frames=[]
                        )
                        logger.debug(f"Started new utterance {self._utterance_counter}")
                    self.emit("start_of_speech", ev)
                    
                elif ev.type == voice_activity_detection.VADEventType.INFERENCE_DONE:
                    self._speech_probability = ev.probability
                    self.emit("vad_inference_done", ev)
                    
                elif ev.type == voice_activity_detection.VADEventType.END_OF_SPEECH:
                    self._speaking = False
                    # Save completed utterance
                    if self._current_utterance is not None:
                        self._utterances.append(self._current_utterance)
                        # Save to WAV file
                        filename = self._current_utterance.save_wav(self._save_directory)
                        logger.debug(f"Saved utterance {self._current_utterance.id} to {filename}")
                        self._current_utterance = None
                    self.emit("end_of_speech", ev)

        async def _stt_stream_co() -> None:
            async for ev in stt_stream:
                stt_forwarder.update(ev)

                # Check for incomplete sentences in real-time
                if ev.type in [speech_to_text.SpeechEventType.FINAL_TRANSCRIPT, 
                             speech_to_text.SpeechEventType.INTERIM_TRANSCRIPT]:
                    ends_with_punctuation = any(ev.text.strip().endswith(p) for p in '.!?')
                    
                    logger.debug(f"STT: '{ev.text}' (punct: {ends_with_punctuation}, delay: {self._current_delay})")
                    
                    # Update the delay based on punctuation
                    new_delay = self._base_delay if ends_with_punctuation else self._incomplete_delay
                    if new_delay != self._current_delay:
                        self._current_delay = new_delay
                        self._stt._min_endpointing_delay = new_delay  # Update STT component's delay
                        logger.debug(f"{'✓' if ends_with_punctuation else '⚠️'} Delay: {new_delay}")

                # Emit events as normal
                if ev.type == speech_to_text.SpeechEventType.FINAL_TRANSCRIPT:
                    self.emit("final_transcript", ev)
                elif ev.type == speech_to_text.SpeechEventType.INTERIM_TRANSCRIPT:
                    self.emit("interim_transcript", ev)

        tasks = [
            asyncio.create_task(_audio_stream_co()),
            asyncio.create_task(_vad_stream_co()),
            asyncio.create_task(_stt_stream_co()),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await utils.aio.gracefully_cancel(*tasks)

            await stt_forwarder.aclose()
            await stt_stream.aclose()
            await vad_stream.aclose()
