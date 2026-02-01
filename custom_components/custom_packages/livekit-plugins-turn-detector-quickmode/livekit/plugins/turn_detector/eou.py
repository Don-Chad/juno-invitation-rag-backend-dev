# Copyright 2023 LiveKit, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Quick Mode Turn Detector - NO MODEL LOADING
Uses only punctuation-based detection for fast turn detection.
"""

from __future__ import annotations

import json

from livekit.agents import llm
from livekit.agents.inference_runner import _InferenceRunner
from livekit.agents.ipc.inference_executor import InferenceExecutor
from livekit.agents.job import get_current_job_context

from .log import logger

MAX_HISTORY = 4


class _EUORunner(_InferenceRunner):
    """Quick mode EOU runner - no model loading, punctuation-based only."""
    
    INFERENCE_METHOD = "lk_end_of_utterance"

    def initialize(self) -> None:
        """Quick mode - no initialization needed."""
        logger.info("Quick mode turn detector initialized (no model loading)")

    def run(self, data: bytes) -> bytes | None:
        """Run quick mode detection based on punctuation only."""
        data_json = json.loads(data)
        chat_ctx = data_json.get("chat_ctx", None)

        if not chat_ctx:
            raise ValueError("chat_ctx is required on the inference input data")

        # Get the last message's content
        if chat_ctx and len(chat_ctx) > 0:
            last_message = chat_ctx[-1]["content"]
            
            # Quick mode: only use punctuation check
            eou_probability = 1.0 if self._is_definite_end(last_message) else 0.0
            
            logger.debug(
                "quick mode eou detection",
                extra={
                    "eou_probability": eou_probability,
                    "input": last_message[:100]
                }
            )
            
            return json.dumps({"eou_probability": eou_probability}).encode()

        # No message, assume not end of utterance
        return json.dumps({"eou_probability": 0.0}).encode()

    def _is_definite_end(self, text: str) -> bool:
        """Check if text ends with definite end-of-utterance markers."""
        text = text.strip()
        return text.endswith(('.', '!', '?'))


class EOUModel:
    """End of Utterance Model - Quick Mode Only."""
    
    def __init__(
        self,
        inference_executor: InferenceExecutor | None = None,
        unlikely_threshold: float = 0.15,
    ) -> None:
        self._executor = (
            inference_executor or get_current_job_context().inference_executor
        )
        self._unlikely_threshold = unlikely_threshold
        self._last_processed = None  # Track last processed text

    def unlikely_threshold(self) -> float:
        return self._unlikely_threshold

    def supports_language(self, language: str | None) -> bool:
        """Quick mode supports all languages."""
        return True

    async def predict_eou(self, chat_ctx: llm.ChatContext) -> float:
        return await self.predict_end_of_turn(chat_ctx)

    async def predict_end_of_turn(self, chat_ctx: llm.ChatContext) -> float:
        """Predict end of turn using quick mode detection."""
        messages = []
        current_message = None

        for msg in chat_ctx.messages:
            if msg.role not in ("user", "assistant"):
                continue

            if isinstance(msg.content, str):
                current_message = msg.content
                messages.append({
                    "role": msg.role,
                    "content": current_message,
                })
            elif isinstance(msg.content, list):
                for cnt in msg.content:
                    if isinstance(cnt, str):
                        current_message = cnt
                        messages.append({
                            "role": msg.role,
                            "content": current_message,
                        })
                        break

        messages = messages[-MAX_HISTORY:]

        # If it's the same as what we've already processed, return low probability
        if current_message == self._last_processed:
            logger.debug("Skipping duplicate message processing")
            return 0.0

        # Update our tracking of what we've processed
        self._last_processed = current_message

        json_data = json.dumps({"chat_ctx": messages}).encode()
        result = await self._executor.do_inference(
            _EUORunner.INFERENCE_METHOD, json_data
        )

        assert (
            result is not None
        ), "end_of_utterance prediction should always returns a result"

        result_json = json.loads(result.decode())
        return result_json["eou_probability"]

