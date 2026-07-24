import os

from dotenv import load_dotenv
from redis import Redis


load_dotenv()


class RedisService:
    def __init__(self) -> None:
        redis_url = os.getenv(
            "REDIS_URL",
            "redis://localhost:6379/2",
        )

        self.client = Redis.from_url(
            redis_url,
            decode_responses=True,
        )

    def ping(self) -> bool:
        return bool(self.client.ping())

    def acquire_lock(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        """
        Acquire a lock only when it does not already exist.
        """
        return bool(
            self.client.set(
                name=key,
                value=value,
                nx=True,
                ex=ttl_seconds,
            )
        )

    def release_lock(
        self,
        key: str,
        expected_value: str,
    ) -> bool:
        """
        Delete a lock only when the current task owns it.
        """
        current_value = self.client.get(key)

        if current_value != expected_value:
            return False

        return bool(self.client.delete(key))


redis_service = RedisService()