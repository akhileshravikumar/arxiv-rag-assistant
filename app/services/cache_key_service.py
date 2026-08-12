import hashlib
import json
import os
import re
from typing import Any

from dotenv import load_dotenv


load_dotenv()


CACHE_KEY_PREFIX = os.getenv(
    "CACHE_KEY_PREFIX",
    "arxiv-rag",
)


class CacheKeyService:
    @staticmethod
    def normalize_text(
        text: str,
    ) -> str:
        """
        Normalize insignificant whitespace and casing.
        """
        return re.sub(
            r"\s+",
            " ",
            text.strip().lower(),
        )

    @staticmethod
    def stable_hash(
        value: Any,
    ) -> str:
        serialized = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

    def answer_key(
        self,
        *,
        session_id: str,
        question: str,
        candidate_k: int,
        final_k: int,
        model: str,
        corpus_version: int,
    ) -> str:
        payload = {
            "session_id": session_id,
            "question": self.normalize_text(
                question
            ),
            "candidate_k": candidate_k,
            "final_k": final_k,
            "model": model,
            "corpus_version": corpus_version,
        }

        digest = self.stable_hash(payload)

        return (
            f"{CACHE_KEY_PREFIX}:"
            f"answer:v1:{digest}"
        )

    def query_embedding_key(
        self,
        *,
        query: str,
        embedding_model: str,
    ) -> str:
        payload = {
            "query": self.normalize_text(query),
            "embedding_model": embedding_model,
        }

        digest = self.stable_hash(payload)

        return (
            f"{CACHE_KEY_PREFIX}:"
            f"query-embedding:v1:{digest}"
        )

    def corpus_version_key(
        self,
        session_id: str,
    ) -> str:
        return (
            f"{CACHE_KEY_PREFIX}:"
            f"corpus-version:{session_id}"
        )