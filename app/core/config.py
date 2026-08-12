import os

from dotenv import load_dotenv


load_dotenv()


# Shared by the embedding service and the Chunk model's vector column.
# Changing this requires recreating the chunks table, since pgvector
# fixes the dimension at column definition time.
EMBEDDING_DIMENSION = int(
    os.getenv(
        "EMBEDDING_DIMENSION",
        "384",
    )
)

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "text-embedding-3-small",
)
