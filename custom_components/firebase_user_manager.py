"""
Firebase User Manager for LiveKit Agent
Handles user authentication, session management, and chat history storage.
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple, Mapping, Union
import logging
import os
import asyncio
from dataclasses import dataclass, field
import base64
import secrets
import json

from livekit.agents import llm

logger = logging.getLogger("firebase-user-manager")

# Configuration
MAX_CHAT_HISTORY_MESSAGES = 50  # Maximum messages to load from history
FIREBASE_CREDENTIALS_PATH = "ai-chatbot-v1-645d6-firebase-adminsdk-fbsvc-0b24386fbb.json"

# History keyring configuration (KEKs / "PEP keys")
#
# - HISTORY_KEK_KEYRING_PATH: optional JSON file containing KEKs by version.
# - HISTORY_KEK_ACTIVE_VERSION: selects active KEK version (file overrides env if present).
#
# Keyring JSON shape (example, do NOT print keys in logs):
# {
#   "active_version": 2,
#   "keys": { "1": "<base64url-32-bytes>", "2": "<base64url-32-bytes>" }
# }
HISTORY_KEK_KEYRING_PATH_ENV = "HISTORY_KEK_KEYRING_PATH"
HISTORY_KEK_ACTIVE_VERSION_ENV = "HISTORY_KEK_ACTIVE_VERSION"

# Per-day DEK rotation
HISTORY_DEK_ROTATION_DAYS_ENABLED = True  # new DEK per UTC day


def _utcnow_naive() -> datetime:
    """
    Replacement for datetime.utcnow() (deprecated on Python 3.13+).
    Returns a timezone-naive UTC datetime for Firestore compatibility.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class UserSession:
    """Represents a user session with their settings and state"""
    user_id: str
    display_name: str = ""
    created_at: datetime = field(default_factory=_utcnow_naive)
    last_active: datetime = field(default_factory=_utcnow_naive)
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
            created_at=data.get('created_at', _utcnow_naive()),
            last_active=data.get('last_active', _utcnow_naive()),
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
            self._dek_cache: Dict[str, bytes] = {}  # In-memory cache of unwrapped DEKs (by cache key)
            self._kek_keyring_cache: Optional[Dict[str, Any]] = None
            self._kek_keyring_mtime: Optional[int] = None
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

    def _read_kek_keyring_file(self) -> Optional[Dict[str, Any]]:
        """
        Read KEK keyring JSON from a local file path.
        Never logs key material.
        """
        path = os.getenv(HISTORY_KEK_KEYRING_PATH_ENV, "").strip()
        if not path:
            return None
        try:
            st = os.stat(path)
            # Use ns precision so quick successive writes are not missed.
            mtime = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
        except Exception:
            return None

        if self._kek_keyring_cache is not None and self._kek_keyring_mtime == mtime:
            return self._kek_keyring_cache

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
        except Exception:
            return None

        self._kek_keyring_cache = data
        self._kek_keyring_mtime = mtime
        return data

    def _get_active_kek_version(self) -> int:
        """
        Determine active KEK version.
        Priority: keyring file "active_version" -> env -> default 1.
        """
        ring = self._read_kek_keyring_file()
        if isinstance(ring, dict):
            av = ring.get("active_version")
            try:
                if av is not None:
                    v = int(av)
                    if v >= 1:
                        return v
            except Exception:
                pass

        raw = os.getenv(HISTORY_KEK_ACTIVE_VERSION_ENV, "").strip()
        try:
            if raw:
                v = int(raw)
                if v >= 1:
                    return v
        except Exception:
            pass
        return 1

    def _get_kek(self, version: int) -> Optional[bytes]:
        """Load KEK (base64url, 32 bytes) from keyring file or env and cache it."""
        if version in self._keks:
            return self._keks[version]

        raw: Optional[str] = None
        ring = self._read_kek_keyring_file()
        if isinstance(ring, dict):
            keys = ring.get("keys")
            if isinstance(keys, dict):
                raw_val = keys.get(str(version))
                if isinstance(raw_val, str) and raw_val.strip():
                    raw = raw_val.strip()

        if raw is None:
            raw = os.getenv(f"HISTORY_KEK_V{version}")
        if not raw:
            return None
        try:
            key = base64.urlsafe_b64decode(raw.encode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid base64 for HISTORY_KEK version {version}") from e

        if len(key) != 32:
            raise ValueError(f"HISTORY_KEK version {version} must decode to 32 bytes (got {len(key)})")

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

    def _dek_aad(self, user_id: str, aad_email: str) -> bytes:
        # aad_email MUST be stable for the lifetime of the wrapped key.
        return f"history-dek|v1|user:{user_id}|email:{aad_email}".encode("utf-8")

    def _msg_aad(self, user_id: str, agent_name: str, role: str, timestamp_ms: int) -> bytes:
        # Bind ciphertext to non-secret metadata to detect tampering (e.g. role swapping to "system").
        return f"history-msg|v1|user:{user_id}|agent:{agent_name}|role:{role}|ts:{timestamp_ms}".encode("utf-8")

    def _wrap_dek(self, kek: bytes, user_id: str, aad_email: str, dek: bytes) -> Tuple[str, str]:
        AESGCM = self._require_aesgcm()
        nonce = secrets.token_bytes(12)
        aad = self._dek_aad(user_id, aad_email)
        wrapped = AESGCM(kek).encrypt(nonce, dek, aad)
        return self._b64e(wrapped), self._b64e(nonce)

    def _unwrap_dek(self, kek: bytes, user_id: str, aad_email: str, wrapped_b64: str, nonce_b64: str) -> bytes:
        AESGCM = self._require_aesgcm()
        wrapped = self._b64d(wrapped_b64)
        nonce = self._b64d(nonce_b64)
        aad = self._dek_aad(user_id, aad_email)
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

    def _dek_cache_key(self, user_id: str, dek_id: str) -> str:
        return f"{user_id}::{dek_id}"

    def _utc_day_id(self, timestamp_ms: int) -> str:
        # Use UTC day boundary to keep deterministic rotation across hosts.
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y%m%d")

    def _candidate_utc_day_ids(self, timestamp_ms: int) -> List[str]:
        """
        Candidate day IDs for key lookup.
        We prefer an explicit stored history_dek_id, but for legacy messages that don't have it
        we derive from timestamp_ms and also try adjacent UTC days to tolerate minor clock skew.
        """
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        day0 = dt.strftime("%Y%m%d")
        day_prev = (dt - timedelta(days=1)).strftime("%Y%m%d")
        day_next = (dt + timedelta(days=1)).strftime("%Y%m%d")
        # Keep order deterministic and unique
        out: List[str] = []
        for d in (day0, day_prev, day_next):
            if d not in out:
                out.append(d)
        return out

    async def _get_user_history_dek_if_present(self, user_id: str) -> Optional[bytes]:
        """
        Legacy: Return the user's single DEK if it exists (unwraps it using the KEK).

        Important: this MUST NOT create/overwrite keys. It's used for decryption on load.
        """
        # Check cache first
        cache_key = self._dek_cache_key(user_id, "legacy")
        if cache_key in self._dek_cache:
            return self._dek_cache[cache_key]

        doc_ref = self.db.collection("users").document(user_id)
        # Offload blocking Firestore call to a thread
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return None

        user_data = doc.to_dict() or {}
        wrapped = user_data.get("history_key_wrapped")
        wrapped_nonce = user_data.get("history_key_wrapped_nonce")
        stored_kek_version = user_data.get("history_key_kek_version") or 1
        stored_v = user_data.get("history_key_v")

        if not (wrapped and wrapped_nonce and stored_v == 1):
            return None

        try:
            kek_version = int(stored_kek_version)
        except Exception:
            return None

        kek = self._get_kek(kek_version)
        if not kek:
            return None

        # Prefer the stored AAD email used at key creation; fallback to current email/unknown.
        aad_email = user_data.get("history_key_email")
        if not isinstance(aad_email, str) or not aad_email:
            aad_email = user_data.get("email", "unknown")

        try:
            dek = self._unwrap_dek(kek, user_id, aad_email, wrapped, wrapped_nonce)
        except Exception:
            # Backwards compatibility: if email changed since wrap, older keys may have used "unknown".
            if aad_email != "unknown":
                try:
                    dek = self._unwrap_dek(kek, user_id, "unknown", wrapped, wrapped_nonce)
                except Exception:
                    return None
            else:
                return None
        if len(dek) != 32:
            return None

        # Store in cache
        self._dek_cache[cache_key] = dek
        return dek

    async def _get_or_create_user_history_dek(self, user_id: str) -> Tuple[bytes, int]:
        """
        Legacy: Return (dek_bytes, kek_version) for single-per-user DEK.

        Stores only the WRAPPED DEK in Firestore user doc.
        """
        # Check cache first
        cache_key = self._dek_cache_key(user_id, "legacy")
        if cache_key in self._dek_cache:
            # KEK version is stored in Firestore; default to active if unknown.
            return self._dek_cache[cache_key], self._get_active_kek_version()

        kek_version = self._get_active_kek_version()
        kek = self._get_kek(kek_version)
        if not kek:
            raise RuntimeError(
                f"Missing HISTORY_KEK for active version {kek_version} (required for history encryption)"
            )

        doc_ref = self.db.collection("users").document(user_id)
        # Offload blocking Firestore call to a thread
        doc = await asyncio.to_thread(doc_ref.get)
        user_data = doc.to_dict() if doc.exists else {}

        wrapped = user_data.get("history_key_wrapped")
        wrapped_nonce = user_data.get("history_key_wrapped_nonce")
        stored_kek_version = user_data.get("history_key_kek_version")
        stored_v = user_data.get("history_key_v")

        if wrapped and wrapped_nonce and stored_v == 1:
            try:
                stored_kek_version_int = int(stored_kek_version or 1)
            except Exception:
                stored_kek_version_int = 1

            stored_kek = self._get_kek(stored_kek_version_int)
            if stored_kek:
                aad_email = user_data.get("history_key_email")
                if not isinstance(aad_email, str) or not aad_email:
                    aad_email = user_data.get("email", "unknown")

                try:
                    dek = self._unwrap_dek(stored_kek, user_id, aad_email, wrapped, wrapped_nonce)
                except Exception:
                    if aad_email != "unknown":
                        dek = self._unwrap_dek(stored_kek, user_id, "unknown", wrapped, wrapped_nonce)
                    else:
                        dek = b""

                if len(dek) == 32:
                    # Optionally re-wrap to active KEK (lazy rotation) without touching messages.
                    if stored_kek_version_int != kek_version:
                        try:
                            wrapped_b64, wrapped_nonce_b64 = self._wrap_dek(kek, user_id, aad_email, dek)
                            data = {
                                "history_key_v": 1,
                                "history_key_kek_version": kek_version,
                                "history_key_wrapped": wrapped_b64,
                                "history_key_wrapped_nonce": wrapped_nonce_b64,
                                "history_key_email": aad_email,
                                "last_active": _utcnow_naive(),
                            }
                            await asyncio.to_thread(doc_ref.set, data, merge=True)
                        except Exception:
                            pass

                    self._dek_cache[cache_key] = dek
                    return dek, kek_version

        # Create + wrap a new DEK
        dek = secrets.token_bytes(32)
        aad_email = user_data.get("email", "unknown")
        if not isinstance(aad_email, str) or not aad_email:
            aad_email = "unknown"
        wrapped_b64, wrapped_nonce_b64 = self._wrap_dek(kek, user_id, aad_email, dek)

        # Merge into user doc (offload blocking set call)
        data = {
            "history_key_v": 1,
            "history_key_kek_version": kek_version,
            "history_key_wrapped": wrapped_b64,
            "history_key_wrapped_nonce": wrapped_nonce_b64,
            "history_key_email": aad_email,
            "last_active": _utcnow_naive(),
        }
        await asyncio.to_thread(doc_ref.set, data, merge=True)

        self._dek_cache[cache_key] = dek
        return dek, kek_version

    async def _get_user_history_dek_for_id_if_present(self, user_id: str, dek_id: str) -> Optional[bytes]:
        """
        Return the DEK for a given key id (e.g. UTC day YYYYMMDD) if present.
        Does NOT create keys.
        """
        cache_key = self._dek_cache_key(user_id, dek_id)
        if cache_key in self._dek_cache:
            return self._dek_cache[cache_key]

        doc_ref = self.db.collection("users").document(user_id)
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return None

        user_data = doc.to_dict() or {}
        keys = user_data.get("history_keys")
        if not isinstance(keys, dict):
            return None

        entry = keys.get(dek_id)
        if not isinstance(entry, dict):
            return None

        wrapped = entry.get("wrapped")
        wrapped_nonce = entry.get("nonce")
        stored_v = entry.get("v")
        stored_kek_version = entry.get("kek_version")
        aad_email = entry.get("aad_email") or user_data.get("email", "unknown")

        if not (wrapped and wrapped_nonce and stored_v == 1 and stored_kek_version):
            return None

        try:
            kek_version_int = int(stored_kek_version)
        except Exception:
            return None

        kek = self._get_kek(kek_version_int)
        if not kek:
            return None

        if not isinstance(aad_email, str) or not aad_email:
            aad_email = "unknown"

        try:
            dek = self._unwrap_dek(kek, user_id, aad_email, wrapped, wrapped_nonce)
        except Exception:
            if aad_email != "unknown":
                try:
                    dek = self._unwrap_dek(kek, user_id, "unknown", wrapped, wrapped_nonce)
                except Exception:
                    return None
            else:
                return None

        if len(dek) != 32:
            return None

        self._dek_cache[cache_key] = dek
        return dek

    async def _get_or_create_user_history_dek_for_day(
        self,
        user_id: str,
        timestamp_ms: int,
    ) -> Tuple[bytes, int, str]:
        """
        Per-day DEK rotation (UTC day). Returns (dek_bytes, kek_version, dek_id).
        Stores only WRAPPED DEKs in the user document under history_keys.<dek_id>.
        """
        dek_id = self._utc_day_id(timestamp_ms)
        cache_key = self._dek_cache_key(user_id, dek_id)
        if cache_key in self._dek_cache:
            return self._dek_cache[cache_key], self._get_active_kek_version(), dek_id

        active_kek_version = self._get_active_kek_version()
        active_kek = self._get_kek(active_kek_version)
        if not active_kek:
            raise RuntimeError(
                f"Missing HISTORY_KEK for active version {active_kek_version} (required for history encryption)"
            )

        doc_ref = self.db.collection("users").document(user_id)
        doc = await asyncio.to_thread(doc_ref.get)
        user_data = doc.to_dict() if doc.exists else {}

        keys = user_data.get("history_keys")
        if not isinstance(keys, dict):
            keys = {}

        entry = keys.get(dek_id)
        if isinstance(entry, dict):
            wrapped = entry.get("wrapped")
            wrapped_nonce = entry.get("nonce")
            stored_v = entry.get("v")
            stored_kek_version = entry.get("kek_version")
            aad_email = entry.get("aad_email") or user_data.get("email", "unknown")
            if wrapped and wrapped_nonce and stored_v == 1 and stored_kek_version:
                try:
                    stored_kek_version_int = int(stored_kek_version)
                except Exception:
                    stored_kek_version_int = active_kek_version

                stored_kek = self._get_kek(stored_kek_version_int)
                if stored_kek and isinstance(aad_email, str) and aad_email:
                    try:
                        dek = self._unwrap_dek(stored_kek, user_id, aad_email, wrapped, wrapped_nonce)
                    except Exception:
                        if aad_email != "unknown":
                            dek = self._unwrap_dek(stored_kek, user_id, "unknown", wrapped, wrapped_nonce)
                        else:
                            dek = b""

                    if len(dek) == 32:
                        # Lazy rotate wrapping KEK to the active version (no message re-encryption).
                        if stored_kek_version_int != active_kek_version:
                            try:
                                new_wrapped, new_nonce = self._wrap_dek(active_kek, user_id, aad_email, dek)
                                new_entry = {
                                    "v": 1,
                                    "kek_version": active_kek_version,
                                    "wrapped": new_wrapped,
                                    "nonce": new_nonce,
                                    "aad_email": aad_email,
                                    "created_day_utc": dek_id,
                                    "rotated_at": datetime.utcnow(),
                                }
                                # Update ONLY this day's entry to avoid clobbering other keys.
                                try:
                                    await asyncio.to_thread(
                                        doc_ref.update,
                                        {
                                            f"history_keys.{dek_id}": new_entry,
                                            "history_keys_v": 1,
                                            "last_active": _utcnow_naive(),
                                        },
                                    )
                                except Exception:
                                    # If the doc doesn't exist or update fails, fallback to set(merge).
                                    await asyncio.to_thread(
                                        doc_ref.set,
                                        {
                                            "history_keys": {dek_id: new_entry},
                                            "history_keys_v": 1,
                                            "last_active": _utcnow_naive(),
                                        },
                                        merge=True,
                                    )
                            except Exception:
                                pass

                        self._dek_cache[cache_key] = dek
                        return dek, active_kek_version, dek_id

        # Create a new DEK for this UTC day
        dek = secrets.token_bytes(32)
        aad_email = user_data.get("email", "unknown")
        if not isinstance(aad_email, str) or not aad_email:
            aad_email = "unknown"
        wrapped_b64, wrapped_nonce_b64 = self._wrap_dek(active_kek, user_id, aad_email, dek)

        new_entry = {
            "v": 1,
            "kek_version": active_kek_version,
            "wrapped": wrapped_b64,
            "nonce": wrapped_nonce_b64,
            "aad_email": aad_email,
            "created_day_utc": dek_id,
            "created_at": _utcnow_naive(),
        }

        # Update ONLY this day's entry to avoid clobbering other keys.
        try:
            await asyncio.to_thread(
                doc_ref.update,
                {
                    f"history_keys.{dek_id}": new_entry,
                    "history_keys_v": 1,
                    "last_active": _utcnow_naive(),
                },
            )
        except Exception:
            await asyncio.to_thread(
                doc_ref.set,
                {"history_keys": {dek_id: new_entry}, "history_keys_v": 1, "last_active": _utcnow_naive()},
                merge=True,
            )

        self._dek_cache[cache_key] = dek
        return dek, active_kek_version, dek_id

    async def rotate_history_keys_for_user(self, user_id: str, target_kek_version: Optional[int] = None) -> bool:
        """
        Re-wrap (rotate) wrapped history DEKs for a single user to a target KEK version.
        This does NOT re-encrypt any messages; it only updates wrapped key blobs in the user doc.
        """
        try:
            if target_kek_version is None:
                target_kek_version = self._get_active_kek_version()

            try:
                target_kek_version_int = int(target_kek_version)
            except Exception:
                return False

            if target_kek_version_int < 1:
                return False

            target_kek = self._get_kek(target_kek_version_int)
            if not target_kek:
                return False

            doc_ref = self.db.collection("users").document(user_id)
            doc = await asyncio.to_thread(doc_ref.get)
            if not doc.exists:
                return False

            user_data = doc.to_dict() or {}

            updates: Dict[str, Any] = {}

            # Rotate legacy single key if present
            legacy_wrapped = user_data.get("history_key_wrapped")
            legacy_nonce = user_data.get("history_key_wrapped_nonce")
            legacy_v = user_data.get("history_key_v")
            legacy_kek_version = user_data.get("history_key_kek_version") or 1
            legacy_aad_email = user_data.get("history_key_email") or user_data.get("email", "unknown")
            if (
                legacy_wrapped
                and legacy_nonce
                and legacy_v == 1
                and isinstance(legacy_aad_email, str)
                and legacy_aad_email
            ):
                try:
                    legacy_kek_version_int = int(legacy_kek_version)
                except Exception:
                    legacy_kek_version_int = 1

                if legacy_kek_version_int != target_kek_version_int:
                    legacy_kek = self._get_kek(legacy_kek_version_int)
                    if legacy_kek:
                        try:
                            dek = self._unwrap_dek(legacy_kek, user_id, legacy_aad_email, legacy_wrapped, legacy_nonce)
                        except Exception:
                            if legacy_aad_email != "unknown":
                                dek = self._unwrap_dek(legacy_kek, user_id, "unknown", legacy_wrapped, legacy_nonce)
                            else:
                                dek = b""

                        if len(dek) == 32:
                            new_wrapped, new_nonce = self._wrap_dek(target_kek, user_id, legacy_aad_email, dek)
                            updates.update(
                                {
                                    "history_key_wrapped": new_wrapped,
                                    "history_key_wrapped_nonce": new_nonce,
                                    "history_key_kek_version": target_kek_version_int,
                                    "history_key_email": legacy_aad_email,
                                }
                            )

            # Rotate per-day keys if present
            keys = user_data.get("history_keys")
            if isinstance(keys, dict) and keys:
                changed = False
                for dek_id, entry in list(keys.items()):
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("v") != 1:
                        continue
                    wrapped = entry.get("wrapped")
                    nonce = entry.get("nonce")
                    kek_version = entry.get("kek_version")
                    aad_email = entry.get("aad_email") or user_data.get("email", "unknown")
                    if not (wrapped and nonce and kek_version and isinstance(aad_email, str) and aad_email):
                        continue

                    try:
                        kek_version_int = int(kek_version)
                    except Exception:
                        continue

                    if kek_version_int == target_kek_version_int:
                        continue

                    old_kek = self._get_kek(kek_version_int)
                    if not old_kek:
                        continue

                    try:
                        dek = self._unwrap_dek(old_kek, user_id, aad_email, wrapped, nonce)
                    except Exception:
                        if aad_email != "unknown":
                            try:
                                dek = self._unwrap_dek(old_kek, user_id, "unknown", wrapped, nonce)
                            except Exception:
                                continue
                        else:
                            continue

                    if len(dek) != 32:
                        continue

                    new_wrapped, new_nonce = self._wrap_dek(target_kek, user_id, aad_email, dek)
                    new_entry = {
                        **entry,
                        "kek_version": target_kek_version_int,
                        "wrapped": new_wrapped,
                        "nonce": new_nonce,
                        "rotated_at": _utcnow_naive(),
                    }
                    # Update using field-path to avoid clobbering other keys.
                    updates[f"history_keys.{dek_id}"] = new_entry
                    changed = True

                if changed:
                    updates["history_keys_v"] = 1

            if updates:
                updates["last_active"] = _utcnow_naive()
                # update() keeps existing nested map keys intact
                await asyncio.to_thread(doc_ref.update, updates)

            return True
        except Exception:
            return False
    
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
                user_session.last_active = _utcnow_naive()
                
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
                'last_active': _utcnow_naive()
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
        timestamp = _utcnow_naive()
        timestamp_ms = int(timestamp.timestamp() * 1000)
        
        try:
            conversation_id = f"{user_id}_{agent_name}"
            doc_ref = self.db.collection('conversations').document(conversation_id)

            # Encrypt content (Firestore is treated as untrusted)
            if HISTORY_DEK_ROTATION_DAYS_ENABLED:
                dek, kek_version, dek_id = await self._get_or_create_user_history_dek_for_day(
                    user_id=user_id,
                    timestamp_ms=timestamp_ms,
                )
            else:
                dek, kek_version = await self._get_or_create_user_history_dek(user_id)
                dek_id = "legacy"
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
                # Legacy field kept for backward compatibility; stores KEK version used for wrapping.
                "key_version": kek_version,
                # New fields for per-day keying
                "history_dek_id": dek_id,
                "history_kek_version": kek_version,
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
        chat_ctx = self._new_chat_context()
        
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
            self._chat_ctx_add(
                chat_ctx,
                role="system",
                content=f"Notice: User is returning. Found {len(messages)} total messages, loading last {len(limited_messages)} from previous conversations (max {max_messages}):",
            )
            
            logger.info(f"Firebase history: total={len(messages)}, loaded={len(limited_messages)}, limit={max_messages}")
            print(f"Firebase history: total={len(messages)}, loaded={len(limited_messages)}, limit={max_messages}", flush=True)
            
            loaded_summary = []
            # Group messages by relative date
            current_date = None
            for msg in limited_messages:
                relative_date = self._calculate_relative_date(msg['timestamp'])
                
                if current_date != relative_date:
                    self._chat_ctx_add(
                        chat_ctx,
                        role="system",
                        content=f"\n--- Previous conversation from {relative_date} ---",
                    )
                    current_date = relative_date

                # Decrypt encrypted messages; allow legacy plaintext fallback.
                text = msg.get("content")
                if msg.get("content_enc") and msg.get("nonce"):
                    try:
                        ts_ms = msg.get("timestamp_ms")
                        if ts_ms is None:
                            # Best-effort fallback for early records.
                            ts = msg.get("timestamp")
                            ts_ms = int(ts.timestamp() * 1000) if isinstance(ts, datetime) else 0

                        dek_id = msg.get("history_dek_id")
                        dek = None
                        if isinstance(dek_id, str) and dek_id and dek_id != "legacy":
                            dek = await self._get_user_history_dek_for_id_if_present(user_id, dek_id)

                        # If dek_id isn't present OR explicit key is missing, try derived candidates.
                        if not dek:
                            for derived_id in self._candidate_utc_day_ids(int(ts_ms)):
                                dek = await self._get_user_history_dek_for_id_if_present(user_id, derived_id)
                                if dek:
                                    break
                            if not dek:
                                dek = await self._get_user_history_dek_if_present(user_id)

                        if not dek:
                            logger.warning(
                                f"Skipping encrypted history message for user {user_id}: missing history key in user doc"
                            )
                            continue

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
                    self._chat_ctx_add(chat_ctx, role=role, content=text)
                    loaded_summary.append(f"{role}: {text[:20]}...")
            
            logger.info(f"Firebase history: Loaded {len(loaded_summary)} messages: {', '.join(loaded_summary)}")
            
        except Exception as e:
            logger.error(f"Error loading chat history: {e}")
            print(f"Firebase history: error loading - {e}", flush=True)
        
        return chat_ctx

    def _new_chat_context(self) -> Any:
        """
        Create an empty ChatContext across livekit-agents versions.
        Some versions expose ChatContext.empty(); others can be instantiated directly.
        """
        ChatContext = getattr(llm, "ChatContext", None)
        if ChatContext is None:
            raise RuntimeError("livekit.agents.llm.ChatContext not available")

        empty = getattr(ChatContext, "empty", None)
        if callable(empty):
            return empty()

        # Fallbacks for older APIs
        try:
            return ChatContext()
        except Exception:
            try:
                return ChatContext(messages=[])
            except Exception:
                return ChatContext([])

    def _chat_ctx_add(self, chat_ctx: Any, role: str, content: str) -> None:
        """
        Add a message to a ChatContext across livekit-agents versions.
        """
        add_message = getattr(chat_ctx, "add_message", None)
        if callable(add_message):
            add_message(role=role, content=content)
            return

        # Minimal fallback: append to messages/items if present.
        msg_obj: Any
        ChatMessage = getattr(llm, "ChatMessage", None)
        if ChatMessage is not None:
            try:
                msg_obj = ChatMessage(role=role, content=content)
            except Exception:
                msg_obj = {"role": role, "content": content}
        else:
            msg_obj = {"role": role, "content": content}

        if hasattr(chat_ctx, "messages") and isinstance(getattr(chat_ctx, "messages"), list):
            chat_ctx.messages.append(msg_obj)
            return
        if hasattr(chat_ctx, "items") and isinstance(getattr(chat_ctx, "items"), list):
            chat_ctx.items.append(msg_obj)
            return

        raise RuntimeError("Unsupported ChatContext API: cannot add message")
    
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
                'last_memory_extraction': _utcnow_naive()
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
