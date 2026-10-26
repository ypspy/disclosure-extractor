from pydantic import BaseModel

from dart_parser.fallback.llm_client import extract_with_slm
from dart_parser.fallback.schemas import DARTTableExtraction


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> DARTTableExtraction:
        self.calls.append(kwargs)
        return DARTTableExtraction(
            title="재무상태표",
            unit="백만원",
            headers=["과목", "당기"],
            rows=[{"과목": "자산총계", "당기": 1200}],
        )


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


def test_extract_with_slm_uses_injected_client_and_schema() -> None:
    fake = _FakeClient()
    result = extract_with_slm(
        "| 과목 | 당기 |\n| 자산총계 | 1,200 |",
        schema=DARTTableExtraction,
        client=fake,
    )
    assert isinstance(result, BaseModel)
    assert result.title == "재무상태표"
    call = fake.chat.completions.calls[0]
    assert call["response_model"] is DARTTableExtraction
    assert call["temperature"] == 0.0
    content = call["messages"][0]["content"]  # type: ignore[index]
    assert "자산총계" in content
