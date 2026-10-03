# doc-cheap

[![PyPI](https://img.shields.io/pypi/v/doc-cheap.svg)](https://pypi.org/project/doc-cheap/)

The Python client for [doc.cheap](https://doc.cheap): it sends a photo or scan
of a passport, national ID card or driving licence to the doc.cheap API and
returns the printed fields – name, date of birth, document number, expiry, the
machine-readable zone – as typed dictionaries.

One recognised document costs one credit, $0.01. Registering gives 100 free
documents every month. An unreadable image, an empty frame or an unsupported
document type costs nothing, and every answer says whether it was billed.

The package needs Python 3.10 or later and depends only on
[httpx](https://www.python-httpx.org/).

## Installation

```sh
pip install doc-cheap
```

## Quick start

```python
from doc_cheap import SANDBOX_KEY, Client

with Client(SANDBOX_KEY) as client:
    scan = client.recognize(path="passport.jpg")

print("status:", scan["meta"]["status"], "billed:", scan["meta"]["billed"])
if scan["holder"] and scan["holder"]["full_name"]:
    print("holder:", scan["holder"]["full_name"])
if scan["document"] and scan["document"]["expiry_date"]:
    print("expires:", scan["document"]["expiry_date"])
```

## API keys

- **Live key** – `sk_live_…`, created in the
  [doc.cheap cabinet](https://doc.cheap/docs/concepts/api-keys-and-sessions).
- **Sandbox key** – `sk_sandbox_public` (the `doc_cheap.SANDBOX_KEY` constant)
  works without an account. It gives 10 free recognised documents per address
  in all, and at most 10 requests per address an hour, whatever their answer.

`Client()` without a key reads it from the `DOC_CHEAP_API_KEY` environment
variable, which keeps a live key out of source code. The key is sent as a
Bearer token.

## Methods

| Method | Request | What it does |
| --- | --- | --- |
| `recognize` | `POST /v1/scans` | Reads one JPEG or PNG image, from a file (`path`), raw bytes (`image`) or base64 (`image_base64`), with an optional `reference` label, `idempotency_key`, `expect_country`, `return_portrait` and `retain_hours`. |
| `get_scan` | `GET /v1/scans/{id}` | Returns a stored result. |
| `list_scans` | `GET /v1/scans` | Returns one page of stored results; pass `next_cursor` back as `cursor` for the next page. |
| `delete_scan` | `DELETE /v1/scans/{id}` | Deletes a stored result. |
| `usage` | `GET /v1/usage` | Returns this month's free credits, the paid credits, the credits spent and the scan counters. |

An image that holds no readable document is not an error: the scan comes back
with a status such as `unreadable` or `no_document_found` and `billed` set to
`False`.

**Stored results.** A result is stored only when the scan was made with a live
key under a non-zero retention window, and only until that window ends. Under
the sandbox key nothing is stored, so `get_scan` and `delete_scan` raise
`NotFoundError`. None of `get_scan`, `delete_scan` or `usage` charges a credit.

## Errors

Every exception the package raises is a `doc_cheap.DocCheapError`. When the API
answers with an error status, it is an `APIError` carrying the HTTP status, the
API's error code and its message, narrowed to a subclass you can catch:

```python
from doc_cheap import APIError, NotFoundError, RateLimitError

try:
    scan = client.get_scan(scan_id)
except NotFoundError:
    scan = None
except RateLimitError as err:
    print("try again in", err.retry_after, "seconds")
except APIError as err:
    print(err.status_code, err.code, err.message, err.request_id)
```

| Exception | When |
| --- | --- |
| `InvalidRequestError` | The request was malformed or failed validation (400, 413, 415, 422). |
| `AuthenticationError` | The key is missing, unknown or revoked (401). |
| `PermissionDeniedError` | The key may not do this (403). |
| `InsufficientCreditsError` | The account has no credits left (402). |
| `NotFoundError` | No such scan (404). |
| `ConflictError` | An idempotency key is reused or still in progress (409). |
| `RateLimitError` | Too many requests; `retry_after` says how long to wait (429). |
| `ServiceUnavailableError` | The service is briefly unavailable (503). |
| `InternalServerError` | Any other server error (5xx). |
| `APIConnectionError` | No answer at all: a network failure or a timeout. |

An argument the API would refuse anyway – no image, an image over 25 MiB, a
reference over 128 characters – raises `InvalidArgumentError` (also a
`ValueError`) before any request is sent.

## Options

```python
import httpx
from doc_cheap import Client

client = Client(
    timeout=30.0,
    user_agent="my-app/1.0",
)

# Or bring your own httpx.Client for a proxy or a shared connection pool;
# the doc.cheap client leaves it open when it closes.
client = Client(http_client=httpx.Client(proxy="http://proxy.internal:3128"))
```

`base_url` (or the `DOC_CHEAP_API_BASE` environment variable) points the client
at another address, for example a test server.

## Resources

- [doc.cheap documentation](https://doc.cheap/docs)
- [Your first recognition](https://doc.cheap/docs/start/first-recognition)
- [From the sandbox to a live key](https://doc.cheap/docs/start/from-sandbox-to-live)
- [API reference](https://doc.cheap/docs/reference)
- [Handling errors](https://doc.cheap/docs/guides/handle-errors)

## License

[MIT](LICENSE)
