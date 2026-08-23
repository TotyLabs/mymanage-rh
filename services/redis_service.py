import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

logger = logging.getLogger("dircom.payroll.redis")


class RedisService:
    def __init__(self):
        if not config.REDIS_URL:
            raise RuntimeError("REDIS_URL is not configured")
        if redis is None:
            raise RuntimeError("redis package is required to use RedisService")

        self._client = redis.from_url(config.REDIS_URL, decode_responses=True, health_check_interval=30)
        self._prefix = config.REDIS_KEY_PREFIX or "mymanagerh"

    def _key(self, name: str) -> str:
        return f"{self._prefix}:{name}"

    def ping(self) -> bool:
        try:
            return self._client.ping()
        except Exception as exc:
            logger.warning("redis.ping_failed: %s", exc)
            return False

    def set_session(self, token_hash: str, session_data: Dict[str, Any], expires_seconds: int) -> None:
        if expires_seconds <= 0:
            return
        key = self._key(f"session:{token_hash}")
        payload = json.dumps(session_data, default=str)
        user_sessions_key = self._key(f"user_sessions:{session_data.get('user_id')}")

        pipe = self._client.pipeline()
        pipe.setex(key, expires_seconds, payload)
        if session_data.get("user_id"):
            pipe.sadd(user_sessions_key, token_hash)
        pipe.execute()

    def get_session(self, token_hash: str) -> Optional[Dict[str, Any]]:
        key = self._key(f"session:{token_hash}")
        value = self._client.get(key)
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("redis.session_decode_failed: token_hash=%s", token_hash)
            return None

    def delete_session(self, token_hash: str, user_id: Optional[str] = None) -> None:
        key = self._key(f"session:{token_hash}")
        if user_id:
            user_sessions_key = self._key(f"user_sessions:{user_id}")
            pipe = self._client.pipeline()
            pipe.delete(key)
            pipe.srem(user_sessions_key, token_hash)
            pipe.execute()
        else:
            self._client.delete(key)

    def delete_sessions_for_user(self, user_id: str) -> None:
        user_sessions_key = self._key(f"user_sessions:{user_id}")
        token_hashes = self._client.smembers(user_sessions_key)
        if not token_hashes:
            self._client.delete(user_sessions_key)
            return

        pipe = self._client.pipeline()
        for token_hash in token_hashes:
            pipe.delete(self._key(f"session:{token_hash}"))
        pipe.delete(user_sessions_key)
        pipe.execute()

    def set_otp_code(self, context_hash: str, payload: Dict[str, Any], expires_seconds: int) -> None:
        if expires_seconds <= 0:
            return
        key = self._key(f"otp:{context_hash}")
        self._client.setex(key, expires_seconds, json.dumps(payload, default=str))

    def get_otp_code(self, context_hash: str) -> Optional[Dict[str, Any]]:
        key = self._key(f"otp:{context_hash}")
        value = self._client.get(key)
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("redis.otp_decode_failed: context_hash=%s", context_hash)
            return None

    def delete_otp_code(self, context_hash: str) -> None:
        self._client.delete(self._key(f"otp:{context_hash}"))

    def increment_otp_attempts(self, context_hash: str) -> Optional[int]:
        key = self._key(f"otp:{context_hash}")
        pipe = self._client.pipeline()
        pipe.get(key)
        pipe.ttl(key)
        data, ttl = pipe.execute()
        if not data or ttl is None or ttl <= 0:
            return None
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return None
        attempts = int(payload.get("attempts", 0)) + 1
        payload["attempts"] = attempts
        self._client.setex(key, ttl, json.dumps(payload, default=str))
        return attempts


redis_service: Optional[RedisService] = None
if config.REDIS_URL:
    try:
        redis_service = RedisService()
    except Exception as exc:  # pragma: no cover
        logger.error("redis_service_failed: %s", exc)
        redis_service = None
