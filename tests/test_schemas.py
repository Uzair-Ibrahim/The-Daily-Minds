import pytest
from pydantic import ValidationError

from backend.schemas import AskRequest, AskResponse, SearchResult
from backend.services.provenance import utc_now


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_question_bounds(question):
    with pytest.raises(ValidationError):
        AskRequest(question=question)


@pytest.mark.parametrize("count", [0, 9, True, "5"])
def test_source_bounds(count):
    with pytest.raises(ValidationError):
        AskRequest(question="test", max_sources=count)


def test_unknown_citation_rejected():
    with pytest.raises(ValidationError):
        AskResponse(answer="Unsupported", status="ok", citations=["invented"],
                    queried_at_utc=utc_now(), freshness="not_retrieved", elapsed_ms=0)


def test_trim_and_extra_fields():
    assert AskRequest(question="  test  ").question == "test"
    with pytest.raises(ValidationError):
        AskRequest(question="test", arbitrary_tool="shell")


def test_search_cannot_report_success_without_data():
    with pytest.raises(ValidationError):
        SearchResult(status="ok", queried_at_utc=utc_now())
