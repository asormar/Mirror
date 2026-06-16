"""Unit tests for SEC EDGAR's pure functions (no network, no cache)."""

from __future__ import annotations

from app.pipeline.clients.sec_edgar import SecEdgarClient

SAMPLE_SUBMISSIONS = {
    "cik": "0001067983",
    "filings": {
        "recent": {
            "form": ["13F-HR", "10-K", "13F-HR/A", "13F-HR"],
            "accessionNumber": [
                "0000950123-23-001234",
                "0000950123-23-009999",
                "0000950123-24-005555",
                "0000950123-24-006666",
            ],
            "primaryDocument": [
                "form13fhr.htm",
                "form10k.htm",
                "form13fhr-a.htm",
                "form13fhr2.htm",
            ],
            "filingDate": ["2023-02-14", "2023-02-22", "2024-02-15", "2024-05-15"],
            "reportDate": ["2022-12-31", "2022-12-31", "2023-12-31", "2024-03-31"],
        }
    },
}


def test_find_new_13f_filters_only_13f_forms() -> None:
    found = SecEdgarClient.find_new_13f_filings(
        SAMPLE_SUBMISSIONS, known_accession_numbers=set()
    )
    forms = [f["form"] for f in found]
    assert forms == ["13F-HR", "13F-HR/A", "13F-HR"]


def test_find_new_13f_excludes_known_accessions() -> None:
    found = SecEdgarClient.find_new_13f_filings(
        SAMPLE_SUBMISSIONS,
        known_accession_numbers={"0000950123-23-001234", "0000950123-24-005555"},
    )
    accessions = [f["accession_number"] for f in found]
    assert accessions == ["0000950123-24-006666"]


def test_find_new_13f_handles_empty_recent() -> None:
    found = SecEdgarClient.find_new_13f_filings(
        {"filings": {"recent": {}}},
        known_accession_numbers=set(),
    )
    assert found == []


def test_find_new_13f_handles_missing_filings_key() -> None:
    found = SecEdgarClient.find_new_13f_filings({}, known_accession_numbers=set())
    assert found == []


def test_find_new_13f_propagates_filing_metadata() -> None:
    found = SecEdgarClient.find_new_13f_filings(
        SAMPLE_SUBMISSIONS, known_accession_numbers=set()
    )
    first = found[0]
    assert first["accession_number"] == "0000950123-23-001234"
    assert first["primary_document"] == "form13fhr.htm"
    assert first["filing_date"] == "2023-02-14"
    assert first["report_date"] == "2022-12-31"
