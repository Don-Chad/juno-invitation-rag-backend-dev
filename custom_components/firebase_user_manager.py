"""
Firebase User Manager for LiveKit Agent
Handles user authentication, session management, and chat history storage.
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import logging
import os
import asyncio
from dataclasses import dataclass, field
import base64
import secrets

from livekit.agents import llm

logger = logging.getLogger("firebase-user-manager")

# Configuration
MAX_CHAT_HISTORY_MESSAGES = 50  # Maximum messages to load from history
FIREBASE_CREDENTIALS_PATH = "ai-chatbot-v1-645d6-firebase-adminsdk-fbsvc-0b24386fbb.json"


@dataclass
class UserSession:
    """Represents a user session with their settings and state"""
    user_id: str
    display_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)
    settings: Dict[str, Any] = field(default_factory=dict)
    is_authenticated: bool = False
    memories: List[str] = field(default_factory=list)
    last_memory_extraction: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'display_name': self.display_name,
            'created_at': self.created_at,
            'last_active': self.last_active,
            'settings': self.settings,
            'is_authenticated': self.is_authenticated,
            'memories': self.memories,
            'last_memory_extraction': self.last_memory_extraction
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'UserSession':
        return UserSession(
            user_id=data.get('user_id', ''),
            display_name=data.get('display_name', ''),
            created_at=data.get('created_at', datetime.utcnow()),
            last_active=data.get('last_active', datetime.utcnow()),
            settings=data.get('settings', {}),
            is_authenticated=data.get('is_authenticated', False),
            memories=data.get('memories', []),
            last_memory_extraction=data.get('last_memory_extraction')
        )


class FirebaseUserManager:
    """Manages user sessions and chat history via Firebase Firestore"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not FirebaseUserManager._initialized:
            self._db = None
            self._keks: Dict[int, bytes] = {}
            self._dek_cache: Dict[str, bytes] = {}  # In-memory cache of unwrapped DEKs
            self._initialize_firebase()
            FirebaseUserManager._initialized = True

    # ==========================================
    # History Encryption (Envelope Encryption)
    # ==========================================
    #
    # Threat model: Firestore is untrusted. Backend worker is trusted.
    # We encrypt message content client-side (in worker) before writing.
    #
    # - Per-user Data Encryption Key (DEK): random 32 bytes, used for AES-256-GCM content encryption.
    # - Master Key Encryption Key (KEK): stored ONLY in worker env as base64, used to wrap (encrypt) the DEK.
    #
    # Firestore stores:
    # - per-message: content_enc (b64), nonce (b64), enc_v, key_version, timestamp_ms
    # - per-user: history_key_wrapped (b64), history_key_wrapped_nonce (b64), history_key_kek_version, history_key_v
    #
    # Nonces are not secret; keys are never stored in Firestore.

    def _get_kek(self, version: int) -> Optional[bytes]:
        """Load KEK from env (base64) and cache it."""
        if version in self._keks:
            return self._keks[version]

        raw = os.getenv(f"HISTORY_KEK_V{version}")
        if not raw:
            return None
        try:
            key = base64.urlsafe_b64decode(raw.encode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid base64 in HISTORY_KEK_V{version}: {e}") from e

        if len(key) != 32:
            raise ValueError(f"HISTORY_KEK_V{version} must decode to 32 bytes (got {len(key)})")

        self._keks[version] = key
        return key

    def _require_aesgcm(self):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
            return AESGCM
        except Exception as e:
            raise RuntimeError(
                "History encryption requires 'cryptography'. Install it in the backend worker environment."
            ) from e

    def _b64e(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8")

    def _b64d(self, data: str) -> bytes:
        return base64.urlsafe_b64decode(data.encode("utf-8"))

    def _dek_aad(self, user_id: str, email: str) -> bytes:
        return f"history-dek|v1|user:{user_id}|email:{email}".encode("utf-8")

    def _msg_aad(self, user_id: str, agent_name: str, role: str, timestamp_ms: int) -> bytes:
        # Bind ciphertext to non-secret metadata to detect tampering (e.g. role swapping to "system").
        return f"history-msg|v1|user:{user_id}|agent:{agent_name}|role:{role}|ts:{timestamp_ms}".encode("utf-8")

    def _wrap_dek(self, kek: bytes, user_id: str, email: str, dek: bytes) -> Tuple[str, str]:
        AESGCM = self._require_aesgcm()
        nonce = secrets.token_bytes(12)
        aad = self._dek_aad(user_id, email)
        wrapped = AESGCM(kek).encrypt(nonce, dek, aad)
        return self._b64e(wrapped), self._b64e(nonce)

    def _unwrap_dek(self, kek: bytes, user_id: str, email: str, wrapped_b64: str, nonce_b64: str) -> bytes:
        AESGCM = self._require_aesgcm()
        wrapped = self._b64d(wrapped_b64)
        nonce = self._b64d(nonce_b64)
        aad = self._dek_aad(user_id, email)
        return AESGCM(kek).decrypt(nonce, wrapped, aad)

    def _encrypt_content(
        self,
        dek: bytes,
        user_id: str,
        agent_name: str,
        role: str,
        timestamp_ms: int,
        plaintext: str,
    ) -> Tuple[str, str]:
        AESGCM = self._require_aesgcm()
        nonce = secrets.token_bytes(12)
        aad = self._msg_aad(user_id, agent_name, role, timestamp_ms)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
        return self._b64e(ciphertext), self._b64e(nonce)

    def _decrypt_content(
        self,
        dek: bytes,
        user_id: str,
        agent_name: str,
        role: str,
        timestamp_ms: int,
        ciphertext_b64: str,
        nonce_b64: str,
    ) -> str:
        AESGCM = self._require_aesgcm()
        aad = self._msg_aad(user_id, agent_name, role, timestamp_ms)
        nonce = self._b64d(nonce_b64)
        ciphertext = self._b64d(ciphertext_b64)
        pt = AESGCM(dek).decrypt(nonce, ciphertext, aad)
        return pt.decode("utf-8")

    async def _get_user_history_dek_if_present(self, user_id: str) -> Optional[bytes]:
        """
        Return the user's DEK if it exists (unwraps it using the KEK).

        Important: this MUST NOT create/overwrite keys. It's used for decryption on load.
        """
        # Check cache first
        if user_id in self._dek_cache:
            return self._dek_cache[user_id]

        kek_version = 1
        kek = self._get_kek(kek_version)
        if not kek:
            return None

        doc_ref = self.db.collection("users").document(user_id)
        # Offload blocking Firestore call to a thread
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return None

        user_data = doc.to_dict() or {}
        email = user_data.get("email", "unknown")
        wrapped = user_data.get("history_key_wrapped")
        wrapped_nonce = user_data.get("history_key_wrapped_nonce")
        stored_kek_version = user_data.get("history_key_kek_version")
        stored_v = user_data.get("history_key_v")

        if not (wrapped and wrapped_nonce and stored_kek_version == kek_version and stored_v == 1):
            return None

        dek = self._unwrap_dek(kek, user_id, email, wrapped, wrapped_nonce)
        if len(dek) != 32:
            return None

        # Store in cache
        self._dek_cache[user_id] = dek
        return dek

    async def _get_or_create_user_history_dek(self, user_id: str) -> Tuple[bytes, int]:
        """
        Return (dek_bytes, kek_version).

        Stores only the WRAPPED DEK in Firestore user doc.
        """
        # Check cache first
        if user_id in self._dek_cache:
            return self._dek_cache[user_id], 1

        kek_version = 1
        kek = self._get_kek(kek_version)
        if not kek:
            raise RuntimeError(
                "Missing HISTORY_KEK_V1 in backend worker environment (required for history encryption)"
            )

        doc_ref = self.db.collection("users").document(user_id)
        # Offload blocking Firestore call to a thread
        doc = await asyncio.to_thread(doc_ref.get)
        user_data = doc.to_dict() if doc.exists else {}
        email = user_data.get("email", "unknown")

        wrapped = user_data.get("history_key_wrapped")
        wrapped_nonce = user_data.get("history_key_wrapped_nonce")
        stored_kek_version = user_data.get("history_key_kek_version")
        stored_v = user_data.get("history_key_v")

        if wrapped and wrapped_nonce and stored_kek_version == kek_version and stored_v == 1:
            dek = self._unwrap_dek(kek, user_id, email, wrapped, wrapped_nonce)
            if len(dek) == 32:
                self._dek_cache[user_id] = dek
                return dek, kek_version

        # Create + wrap a new DEK
        dek = secrets.token_bytes(32)
        wrapped_b64, wrapped_nonce_b64 = self._wrap_dek(kek, user_id, email, dek)

        # Merge into user doc (offload blocking set call)
        data = {
            "history_key_v": 1,
            "history_key_kek_version": kek_version,
            "history_key_wrapped": wrapped_b64,
            "history_key_wrapped_nonce": wrapped_nonce_b64,
            "last_active": datetime.utcnow(),
        }
        await asyncio.to_thread(doc_ref.set, data, merge=True)

        self._dek_cache[user_id] = dek
        return dek, kek_version
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if already initialized
            try:
                firebase_admin.get_app()
                logger.info("Firebase already initialized")
            except ValueError:
                # Initialize with credentials
                cred_path = FIREBASE_CREDENTIALS_PATH
                if not os.path.isabs(cred_path):
                    # Try relative to current working directory
                    cred_path = os.path.join(os.getcwd(), cred_path)
                
                if not os.path.exists(cred_path):
                    # Try relative to this file's directory
                    cred_path = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", FIREBASE_CREDENTIALS_PATH)
                    )
                
                if not os.path.exists(cred_path):
                    raise FileNotFoundError(f"Firebase credentials not found at {FIREBASE_CREDENTIALS_PATH}")
                
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info(f"Firebase initialized with credentials from {cred_path}")
            
            self._db = firestore.client()
            logger.info("Firestore client ready")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    
    @property
    def db(self):
        """Get Firestore client"""
        if self._db is None:
            self._db = firestore.client()
        return self._db
    
    # ==========================================
    # User Session Management
    # ==========================================
    
    async def get_or_create_user(self, user_id: str, display_name: str = "") -> UserSession:
        """Get existing user or create a new one"""
        try:
            doc_ref = self.db.collection('users').document(user_id)
            doc = await asyncio.to_thread(doc_ref.get)
            
            if doc.exists:
                user_data = doc.to_dict() or {}
                user_session = UserSession.from_dict(user_data)
                user_session.last_active = datetime.utcnow()
                
                # Update last active timestamp
                await asyncio.to_thread(doc_ref.update, {'last_active': user_session.last_active})
                logger.info(f"Retrieved existing user: {user_id}")
                return user_session
            else:
                # Create new user
                user_session = UserSession(
                    user_id=user_id,
                    display_name=display_name or user_id,
                    is_authenticated=True
                )
                await asyncio.to_thread(doc_ref.set, user_session.to_dict())
                logger.info(f"Created new user: {user_id}")
                return user_session
                
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            # Return a default session on error
            return UserSession(user_id=user_id, display_name=display_name)
    
    async def update_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Update user settings"""
        try:
            doc_ref = self.db.collection('users').document(user_id)
            await asyncio.to_thread(doc_ref.update, {
                'settings': settings,
                'last_active': datetime.utcnow()
            })
            logger.info(f"Updated settings for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return False
    
    # ==========================================
    # Chat History Management
    # ==========================================
    
    async def store_message(self, user_id: str, content: str, role: str, agent_name: str = "juno"):
        """Store a chat message in Firebase"""
        timestamp = datetime.utcnow()
        timestamp_ms = int(timestamp.timestamp() * 1000)
        
        try:
            conversation_id = f"{user_id}_{agent_name}"
            doc_ref = self.db.collection('conversations').document(conversation_id)

            # Encrypt content (Firestore is treated as untrusted)
            dek, kek_version = await self._get_or_create_user_history_dek(user_id)
            content_enc, nonce_b64 = self._encrypt_content(
                dek=dek,
                user_id=user_id,
                agent_name=agent_name,
                role=role,
                timestamp_ms=timestamp_ms,
                plaintext=content,
            )

            new_message = {
                "user_id": user_id,
                "agent_name": agent_name,
                "role": role,
                "timestamp": timestamp,
                "timestamp_ms": timestamp_ms,
                "content_enc": content_enc,
                "nonce": nonce_b64,
                "enc_v": 1,
                "key_version": kek_version,
            }
            
            doc = await asyncio.to_thread(doc_ref.get)
            if doc.exists:
                await asyncio.to_thread(
                    doc_ref.update,
                    {
                        'messages': firestore.ArrayUnion([new_message]),
                        'updated_at': timestamp
                    }
                )
            else:
                await asyncio.to_thread(
                    doc_ref.set,
                    {
                        'messages': [new_message],
                        'created_at': timestamp,
                        'updated_at': timestamp,
                        'user_id': user_id,
                        'agent_name': agent_name
                    }
                )

            logger.debug(f"Stored encrypted message for {user_id}: role={role}, bytes={len(content.encode('utf-8'))}")
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")

    async def load_chat_history(
        self, 
        user_id: str,
        agent_name: str = "juno",
        max_messages: int = MAX_CHAT_HISTORY_MESSAGES
    ) -> llm.ChatContext:
        """
        Load chat history from Firebase and build ChatContext.

        IMPORTANT:
        - We intentionally do NOT inject the main system prompt here, because LiveKit Agents
          already takes `instructions=...` in the Agent constructor.
        - We only add lightweight system markers (like "User is returning...") plus prior messages.
        """
        chat_ctx = llm.ChatContext.empty()
        
        try:
            conversation_id = f"{user_id}_{agent_name}"
            doc_ref = self.db.collection('conversations').document(conversation_id)
            doc = await asyncio.to_thread(doc_ref.get)
            
            if not doc.exists:
                logger.info(f"No history found for user {user_id}, starting fresh")
                print(f"Firebase history: total=0, loaded=0, limit={max_messages}", flush=True)
                return chat_ctx
            
            data = doc.to_dict()
            messages = data.get('messages', [])
            
            if not messages:
                print(f"Firebase history: total=0, loaded=0, limit={max_messages}", flush=True)
                return chat_ctx
            
            # Sort by timestamp and limit
            sorted_messages = sorted(messages, key=lambda x: x['timestamp'])
            limited_messages = sorted_messages[-max_messages:] if len(sorted_messages) > max_messages else sorted_messages
            
            # Add context about returning user
            chat_ctx.add_message(
                role="system",
                content=f"Notice: User is returning. Found {len(messages)} total messages, loading last {len(limited_messages)} from previous conversations (max {max_messages}):"
            )
            
            logger.info(f"Firebase history: total={len(messages)}, loaded={len(limited_messages)}, limit={max_messages}")
            print(f"Firebase history: total={len(messages)}, loaded={len(limited_messages)}, limit={max_messages}", flush=True)
            
            loaded_summary = []
            # Group messages by relative date
            current_date = None
            for msg in limited_messages:
                relative_date = self._calculate_relative_date(msg['timestamp'])
                
                if current_date != relative_date:
                    chat_ctx.add_message(
                        role="system",
                        content=f"\n--- Previous conversation from {relative_date} ---"
                    )
                    current_date = relative_date

                # Decrypt encrypted messages; allow legacy plaintext fallback.
                text = msg.get("content")
                if msg.get("content_enc") and msg.get("nonce"):
                    try:
                        dek = await self._get_user_history_dek_if_present(user_id)
                        if not dek:
                            logger.warning(
                                f"Skipping encrypted history message for user {user_id}: missing history key in user doc"
                            )
                            continue
                        ts_ms = msg.get("timestamp_ms")
                        if ts_ms is None:
                            # Best-effort fallback for very early encrypted records (should not happen).
                            ts = msg.get("timestamp")
                            ts_ms = int(ts.timestamp() * 1000) if isinstance(ts, datetime) else 0

                        text = self._decrypt_content(
                            dek=dek,
                            user_id=user_id,
                            agent_name=agent_name,
                            role=msg.get("role", "user"),
                            timestamp_ms=int(ts_ms),
                            ciphertext_b64=msg["content_enc"],
                            nonce_b64=msg["nonce"],
                        )
                    except Exception as e:
                        # If ciphertext is tampered/unreadable, skip it (don't poison LLM context).
                        logger.warning(f"Skipping unreadable encrypted history message for user {user_id}: {e}")
                        continue

                if text:
                    role = msg.get('role', 'user')
                    chat_ctx.add_message(role=role, content=text)
                    loaded_summary.append(f"{role}: {text[:20]}...")
            
            logger.info(f"Firebase history: Loaded {len(loaded_summary)} messages: {', '.join(loaded_summary)}")
            
        except Exception as e:
            logger.error(f"Error loading chat history: {e}")
            print(f"Firebase history: error loading - {e}", flush=True)
        
        return chat_ctx
    
    def _calculate_relative_date(self, date: datetime) -> str:
        """Convert date to relative format"""
        # Handle timezone-aware dates
        if hasattr(date, 'tzinfo') and date.tzinfo is not None:
            date = date.replace(tzinfo=None)
        
        delta = datetime.now() - date
        
        if delta < timedelta(days=1):
            return "today"
        elif delta < timedelta(days=2):
            return "yesterday"
        elif delta < timedelta(days=7):
            return f"{delta.days} days ago"
        elif delta < timedelta(days=14):
            return "more than a week ago"
        elif delta < timedelta(days=30):
            return "2 weeks ago"
        else:
            return "more than a month ago"
    
    async def clear_history(self, user_id: str, agent_name: str = "juno") -> bool:
        """Clear chat history for a user"""
        try:
            conversation_id = f"{user_id}_{agent_name}"
            doc_ref = self.db.collection('conversations').document(conversation_id)
            doc_ref.delete()
            logger.info(f"Cleared history for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing history: {e}")
            return False

    # ==========================================
    # Active Memory Management
    # ==========================================

    async def store_memories(self, user_id: str, memories: List[str]):
        """Store or update user memories in Firestore"""
        try:
            doc_ref = self.db.collection('users').document(user_id)
            doc_ref.update({
                'memories': memories,
                'last_memory_extraction': datetime.utcnow()
            })
            logger.info(f"Stored {len(memories)} memories for user {user_id}")
        except Exception as e:
            logger.error(f"Error storing memories: {e}")

    async def load_memories(self, user_id: str) -> List[str]:
        """Load user memories from Firestore"""
        try:
            doc_ref = self.db.collection('users').document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict().get('memories', [])
            return []
        except Exception as e:
            logger.error(f"Error loading memories: {e}")
            return []
    
    # ==========================================
    # User Authentication Helpers
    # ==========================================
    
    def extract_user_id_from_room(self, room_name: str) -> str:
        """
        Extract user ID from LiveKit room name.
        Room names often follow format: userId_roomId or similar
        """
        # If we use a fixed suffix, strip it (supports UIDs containing underscores)
        suffix = "_conversation"
        if room_name.endswith(suffix):
            return room_name[: -len(suffix)]

        # Fallback to first segment split (legacy behavior)
        if "_" in room_name:
            return room_name.split("_", 1)[0]
        return room_name
    
    def extract_user_from_participant_identity(self, identity: str) -> str:
        """
        Extract user ID from participant identity.
        Identity can be passed from frontend during connection.
        """
        # If identity contains user info in format "user:userId" or just userId
        if ":" in identity:
            parts = identity.split(":")
            if parts[0] == "user":
                return parts[1]
        return identity


# Singleton instance for easy access
_manager_instance: Optional[FirebaseUserManager] = None

def get_firebase_manager() -> FirebaseUserManager:
    """Get the singleton FirebaseUserManager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = FirebaseUserManager()
    return _manager_instance
