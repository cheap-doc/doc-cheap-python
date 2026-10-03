from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest

import doc_cheap
from doc_cheap import (
    DEFAULT_BASE_URL,
    MAX_IMAGE_BYTES,
    SANDBOX_KEY,
    APIConnectionError,
    Client,
    DocCheapError,
    InvalidArgumentError,
)

from .conftest import Recorder

PNG = b"\x89PNG\r\n\x1a\nfake"
SCAN = {"meta": {"id": "scan_1", "status": "unsupported_document", "billed": False}}


def test_version_is_exported() -> None:
    assert doc_cheap.__version__ == "0.1.0"
    assert "Client" in doc_cheap.__all__


def test_key_from_argument_wins_over_environment(
    monkeypatch: pytest.MonkeyPatch, recorder: Recorder
) -> None:
    monkeypatch.setenv("DOC_CHEAP_API_KEY", "sk_env")
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    Client("sk_arg", http_client=http).usage()
    assert recorder.last.headers["authorization"] == "Bearer sk_arg"


def test_key_and_base_url_from_environment(
    monkeypatch: pytest.MonkeyPatch, recorder: Recorder
) -> None:
    monkeypatch.setenv("DOC_CHEAP_API_KEY", "sk_env")
    monkeypatch.setenv("DOC_CHEAP_API_BASE", "https://env.test/")
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    client = Client(http_client=http)
    assert client.base_url == "https://env.test"
    client.usage()
    assert recorder.last.headers["authorization"] == "Bearer sk_env"
    assert str(recorder.last.url) == "https://env.test/v1/usage"


def test_default_base_url() -> None:
    with Client(SANDBOX_KEY) as client:
        assert client.base_url == DEFAULT_BASE_URL


def test_missing_key_names_the_sandbox_key() -> None:
    with pytest.raises(DocCheapError, match=SANDBOX_KEY):
        Client()
    with pytest.raises(DocCheapError):
        Client("")


def test_close_leaves_a_borrowed_http_client_open(recorder: Recorder) -> None:
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    Client("k", http_client=http).close()
    assert not http.is_closed


def test_close_closes_its_own_http_client() -> None:
    client = Client("k")
    client.close()
    assert client._http.is_closed


def test_headers(client: Client, recorder: Recorder) -> None:
    client.usage()
    headers = recorder.last.headers
    assert headers["accept"] == "application/json"
    assert headers["authorization"] == "Bearer sk_test_key"
    assert headers["user-agent"].startswith("doc-cheap-python/0.1.0 ")
    assert "content-type" not in headers


def test_user_agent_product_token(recorder: Recorder) -> None:
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    Client("k", http_client=http, user_agent="  my-app/1.0 ").usage()
    assert recorder.last.headers["user-agent"].startswith("my-app/1.0 doc-cheap-python/0.1.0")
    Client("k", http_client=http, user_agent="   ").usage()
    assert recorder.last.headers["user-agent"].startswith("doc-cheap-python/")


def test_recognize_bytes_with_every_option(client: Client, recorder: Recorder) -> None:
    recorder.answer(201, SCAN)
    scan = client.recognize(
        image=PNG,
        reference="order-7",
        idempotency_key="idem-1",
        expect_country="UTO",
        return_portrait=False,
        retain_hours=0,
    )
    assert scan["meta"]["status"] == "unsupported_document"
    request = recorder.last
    assert request.method == "POST"
    assert str(request.url) == "https://api.test/v1/scans"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["idempotency-key"] == "idem-1"
    assert recorder.last_json() == {
        "image": base64.b64encode(PNG).decode(),
        "reference": "order-7",
        "options": {"expect_country": "UTO", "return_portrait": False, "retain_hours": 0},
    }


def test_recognize_minimal_body(client: Client, recorder: Recorder) -> None:
    recorder.answer(201, SCAN)
    client.recognize(image=PNG, reference="", idempotency_key="", expect_country="")
    assert recorder.last_json() == {"image": base64.b64encode(PNG).decode()}
    assert "idempotency-key" not in recorder.last.headers


def test_recognize_from_path(client: Client, recorder: Recorder, tmp_path: Path) -> None:
    file = tmp_path / "doc.png"
    file.write_bytes(PNG)
    client.recognize(path=file)
    client.recognize(path=str(file))
    assert recorder.last_json()["image"] == base64.b64encode(PNG).decode()


def test_recognize_base64_strips_a_data_url(client: Client, recorder: Recorder) -> None:
    encoded = base64.b64encode(PNG).decode()
    client.recognize(image_base64=f" data:image/png;base64,{encoded} ")
    assert recorder.last_json()["image"] == encoded
    client.recognize(image_base64=encoded)
    assert recorder.last_json()["image"] == encoded


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"image": PNG, "image_base64": "AAAA"},
        {"image": PNG, "path": "x.png"},
    ],
)
def test_recognize_needs_exactly_one_source(client: Client, kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidArgumentError, match="exactly one"):
        client.recognize(**kwargs)  # type: ignore[arg-type]


def test_recognize_refuses_bad_images(client: Client, recorder: Recorder, tmp_path: Path) -> None:
    with pytest.raises(InvalidArgumentError, match="empty"):
        client.recognize(image=b"")
    with pytest.raises(InvalidArgumentError, match="empty"):
        client.recognize(image_base64="data:image/png;base64,")
    with pytest.raises(InvalidArgumentError, match="limit"):
        client.recognize(image=b"\0" * (MAX_IMAGE_BYTES + 1))
    with pytest.raises(InvalidArgumentError, match="larger"):
        client.recognize(image_base64="A" * ((MAX_IMAGE_BYTES + 3) * 4 // 3 + 4))
    with pytest.raises(InvalidArgumentError, match="cannot read"):
        client.recognize(path=tmp_path / "missing.png")
    assert recorder.requests == []


def test_recognize_accepts_an_image_at_the_limit(client: Client) -> None:
    client.recognize(image=b"\0" * MAX_IMAGE_BYTES)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"reference": "x" * 129}, "reference"),
        ({"idempotency_key": "x" * 256}, "idempotency_key"),
        ({"expect_country": "uto"}, "expect_country"),
        ({"expect_country": "UTOO"}, "expect_country"),
        ({"retain_hours": -1}, "retain_hours"),
        ({"retain_hours": 8761}, "retain_hours"),
        ({"retain_hours": True}, "retain_hours"),
    ],
)
def test_recognize_refuses_bad_arguments(
    client: Client, recorder: Recorder, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(InvalidArgumentError, match=message):
        client.recognize(image=PNG, **kwargs)  # type: ignore[arg-type]
    assert recorder.requests == []


def test_recognize_accepts_the_limits(client: Client, recorder: Recorder) -> None:
    client.recognize(image=PNG, reference="é" * 128, idempotency_key="k" * 255, retain_hours=8760)
    assert recorder.last_json()["options"] == {"retain_hours": 8760}


def test_get_scan_escapes_the_id(client: Client, recorder: Recorder) -> None:
    recorder.answer(200, SCAN)
    assert client.get_scan("a/b c")["meta"]["id"] == "scan_1"
    assert recorder.last.method == "GET"
    assert recorder.last.url.raw_path == b"/v1/scans/a%2Fb%20c"


def test_delete_scan(client: Client, recorder: Recorder) -> None:
    recorder.answer(200, {"id": "scan_1", "deleted": True})
    assert client.delete_scan("scan_1") == {"id": "scan_1", "deleted": True}
    assert recorder.last.method == "DELETE"
    assert str(recorder.last.url) == "https://api.test/v1/scans/scan_1"


@pytest.mark.parametrize("method", ["get_scan", "delete_scan"])
def test_scan_id_is_required(client: Client, recorder: Recorder, method: str) -> None:
    with pytest.raises(InvalidArgumentError, match="scan id"):
        getattr(client, method)("")
    assert recorder.requests == []


def test_list_scans(client: Client, recorder: Recorder) -> None:
    recorder.answer(200, {"scans": [], "next_cursor": None})
    assert client.list_scans() == {"scans": [], "next_cursor": None}
    assert str(recorder.last.url) == "https://api.test/v1/scans"
    client.list_scans(limit=100, cursor="c" * 256)
    assert recorder.last.url.params["limit"] == "100"
    assert recorder.last.url.params["cursor"] == "c" * 256
    client.list_scans(limit=1, cursor="")
    assert "cursor" not in recorder.last.url.params


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"limit": True}, "limit"),
        ({"cursor": "c" * 257}, "cursor"),
    ],
)
def test_list_scans_refuses_bad_arguments(
    client: Client, recorder: Recorder, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(InvalidArgumentError, match=message):
        client.list_scans(**kwargs)  # type: ignore[arg-type]
    assert recorder.requests == []


def test_usage(client: Client, recorder: Recorder) -> None:
    recorder.answer(200, {"credits_spent": 0})
    assert client.usage()["credits_spent"] == 0
    assert str(recorder.last.url) == "https://api.test/v1/usage"


def test_transport_failure_is_a_connection_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    http = httpx.Client(transport=httpx.MockTransport(fail))
    with pytest.raises(APIConnectionError, match="GET /v1/usage"):
        Client("k", http_client=http).usage()


def test_an_answer_that_is_not_json(recorder: Recorder) -> None:
    recorder.response = httpx.Response(200, text="<html>")
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    with pytest.raises(DocCheapError, match="not JSON"):
        Client("k", http_client=http).usage()
