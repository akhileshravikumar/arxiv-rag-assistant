import os


# Unit tests exercise the service layer with fakes and never open a
# connection. These defaults keep the suite hermetic: it will not read
# the developer's real credentials from .env, and cannot accidentally
# reach a live database or a paid API.
#
# load_dotenv() does not overwrite variables that are already set, so
# setting them here takes precedence over .env.
TEST_ENVIRONMENT = {
    "DATABASE_URL": (
        "postgresql+psycopg://test:test@localhost:5432/test_db"
    ),
    "REDIS_URL": "redis://localhost:6379/15",
    "OPENAI_API_KEY": "test-key-not-used",
    "OPENAI_MODEL": "test-model",
    "EMBEDDING_MODEL": "test-embedding-model",
    "EMBEDDING_DIMENSION": "384",
    "COHERE_API_KEY": "",
    "CACHE_KEY_PREFIX": "arxiv-rag-test",
}


for name, value in TEST_ENVIRONMENT.items():
    os.environ.setdefault(name, value)
