import json
import os
from typing import Any

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import RedisError

from dataclasses import dataclass


load_dotenv()

@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int

class RedisService:
    def __init__(self) -> None:
        redis_url = os.getenv(
            "REDIS_URL",
            "redis://localhost:6379/2",
        )

        self.client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except RedisError:
            return False

    def get_json(
        self,
        key: str,
    ) -> dict[str, Any] | list[Any] | None:
        """
        Retrieve and deserialize a JSON cache value.
        """
        try:
            raw_value = self.client.get(key)

            if raw_value is None:
                return None

            return json.loads(raw_value)

        except (
            RedisError,
            json.JSONDecodeError,
        ):
            return None

    def set_json(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        ttl_seconds: int,
    ) -> bool:
        """
        Serialize and cache a value with expiration.
        """
        if ttl_seconds < 1:
            raise ValueError(
                "ttl_seconds must be positive."
            )

        serialized_value = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        try:
            return bool(
                self.client.set(
                    name=key,
                    value=serialized_value,
                    ex=ttl_seconds,
                )
            )
        except RedisError:
            return False

    def delete(
        self,
        key: str,
    ) -> bool:
        try:
            return bool(
                self.client.delete(key)
            )
        except RedisError:
            return False

    def get_integer(
        self,
        key: str,
        default: int = 0,
    ) -> int:
        try:
            raw_value = self.client.get(key)

            if raw_value is None:
                return default

            return int(raw_value)

        except (
            RedisError,
            TypeError,
            ValueError,
        ):
            return default

    def increment(
        self,
        key: str,
    ) -> int:
        try:
            return int(
                self.client.incr(key)
            )
        except RedisError as exc:
            raise RuntimeError(
                "Could not increment Redis value."
            ) from exc

    def acquire_lock(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        try:
            return bool(
                self.client.set(
                    name=key,
                    value=value,
                    nx=True,
                    ex=ttl_seconds,
                )
            )
        except RedisError:
            return False

    def release_lock(
        self,
        key: str,
        expected_value: str,
    ) -> bool:
        """
        Release a lock only when this caller still owns it.
        """
        release_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            result = self.client.eval(
                release_script,
                1,
                key,
                expected_value,
            )

            return bool(result)

        except RedisError:
            return False

    def check_rate_limit(
    self,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
        if limit < 1:
            raise ValueError(
                "Rate-limit value must be positive."
            )

        if window_seconds < 1:
            raise ValueError(
                "Rate-limit window must be positive."
            )

        script = """
        local current = redis.call(
            "INCR",
            KEYS[1]
        )

        if current == 1 then
            redis.call(
                "EXPIRE",
                KEYS[1],
                ARGV[1]
            )
        end

        local ttl = redis.call(
            "TTL",
            KEYS[1]
        )

        return {
            current,
            ttl
        }
        """

        try:
            result = self.client.eval(
                script,
                1,
                key,
                window_seconds,
            )

            current_count = int(result[0])
            ttl = max(
                int(result[1]),
                0,
            )

            remaining = max(
                limit - current_count,
                0,
            )

            return RateLimitResult(
                allowed=(
                    current_count <= limit
                ),
                limit=limit,
                remaining=remaining,
                retry_after_seconds=ttl,
            )

        except RedisError as exc:
            raise RuntimeError(
                "Rate-limit service unavailable."
            ) from exc


redis_service = RedisService()