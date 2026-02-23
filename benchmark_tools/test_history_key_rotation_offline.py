#!/usr/bin/env python3
import asyncio
import base64
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8")


def _dt_from_ms(ms: int) -> datetime:
    # Use naive UTC datetime for Firestore-like behavior, without deprecated utcfromtimestamp().
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def _set_field_path(doc: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Dict[str, Any] = doc
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


@dataclass
class _FakeSnapshot:
    exists: bool
    _data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class _ArrayUnion:
    def __init__(self, values):
        self.values = list(values)


class _FakeDocRef:
    def __init__(self, store: Dict[str, Dict[str, Any]], key: str):
        self._store = store
        self._key = key

    def get(self) -> _FakeSnapshot:
        if self._key not in self._store:
            return _FakeSnapshot(False, {})
        return _FakeSnapshot(True, self._store[self._key])

    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        if not merge or self._key not in self._store:
            self._store[self._key] = dict(data)
            return
        cur = self._store[self._key]
        for k, v in data.items():
            cur[k] = v

    def update(self, data: Dict[str, Any]) -> None:
        if self._key not in self._store:
            raise RuntimeError("document does not exist")
        cur = self._store[self._key]
        for k, v in data.items():
            if isinstance(v, _ArrayUnion):
                existing = cur.get(k)
                if not isinstance(existing, list):
                    existing = []
                existing.extend(v.values)
                cur[k] = existing
                continue

            if "." in k:
                _set_field_path(cur, k, v)
            else:
                cur[k] = v

    def delete(self) -> None:
        self._store.pop(self._key, None)


class _FakeCollection:
    def __init__(self, root: Dict[str, Dict[str, Any]], name: str):
        self._root = root
        self._name = name

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._root, f"{self._name}/{doc_id}")


class _FakeDB:
    def __init__(self):
        self._docs: Dict[str, Dict[str, Any]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._docs, name)


class HistoryKeyRotationOfflineTests(unittest.IsolatedAsyncioTestCase):
    def _content_text(self, msg: Any) -> str:
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            out = ""
            for item in content:
                if hasattr(item, "text"):
                    out += str(item.text)
                elif isinstance(item, str):
                    out += item
                elif isinstance(item, dict) and "text" in item:
                    out += str(item["text"])
                else:
                    out += str(item)
            return out
        s = str(content)
        # Some versions stringify list-like content as "['text']"
        if s.startswith("['") and s.endswith("']") and len(s) >= 4:
            return s[2:-2]
        return s

    async def test_decrypt_across_days_and_kek_rotation(self):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        except Exception:
            self.skipTest("cryptography not available")

        # Import the module under test
        import sys
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from custom_components import firebase_user_manager as fum

        # Patch ArrayUnion in the imported module so store_message/update works offline
        fum.firestore.ArrayUnion = _ArrayUnion  # type: ignore[attr-defined]

        with tempfile.TemporaryDirectory() as td:
            keyring_path = os.path.join(td, "history-kek-keyring.json")

            # Write keyring with KEK v1 + v2 (never printed)
            import json
            import secrets

            kek_v1 = secrets.token_bytes(32)
            kek_v2 = secrets.token_bytes(32)
            with open(keyring_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active_version": 1,
                        "keys": {"1": _b64url(kek_v1), "2": _b64url(kek_v2)},
                    },
                    f,
                )

            os.environ["HISTORY_KEK_KEYRING_PATH"] = keyring_path

            # Build an instance without running firebase initialization
            mgr = object.__new__(fum.FirebaseUserManager)
            mgr._db = _FakeDB()
            mgr._keks = {}
            mgr._dek_cache = {}
            mgr._kek_keyring_cache = None
            mgr._kek_keyring_mtime = None

            user_id = "test_user_rotation"
            agent_name = "juno"
            email = "test@example.com"

            # Seed user doc (email used for key AAD binding)
            mgr.db.collection("users").document(user_id).set({"email": email})

            # Two messages on two different UTC days to force DEK rotation
            ts1_ms = 1769953899810
            ts2_ms = ts1_ms + 24 * 60 * 60 * 1000
            pt1 = "hello day 1"
            pt2 = "hello day 2"

            dek1, kek_ver_1, dek_id_1 = await mgr._get_or_create_user_history_dek_for_day(user_id, ts1_ms)
            c1, n1 = mgr._encrypt_content(
                dek=dek1,
                user_id=user_id,
                agent_name=agent_name,
                role="assistant",
                timestamp_ms=ts1_ms,
                plaintext=pt1,
            )

            dek2, kek_ver_2, dek_id_2 = await mgr._get_or_create_user_history_dek_for_day(user_id, ts2_ms)
            c2, n2 = mgr._encrypt_content(
                dek=dek2,
                user_id=user_id,
                agent_name=agent_name,
                role="assistant",
                timestamp_ms=ts2_ms,
                plaintext=pt2,
            )

            conv_id = f"{user_id}_{agent_name}"
            mgr.db.collection("conversations").document(conv_id).set(
                {
                    "messages": [
                        {
                            "user_id": user_id,
                            "agent_name": agent_name,
                            "role": "assistant",
                            "timestamp": _dt_from_ms(ts1_ms),
                            "timestamp_ms": ts1_ms,
                            "content_enc": c1,
                            "nonce": n1,
                            "enc_v": 1,
                            "key_version": kek_ver_1,
                            "history_dek_id": dek_id_1,
                            "history_kek_version": kek_ver_1,
                        },
                        {
                            "user_id": user_id,
                            "agent_name": agent_name,
                            "role": "assistant",
                            "timestamp": _dt_from_ms(ts2_ms),
                            "timestamp_ms": ts2_ms,
                            "content_enc": c2,
                            "nonce": n2,
                            "enc_v": 1,
                            "key_version": kek_ver_2,
                            "history_dek_id": dek_id_2,
                            "history_kek_version": kek_ver_2,
                        },
                    ],
                    "created_at": _dt_from_ms(ts1_ms),
                    "updated_at": _dt_from_ms(ts2_ms),
                    "user_id": user_id,
                    "agent_name": agent_name,
                }
            )

            chat_ctx = await mgr.load_chat_history(user_id=user_id, agent_name=agent_name, max_messages=50)
            msgs = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", [])
            recovered = [m for m in msgs if getattr(m, "role", None) == "assistant"]
            self.assertGreaterEqual(len(recovered), 2)
            recovered_text = [self._content_text(m) for m in recovered]
            self.assertIn(pt1, recovered_text)
            self.assertIn(pt2, recovered_text)

            # Simulate KEK rotation by switching active_version to 2 and re-wrapping user keys
            with open(keyring_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active_version": 2,
                        "keys": {"1": _b64url(kek_v1), "2": _b64url(kek_v2)},
                    },
                    f,
                )

            ok = await mgr.rotate_history_keys_for_user(user_id)
            self.assertTrue(ok)

            chat_ctx2 = await mgr.load_chat_history(user_id=user_id, agent_name=agent_name, max_messages=50)
            msgs2 = getattr(chat_ctx2, "messages", None) or getattr(chat_ctx2, "items", [])
            recovered2 = [m for m in msgs2 if getattr(m, "role", None) == "assistant"]
            recovered2_text = [self._content_text(m) for m in recovered2]
            self.assertIn(pt1, recovered2_text)
            self.assertIn(pt2, recovered2_text)


if __name__ == "__main__":
    unittest.main()

