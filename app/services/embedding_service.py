from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSION = 1024


class EmbeddingService:
    def __init__(self) -> None:
        self.model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

    def embed_text(self, text: str) -> list[float]:
        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError("Cannot embed empty text.")

        embedding = self.model.encode(
            cleaned_text,
            normalize_embeddings=True,
        )

        vector = embedding.tolist()

        if len(vector) != EMBEDDING_DIMENSION:
            raise RuntimeError(
                "Unexpected embedding dimension: "
                f"expected {EMBEDDING_DIMENSION}, "
                f"received {len(vector)}."
            )

        return vector