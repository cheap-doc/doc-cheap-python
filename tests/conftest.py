from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from doc_cheap import Client

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Answers every request with a fixed response and keeps the requests."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.response: httpx.Response = httpx.Response(200, json={})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response

    def answer(self, status: int = 200, body: Any = None, **kwargs: Any) -> None:
        if body is None:
            body = {}
        self.response = httpx.Response(status, json=body, **kwargs)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def client(recorder: Recorder) -> Iterator[Client]:
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    with Client("sk_test_key", base_url="https://api.test/", http_client=http) as c:
        yield c
    http.close()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOC_CHEAP_API_KEY", raising=False)
    monkeypatch.delenv("DOC_CHEAP_API_BASE", raising=False)
