import logging
import asyncio
import os
from typing import List, Dict, Any
from groq import AsyncGroq
from livekit.agents.llm import ChatContext, ChatMessage
from config import (
    MEMORY_ENABLED, MEMORY_MODEL, MEMORY_MAX_ITEMS, 
    MEMORY_PII_PROTECTION, MEMORY_THRESHOLD_MESSAGES
)
from custom_components.firebase_user_manager import get_firebase_manager

logger = logging.getLogger("memory-manager")

class MemoryManager:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("GROQ_API_KEY not found. Memory formation will fail.")
        self.client = AsyncGroq(api_key=self.api_key) if self.api_key else None
        self.firebase_manager = get_firebase_manager()

    async def extract_memories(self, user_id: str, chat_ctx: ChatContext):
        """
        Asynchronously extract memories from chat history.
        This is non-blocking and safe.
        """
        if not MEMORY_ENABLED:
            return

        if not self.client:
            logger.error("Groq client not initialized. Cannot extract memories.")
            return

        # Get messages
        messages = getattr(chat_ctx, "messages", [])
        if not messages:
            return

        # Threshold check
        if len(messages) < MEMORY_THRESHOLD_MESSAGES:
            return

        # Start extraction in background
        asyncio.create_task(self._process_memory_formation(user_id, messages))

    async def _process_memory_formation(self, user_id: str, messages: List[ChatMessage]):
        """Background task to extract and save memories"""
        logger.info(f"🧠 Starting background memory extraction for user {user_id}")
        
        try:
            # 1. Load existing memories
            existing_memories = await self.firebase_manager.load_memories(user_id)
            
            # 2. Format conversation for the LLM
            conversation_text = ""
            for msg in messages:
                role = "User" if msg.role == "user" else "Assistant"
                content = str(msg.content)
                conversation_text += f"{role}: {content}\n"

            # 3. Build the prompt
            system_prompt = self._build_extraction_prompt(existing_memories)
            
            # 4. Call Groq
            response = await self.client.chat.completions.create(
                model=MEMORY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract new memories from this conversation:\n\n{conversation_text}"}
                ],
                temperature=0.1, # Low temperature for consistency
                max_tokens=2000
            )

            new_memories_raw = response.choices[0].message.content
            
            # 5. Parse and clean memories
            processed_memories = self._parse_memories(new_memories_raw, existing_memories)
            
            # 6. Store back to Firebase
            await self.firebase_manager.store_memories(user_id, processed_memories[:MEMORY_MAX_ITEMS])
            logger.info(f"✅ Background memory extraction complete for {user_id}. Total: {len(processed_memories)}")

        except Exception as e:
            logger.error(f"❌ Error in background memory extraction: {e}", exc_info=True)

    def _build_extraction_prompt(self, existing_memories: List[str]) -> str:
        existing_context = "\n".join([f"- {m}" for m in existing_memories]) if existing_memories else "None yet."
        
        prompt = f"""You are a specialized Memory Extraction Agent. Your goal is to identify and store useful, permanent facts about the user to help an AI agent provide a personalized experience.

### INSTRUCTIONS:
1. **Fact Extraction**: Extract specific facts about the user's preferences, background, goals, or recurring themes.
2. **Quality**: Only store high-value information. Avoid temporary context like "the user said hello".
3. **Safety & Privacy**: NEVER store PII (Personally Identifiable Information). Redact or skip:
   - Full names (unless public figure)
   - Emails, passwords, addresses, phone numbers
   - Credit card or financial details
   - Sensitive medical data
4. **Token Efficiency**: 
   - Combine similar facts.
   - Do NOT repeat facts already in the "Existing Memories" list below.
   - Be extremely concise (max 15 words per memory).
5. **Format**: Return a bulleted list of memories. Each line must be a single memory starting with "- ".

### EXISTING MEMORIES:
{existing_context}

### OUTPUT FORMAT:
- User prefers [X] over [Y]
- User is currently working on [Project Z]
- User mentioned they have a background in [Field]
"""
        return prompt

    def _parse_memories(self, raw_content: str, existing_memories: List[str]) -> List[str]:
        """Simple parsing of the bulleted list"""
        new_memories = []
        lines = raw_content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith("- "):
                memory = line[2:].strip()
                if memory and memory not in existing_memories:
                    new_memories.append(memory)
        
        # Merge lists, keeping uniqueness
        all_memories = existing_memories + new_memories
        unique_memories = []
        seen = set()
        for m in all_memories:
            m_lower = m.lower()
            if m_lower not in seen:
                unique_memories.append(m)
                seen.add(m_lower)
        
        return unique_memories

# Singleton instance
_memory_manager = None
def get_memory_manager():
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
