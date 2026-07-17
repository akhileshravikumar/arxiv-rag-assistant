from app.services.embedding_service import EmbeddingService


def main() -> None:
    service = EmbeddingService()

    text = (
        "Retrieval-augmented generation combines "
        "language models with external knowledge."
    )

    embedding = service.embed_text(text)

    print(f"Input text: {text}")
    print(f"Embedding dimensions: {len(embedding)}")
    print(f"First five values: {embedding[:5]}")


if __name__ == "__main__":
    main()