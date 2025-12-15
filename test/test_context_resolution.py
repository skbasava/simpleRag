from rag.context_resolver import resolve_context
from rag.session import RAGSession

def test_missing_project_and_version():
    session = RAGSession()
    project, version, clarification = resolve_context(
        "What is the MPU access range?",
        session
    )

    assert project is None
    assert version is None
    assert "Project name" in clarification
    assert "version" in clarification


def test_project_only():
    session = RAGSession()
    project, version, clarification = resolve_context(
        "What is the MPU access range for KAANAPALI?",
        session
    )

    assert project is None
    assert version is None
    assert "version" in clarification


def test_project_and_version():
    session = RAGSession()
    project, version, clarification = resolve_context(
        "KAANAPALI version 5.3 MPU access",
        session
    )

    assert clarification is None
    assert project == "KAANAPALI"
    assert version == "5.3"
