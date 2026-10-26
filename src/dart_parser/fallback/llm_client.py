"""OpenAI-compatible SLM client (Ollama / vLLM / OpenAI) via Instructor."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from dart_parser.config.settings import Settings, get_settings
from dart_parser.fallback.schemas import DARTTableExtraction


def get_instructor_client(settings: Settings | None = None) -> Any:
    """Build an Instructor-wrapped OpenAI client. Network is used only on call."""
    import instructor
    from openai import OpenAI

    cfg = settings or get_settings()
    return instructor.from_openai(
        OpenAI(
            base_url=cfg.llm_base_url,
            api_key=cfg.llm_api_key,
            timeout=cfg.llm_timeout,
        ),
        mode=instructor.Mode.JSON,
    )


def extract_with_slm(
    table_markdown: str,
    schema: type[BaseModel] | None = None,
    *,
    settings: Settings | None = None,
    extra_instructions: str = "",
    client: Any | None = None,
) -> BaseModel:
    """Structured extraction of one table. Pass ``client`` in tests to avoid I/O."""
    cfg = settings or get_settings()
    model_cls = schema or DARTTableExtraction
    llm = client if client is not None else get_instructor_client(cfg)
    extra = f"\n{extra_instructions.strip()}\n" if extra_instructions.strip() else ""
    prompt = (
        "다음은 DART 공시 문서의 파싱되지 않은 비정형 표 데이터입니다.\n"
        "정확한 수치와 항목을 식별하여 구조화된 JSON으로 변환하세요.\n"
        f"{extra}\n"
        "[Table Data]\n"
        f"{table_markdown}\n"
    )
    return llm.chat.completions.create(
        model=cfg.llm_model,
        response_model=model_cls,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
