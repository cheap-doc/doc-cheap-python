"""The synchronous client for the doc.cheap API."""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Union, cast
from urllib.parse import quote

import httpx

from ._errors import APIConnectionError, DocCheapError, InvalidArgumentError, error_from_response
from ._types import Scan, ScanDeletion, ScanList, Usage
from ._version import __version__

DEFAULT_BASE_URL = "https://api.doc.cheap"
"""The API the client talks to unless told otherwise."""

SANDBOX_KEY = "sk_sandbox_public"
"""A public key that works without an account and never draws credits."""

MAX_IMAGE_BYTES = 25 * 1024 * 1024
"""The largest image the API accepts, measured before base64 encoding."""

API_KEY_ENV = "DOC_CHEAP_API_KEY"
BASE_URL_ENV = "DOC_CHEAP_API_BASE"

_MAX_REFERENCE_LENGTH = 128
_MAX_IDEMPOTENCY_KEY_LENGTH = 255
_MAX_CURSOR_LENGTH = 256
_MAX_RETAIN_HOURS = 8760
_MAX_LIST_LIMIT = 100
_COUNTRY_CODE = re.compile(r"[A-Z]{3}")
_DATA_URL_PREFIX = re.compile(r"^data:[^,]*;base64,", re.IGNORECASE)

StrPath = Union[str, "os.PathLike[str]"]


def _default_user_agent() -> str:
    return f"doc-cheap-python/{__version__} (+https://gitlab.com/doccheap/doc-cheap-python)"


def _decoded_length(encoded: str) -> int:
    # The size the API will see after decoding, without decoding a string
    # that may be tens of megabytes only to measure it.
    return len(encoded) * 3 // 4


class Client:
    """Calls the doc.cheap API.

    Args:
        api_key: The API key. When omitted it is read from the
            ``DOC_CHEAP_API_KEY`` environment variable. A live key starts with
            ``sk_live_``; :data:`SANDBOX_KEY` works without an account.
        base_url: The API address. When omitted it is read from
            ``DOC_CHEAP_API_BASE``, else :data:`DEFAULT_BASE_URL`.
        timeout: Seconds to wait for an answer. Ignored when ``http_client``
            is given.
        http_client: An ``httpx.Client`` to send the requests through, for a
            proxy, custom transport or shared connection pool. The caller
            keeps ownership of it: :meth:`close` leaves it open.
        user_agent: A product token put in front of the client's own
            ``User-Agent``, so an application's requests can be told apart.

    The client is safe to share between threads, like the ``httpx.Client``
    under it. Use it as a context manager, or call :meth:`close`, to release
    its connections.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
        user_agent: str | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
        if not key:
            raise DocCheapError(
                f"no API key: pass api_key or set {API_KEY_ENV} "
                f"(the public sandbox key is {SANDBOX_KEY!r})"
            )
        self._api_key = key
        base = base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
        self._base_url = base.rstrip("/")
        agent = _default_user_agent()
        if user_agent and user_agent.strip():
            agent = f"{user_agent.strip()} {agent}"
        self._user_agent = agent
        self._owns_http_client = http_client is None
        self._http = http_client if http_client is not None else httpx.Client(timeout=timeout)

    @property
    def base_url(self) -> str:
        """The API address requests are sent to."""
        return self._base_url

    def close(self) -> None:
        """Releases the connections of the HTTP client this client created."""
        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def recognize(
        self,
        *,
        image: bytes | None = None,
        image_base64: str | None = None,
        path: StrPath | None = None,
        reference: str | None = None,
        idempotency_key: str | None = None,
        expect_country: str | None = None,
        return_portrait: bool | None = None,
        retain_hours: int | None = None,
    ) -> Scan:
        """Sends one image and returns what was read from it.

        Give exactly one of ``image`` (raw JPEG or PNG bytes), ``image_base64``
        (the same bytes as standard base64, a ``data:`` URL prefix allowed) or
        ``path`` (a file to read).

        An image that holds no readable document is not an error: the scan
        comes back with a status other than ``"recognized"`` and
        ``scan["meta"]["billed"]`` set to ``False``.

        Args:
            reference: A label of up to 128 characters, stored with the scan
                and returned with it.
            idempotency_key: When set, a retried request returns the first
                answer instead of reading the document twice. Up to 255
                characters.
            expect_country: The issuing country you expect, as three
                upper-case letters (ISO 3166-1 alpha-3).
            return_portrait: Whether to return the holder's portrait image.
            retain_hours: How long the API keeps the scan, from 0 to 8760.
        """
        body: dict[str, Any] = {"image": self._image(image, image_base64, path)}
        if reference:
            if len(reference) > _MAX_REFERENCE_LENGTH:
                raise InvalidArgumentError(
                    f"reference is {len(reference)} characters, "
                    f"the limit is {_MAX_REFERENCE_LENGTH}"
                )
            body["reference"] = reference
        options: dict[str, Any] = {}
        if expect_country:
            if not _COUNTRY_CODE.fullmatch(expect_country):
                raise InvalidArgumentError(
                    f"expect_country {expect_country!r} is not three upper-case letters"
                )
            options["expect_country"] = expect_country
        if return_portrait is not None:
            options["return_portrait"] = bool(return_portrait)
        if retain_hours is not None:
            if isinstance(retain_hours, bool) or not 0 <= retain_hours <= _MAX_RETAIN_HOURS:
                raise InvalidArgumentError(
                    f"retain_hours {retain_hours!r} is outside 0..{_MAX_RETAIN_HOURS}"
                )
            options["retain_hours"] = retain_hours
        if options:
            body["options"] = options
        headers: dict[str, str] = {}
        if idempotency_key:
            if len(idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
                raise InvalidArgumentError(
                    f"idempotency_key is {len(idempotency_key)} characters, "
                    f"the limit is {_MAX_IDEMPOTENCY_KEY_LENGTH}"
                )
            headers["Idempotency-Key"] = idempotency_key
        return cast(Scan, self._request("POST", "/v1/scans", json=body, headers=headers))

    def get_scan(self, scan_id: str) -> Scan:
        """Returns a stored scan by its id."""
        return cast(Scan, self._request("GET", self._scan_path(scan_id)))

    def list_scans(self, *, limit: int | None = None, cursor: str | None = None) -> ScanList:
        """Returns one page of stored scans, newest first.

        Args:
            limit: The page size, from 1 to 100. The API's default when omitted.
            cursor: The ``next_cursor`` of the previous page. It is ``None`` on
                the last page.
        """
        params: dict[str, str] = {}
        if limit is not None:
            if isinstance(limit, bool) or not 1 <= limit <= _MAX_LIST_LIMIT:
                raise InvalidArgumentError(f"limit {limit!r} is outside 1..{_MAX_LIST_LIMIT}")
            params["limit"] = str(limit)
        if cursor:
            if len(cursor) > _MAX_CURSOR_LENGTH:
                raise InvalidArgumentError(
                    f"cursor is {len(cursor)} characters, the limit is {_MAX_CURSOR_LENGTH}"
                )
            params["cursor"] = cursor
        return cast(ScanList, self._request("GET", "/v1/scans", params=params))

    def delete_scan(self, scan_id: str) -> ScanDeletion:
        """Deletes a stored scan by its id."""
        return cast(ScanDeletion, self._request("DELETE", self._scan_path(scan_id)))

    def usage(self) -> Usage:
        """Returns the account's balance and what was spent in the current period."""
        return cast(Usage, self._request("GET", "/v1/usage"))

    @staticmethod
    def _scan_path(scan_id: str) -> str:
        if not scan_id:
            raise InvalidArgumentError("a scan id is required")
        return "/v1/scans/" + quote(scan_id, safe="")

    @staticmethod
    def _image(image: bytes | None, image_base64: str | None, path: StrPath | None) -> str:
        given = sum(source is not None for source in (image, image_base64, path))
        if given != 1:
            raise InvalidArgumentError("give exactly one of image, image_base64 or path")
        if path is not None:
            try:
                image = Path(path).read_bytes()
            except OSError as exc:
                raise InvalidArgumentError(f"cannot read the image file: {exc}") from exc
        if image is not None:
            if not image:
                raise InvalidArgumentError("the image is empty")
            if len(image) > MAX_IMAGE_BYTES:
                raise InvalidArgumentError(
                    f"image is {len(image)} bytes, the limit is {MAX_IMAGE_BYTES}"
                )
            return base64.b64encode(image).decode("ascii")
        encoded = _DATA_URL_PREFIX.sub("", cast(str, image_base64).strip(), count=1)
        if not encoded:
            raise InvalidArgumentError("the image is empty")
        if _decoded_length(encoded) > MAX_IMAGE_BYTES + 2:
            raise InvalidArgumentError(f"image is larger than {MAX_IMAGE_BYTES} bytes")
        return encoded

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": self._user_agent,
        }
        if headers:
            request_headers.update(headers)
        try:
            response = self._http.request(
                method,
                self._base_url + path,
                json=json,
                params=params or None,
                headers=request_headers,
            )
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"{method} {path}: {exc}") from exc
        if not response.is_success:
            raise error_from_response(response)
        try:
            return response.json()
        except ValueError as exc:
            raise DocCheapError(f"{method} {path}: the answer is not JSON") from exc
