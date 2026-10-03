from __future__ import annotations

import httpx
import pytest

from doc_cheap import (
    APIError,
    AuthenticationError,
    Client,
    ConflictError,
    InsufficientCreditsError,
    InternalServerError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
)
from doc_cheap._errors import error_from_response

from .conftest import Recorder


def _error(status: int, code: str | None = None, **extra: object) -> httpx.Response:
    body: dict[str, object] = {"message": "went wrong", **extra}
    if code is not None:
        body["code"] = code
    return httpx.Response(status, json={"error": body})


@pytest.mark.parametrize(
    ("status", "code", "cls"),
    [
        (400, "invalid_request", InvalidRequestError),
        (422, "validation_failed", InvalidRequestError),
        (413, "payload_too_large", InvalidRequestError),
        (415, "unsupported_media_type", InvalidRequestError),
        (401, "unauthorized", AuthenticationError),
        (403, "registration_required", PermissionDeniedError),
        (403, "impersonation_read_only", PermissionDeniedError),
        (402, "insufficient_credits", InsufficientCreditsError),
        (404, "not_found", NotFoundError),
        (409, "idempotency_conflict", ConflictError),
        (409, "idempotency_in_progress", ConflictError),
        (409, "idempotency_replay_unavailable", ConflictError),
        (409, "topup_in_progress", ConflictError),
        (429, "rate_limited", RateLimitError),
        (429, "document_repeated", RateLimitError),
        (503, "engine_unavailable", ServiceUnavailableError),
        (503, "service_unavailable", ServiceUnavailableError),
        (503, "maintenance", ServiceUnavailableError),
        (503, "payment_driver_unavailable", ServiceUnavailableError),
        (503, "rate_unavailable", ServiceUnavailableError),
        (500, "internal_error", InternalServerError),
    ],
)
def test_known_codes(status: int, code: str, cls: type[APIError]) -> None:
    err = error_from_response(_error(status, code))
    assert type(err) is cls
    assert err.code == code
    assert err.status_code == status


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, InvalidRequestError),
        (413, InvalidRequestError),
        (415, InvalidRequestError),
        (422, InvalidRequestError),
        (401, AuthenticationError),
        (402, InsufficientCreditsError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (429, RateLimitError),
        (503, ServiceUnavailableError),
        (502, InternalServerError),
        (418, APIError),
    ],
)
def test_unknown_code_falls_back_to_the_status(status: int, cls: type[APIError]) -> None:
    err = error_from_response(_error(status, "something_new"))
    assert type(err) is cls
    assert err.code == "something_new"


def test_every_field_is_carried() -> None:
    response = _error(
        429,
        "rate_limited",
        docs_url="https://doc.cheap/docs/errors#rate_limited",
        request_id="req_1",
        event_id="evt_1",
    )
    response.headers["Retry-After"] = "12"
    err = error_from_response(response)
    assert isinstance(err, RateLimitError)
    assert err.message == "went wrong"
    assert err.docs_url == "https://doc.cheap/docs/errors#rate_limited"
    assert err.request_id == "req_1"
    assert err.event_id == "evt_1"
    assert err.retry_after == 12
    assert str(err) == "429 rate_limited: went wrong"


@pytest.mark.parametrize("header", ["", "0", "-3", "soon", "Wed, 21 Oct 2026 07:28:00 GMT"])
def test_retry_after_keeps_only_positive_seconds(header: str) -> None:
    response = _error(503, "maintenance")
    response.headers["Retry-After"] = header
    assert error_from_response(response).retry_after is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, text="<html>bad gateway</html>"),
        httpx.Response(502, json=["not", "an", "object"]),
        httpx.Response(502, json={"error": "flat string"}),
        httpx.Response(502, json={"error": {"code": "", "message": 7}}),
        httpx.Response(502, content=b"\xff\xfe"),
    ],
)
def test_a_body_without_an_error_object(response: httpx.Response) -> None:
    err = error_from_response(response)
    assert type(err) is InternalServerError
    assert err.code == "http_502"
    assert err.message == "Bad Gateway"
    assert err.request_id is None


def test_message_falls_back_to_the_status_number() -> None:
    err = error_from_response(httpx.Response(599))
    assert err.message == "HTTP 599"
    assert type(err) is InternalServerError


def test_a_huge_body_is_not_parsed_whole() -> None:
    body = b'{"error": {"code": "not_found", "message": "' + b"x" * 70_000 + b'"}}'
    err = error_from_response(httpx.Response(404, content=body))
    assert type(err) is NotFoundError
    assert err.code == "http_404"


def test_the_client_raises_the_mapped_error(recorder: Recorder) -> None:
    recorder.response = _error(401, "unauthorized", request_id="req_9")
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    with pytest.raises(AuthenticationError) as caught:
        Client("bad", http_client=http).usage()
    assert caught.value.request_id == "req_9"
