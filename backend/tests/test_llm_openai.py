"""OpenAI adapter against a mock HTTP transport: no network, no keys."""

from __future__ import annotations

import json

import httpx2
import pytest

from app.llm.base import ChatMessage
from app.llm.errors import PermanentLLMError, TransientLLMError
from app.llm.openai_provider import OpenAIProvider

MSGS = [ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hi")]


def provider(handler) -> OpenAIProvider:  # type: ignore[no-untyped-def]
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return OpenAIProvider(api_key="test-key", base_url="http://mock/v1", http_client=client)


def chat_json(text: str = "hello", **usage: object) -> dict[str, object]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-test",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14, **usage},
    }


async def test_complete_maps_text_usage_and_cached_tokens() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(req.content))
        seen["auth"] = req.headers["authorization"]
        return httpx2.Response(200, json=chat_json(prompt_tokens_details={"cached_tokens": 8}))

    out = await provider(handler).complete(model="gpt-test", messages=MSGS)
    assert out.text == "hello"
    assert (out.input_tokens, out.output_tokens, out.cached_tokens) == (11, 3, 8)
    assert seen["model"] == "gpt-test"
    assert seen["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert seen["auth"] == "Bearer test-key"
    assert "response_format" not in seen


async def test_complete_requests_json_schema() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(req.content))
        return httpx2.Response(200, json=chat_json('{"a": 1}'))

    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    await provider(handler).complete(model="m", messages=MSGS, response_schema=schema)
    fmt = seen["response_format"]
    assert isinstance(fmt, dict) and fmt["type"] == "json_schema"
    assert fmt["json_schema"]["schema"] == schema


async def test_embed_orders_by_index_and_sends_dimensions_for_v3() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(req.content))
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    out = await provider(handler).embed(
        model="text-embedding-3-small", texts=["a", "b"], dimensions=3
    )
    assert out.vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert out.input_tokens == 4
    assert seen["dimensions"] == 3


async def test_embed_omits_dimensions_for_other_models_and_checks_shape() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(req.content))
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "other",
                "data": [{"object": "embedding", "index": 0, "embedding": [1.0, 2.0]}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    p = provider(handler)
    with pytest.raises(PermanentLLMError, match="shape"):
        await p.embed(model="other", texts=["a"], dimensions=3)
    assert "dimensions" not in seen


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, TransientLLMError),
        (500, TransientLLMError),
        (503, TransientLLMError),
        (400, PermanentLLMError),
        (401, PermanentLLMError),
        (404, PermanentLLMError),
    ],
)
async def test_http_errors_are_classified(status: int, expected: type[Exception]) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, json={"error": {"message": "secret prompt echo", "type": "x"}}
        )

    with pytest.raises(expected) as info:
        await provider(handler).complete(model="m", messages=MSGS)
    assert "secret prompt echo" not in str(info.value)


async def test_connection_error_is_transient() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down")

    with pytest.raises(TransientLLMError):
        await provider(handler).complete(model="m", messages=MSGS)


async def test_stream_yields_deltas() -> None:
    def sse(text: str) -> str:
        chunk = {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        }
        return f"data: {json.dumps(chunk)}\n\n"

    body = sse("Hel") + sse("lo") + "data: [DONE]\n\n"

    def handler(req: httpx2.Request) -> httpx2.Response:
        assert json.loads(req.content)["stream"] is True
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    pieces = [p async for p in provider(handler).stream(model="m", messages=MSGS)]
    assert "".join(pieces) == "Hello"
