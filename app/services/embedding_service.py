from collections.abc import Sequence

from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSION = 1024

QUERY_INSTRUCTION = (
    "Represent this sentence for searching relevant passages: "
)


class EmbeddingService:
    def __init__(self) -> None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")

        self.model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

        print("Embedding model loaded.")

    def embed_text(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_query(self, query: str) -> list[float]:
        """
        Generate an embedding for a search query.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError("Search query cannot be empty.")

        instructed_query = (
            f"{QUERY_INSTRUCTION}{cleaned_query}"
        )

        embedding = self.model.encode(
            instructed_query,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        vector = embedding.tolist()

        if len(vector) != EMBEDDING_DIMENSION:
            raise RuntimeError(
                "Unexpected query embedding dimension: "
                f"expected {EMBEDDING_DIMENSION}, "
                f"received {len(vector)}."
            )

        return vector

    def embed_documents(
        self,
        texts: Sequence[str],
        batch_size: int = 16,
    ) -> list[list[float]]:
        if not texts:
            return []

        cleaned_texts: list[str] = []

        for index, text in enumerate(texts):
            cleaned_text = text.strip()

            if not cleaned_text:
                raise ValueError(
                    f"Cannot embed empty text at position {index}."
                )

            cleaned_texts.append(cleaned_text)

        embeddings = self.model.encode(
            cleaned_texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        if embeddings.ndim != 2:
            raise RuntimeError(
                "The embedding model returned an unexpected shape."
            )

        if embeddings.shape[1] != EMBEDDING_DIMENSION:
            raise RuntimeError(
                "Unexpected embedding dimension: "
                f"expected {EMBEDDING_DIMENSION}, "
                f"received {embeddings.shape[1]}."
            )

        return embeddings.tolist()