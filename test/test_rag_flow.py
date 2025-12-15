import pytest
from rag.service import RAGService

@pytest.fixture
def rag_service(monkeypatch):
    service = RAGService()

    # Mock LLM call
    monkeypatch.setattr(
        "llm.client.submit_prompt",
        lambda prompt: "MOCK_LLM_RESPONSE"
    )

    return service


def test_rag_requires_context(rag_service):
    answer = rag_service.answer("What is the MPU access range?")

    assert "Project name" in answer


def test_rag_full_flow(rag_service):
    # First clarification
    answer1 = rag_service.answer("What is the MPU access range?")
    assert "Project name" in answer1

    # Provide missing context
    answer2 = rag_service.answer("KAANAPALI version 5.3")
    assert answer2 == "MOCK_LLM_RESPONSE"
