"""The shapes of the API's answers, as typed dictionaries.

The client returns the decoded JSON as it came, so every field the API adds
later is still there; these types describe the fields known today, for editors
and type checkers. Dates are ISO-8601 strings and country codes are ISO 3166-1
alpha-3.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Status = Literal[
    "recognized",
    "no_document_found",
    "unreadable",
    "unsupported_document",
    "rejected",
]
"""The outcome of one scan. Whether it was charged is ``meta["billed"]``."""

Confidence = Literal["low", "medium", "high"]
"""How strongly the recognition backs a value: a band rather than a number."""


class ScanTiming(TypedDict):
    upload_ms: int
    processing_ms: int
    total_ms: int


class ScanMeta(TypedDict):
    schema_version: str
    id: str
    status: Status
    billed: bool
    confidence: Confidence
    timing: ScanTiming | None
    created_at: str
    reference: str | None


class ScanDocument(TypedDict):
    kind: str
    country: str | None
    country_name: str | None
    issuing_state: str | None
    type_name: str | None
    type_confidence: Confidence
    number: str | None
    series: str | None
    issue_date: str | None
    expiry_date: str | None
    is_expired: bool | None
    days_remaining: int | None


class ScanHolder(TypedDict):
    given_names: str | None
    surname: str | None
    full_name: str | None
    birth_date: str | None
    sex: str | None
    nationality: str | None


class ScanField(TypedDict):
    id: str
    name: str
    label: str
    category: str
    value: str | None
    language: str | None
    confidence: Confidence


class ScanMRZ(TypedDict):
    status: Literal["passed", "failed", "absent"]
    reason: str | None
    lines: list[str]
    text: str | None


class ScanImages(TypedDict):
    """Image areas cut from the document, each a ``data:`` URL or ``None``."""

    document_crop: str | None
    rear: str | None
    main_photo: str | None
    signature: str | None
    watermark_face: str | None
    barcode: str | None
    chip: str | None


class ScanQuality(TypedDict):
    overall: str


class ScanCheck(TypedDict):
    name: str
    label: str
    result: str
    detail: str | None


class ScanAuthenticity(TypedDict):
    overall: str
    checks: list[ScanCheck]


class Scan(TypedDict):
    """The full result of one recognition."""

    meta: ScanMeta
    document: ScanDocument | None
    holder: ScanHolder | None
    fields: list[ScanField]
    mrz: ScanMRZ
    images: ScanImages
    quality: ScanQuality
    authenticity: ScanAuthenticity


class ScanSummary(TypedDict):
    id: str
    status: Status
    billed: bool
    duration_ms: int
    reference: str | None
    created_at: str


class ScanList(TypedDict):
    """One page of stored scans, newest first."""

    scans: list[ScanSummary]
    next_cursor: str | None


class ScanDeletion(TypedDict):
    id: str
    deleted: bool


class UsagePeriod(TypedDict):
    start: str
    end: str


class UsageScans(TypedDict):
    total: int
    billed: int
    by_status: dict[str, int]


class FreeAllowance(TypedDict):
    monthly_credits: int
    remaining_credits: int
    resets_at: str | None


class CreditsByKind(TypedDict):
    free: int
    paid: int


class Usage(TypedDict):
    """The account's balance and what was spent in the current period."""

    balance_credits: int | None
    period: UsagePeriod
    scans: UsageScans
    credits_spent: int
    free_allowance: FreeAllowance | None
    paid_balance_credits: int | None
    credits_spent_by_kind: CreditsByKind
