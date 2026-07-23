from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_me_requires_authentication():
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_chat_requires_authentication():
    response = client.post(
        "/chat",
        json={
            "question": "What is RAG?",
            "candidate_k": 10,
            "final_k": 3,
        },
    )

    assert response.status_code == 401