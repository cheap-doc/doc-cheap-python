"""The exceptions the client raises.

Every failure is a :class:`DocCheapError`. An answer from the API with an
error status is an :class:`APIError`, narrowed to a subclass by the API's own
error code, so a caller can catch the case it handles (``NotFoundError``,
``RateLimitError``) and let the rest propagate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import httpx

# The error body is small JSON; anything larger is not one, and parsing it
# whole would only hold memory for a message nobody can read.
_MAX_ERROR_BODY_BYTES = 64 * 1024


class DocCheapError(Exception):
    """Base class of every exception this package raises."""


class InvalidArgumentError(DocCheapError, ValueError):
    """An argument the API would refuse, caught before any request is sent."""


class APIConnectionError(DocCheapError):
    """The request did not get an answer: a network failure or a timeout."""


class APIError(DocCheapError):
    """The API answered with a status outside 2xx.

    Attributes:
        status_code: The HTTP status, for example 401 or 404.
        code: The API's machine-readable error code, for example
            ``"unauthorized"``. When the body carries none it is ``"http_"``
            followed by the status.
        message: The API's human-readable explanation.
        docs_url: The documentation page for ``code``, when the API gave one.
        request_id: Identifies the request in the API's logs; quote it when
            asking for help.
        event_id: Identifies a recorded unexpected failure, or ``None``.
        retry_after: Seconds to wait before retrying, from the ``Retry-After``
            header of a 429 or 503 answer, or ``None`` when it is absent.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        docs_url: str | None = None,
        request_id: str | None = None,
        event_id: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.docs_url = docs_url
        self.request_id = request_id
        self.event_id = event_id
        self.retry_after = retry_after


class InvalidRequestError(APIError):
    """The request was malformed, failed validation, or carried a bad image."""


class AuthenticationError(APIError):
    """The API key is missing, unknown or revoked."""


class PermissionDeniedError(APIError):
    """The key is valid but may not do this, for example before registration."""


class InsufficientCreditsError(APIError):
    """The account has no credits left for a billable scan."""


class NotFoundError(APIError):
    """The scan does not exist, was deleted, or was never stored."""


class ConflictError(APIError):
    """The request clashes with an earlier one, such as a reused idempotency key."""


class RateLimitError(APIError):
    """Too many requests; wait ``retry_after`` seconds before the next one."""


class ServiceUnavailableError(APIError):
    """The API cannot serve the request right now; retrying later may succeed."""


class InternalServerError(APIError):
    """The API failed unexpectedly; quote ``request_id`` and ``event_id``."""


_BY_CODE: Mapping[str, type[APIError]] = {
    "invalid_request": InvalidRequestError,
    "validation_failed": InvalidRequestError,
    "payload_too_large": InvalidRequestError,
    "unsupported_media_type": InvalidRequestError,
    "unauthorized": AuthenticationError,
    "registration_required": PermissionDeniedError,
    "impersonation_read_only": PermissionDeniedError,
    "insufficient_credits": InsufficientCreditsError,
    "not_found": NotFoundError,
    "idempotency_conflict": ConflictError,
    "idempotency_in_progress": ConflictError,
    "idempotency_replay_unavailable": ConflictError,
    "document_repeated": RateLimitError,
    "topup_in_progress": ConflictError,
    "rate_limited": RateLimitError,
    "engine_unavailable": ServiceUnavailableError,
    "service_unavailable": ServiceUnavailableError,
    "maintenance": ServiceUnavailableError,
    "payment_driver_unavailable": ServiceUnavailableError,
    "rate_unavailable": ServiceUnavailableError,
    "internal_error": InternalServerError,
}

# Used only when the body names no code this package knows, so an error from a
# proxy in front of the API still lands in the class its status implies.
_BY_STATUS: Mapping[int, type[APIError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    413: InvalidRequestError,
    415: InvalidRequestError,
    422: InvalidRequestError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("retry-after", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return None


def error_from_response(response: httpx.Response) -> APIError:
    """Builds the exception for an answer with an error status."""
    body: object = None
    content = response.content[:_MAX_ERROR_BODY_BYTES]
    try:
        body = json.loads(content)
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    fields: dict[str, object] = error if isinstance(error, dict) else {}

    status = response.status_code
    code = _text(fields.get("code")) or f"http_{status}"
    message = _text(fields.get("message")) or response.reason_phrase or f"HTTP {status}"
    cls = _BY_CODE.get(code) or _BY_STATUS.get(status)
    if cls is None:
        cls = InternalServerError if status >= 500 else APIError
    return cls(
        status_code=status,
        code=code,
        message=message,
        docs_url=_text(fields.get("docs_url")),
        request_id=_text(fields.get("request_id")),
        event_id=_text(fields.get("event_id")),
        retry_after=_retry_after(response),
    )
