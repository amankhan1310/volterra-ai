from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.acquisition.conftest import Server, payload, remote, sha
from volterra_ml.acquisition.fetch import (
    USER_AGENT,
    AcquisitionError,
    Fetcher,
    _total_from_content_range,
)
from volterra_ml.acquisition.manifest import is_read_only


def test_download_records_provenance_and_publishes_read_only(server: Server, tmp_path: Path):
    data = payload(1)
    server.state.files["a.zip"] = data
    fixed = datetime(2026, 11, 15, 9, 30, 5, tzinfo=timezone.utc)
    fetcher = Fetcher(retries=0, progress=None, now=lambda: fixed)
    record = fetcher.download(remote("a.zip", server.url("a.zip")), tmp_path)
    target = tmp_path / "a.zip"
    assert target.read_bytes() == data
    assert record.bytes == len(data) and record.sha256 == sha(data)
    assert record.retrieved_at == "2026-11-15T09:30:05Z"
    assert record.retrieval_method == "http"
    assert record.final_url == server.url("a.zip")
    assert record.etag and record.last_modified == "Mon, 10 Aug 2015 14:37:18 GMT"
    assert is_read_only(target)
    assert not (tmp_path / "a.zip.part").exists()


def test_generic_user_agent_and_no_personal_headers(server: Server, tmp_path: Path, fetcher):
    seen: list[dict[str, str]] = []
    import urllib.request

    def opener(request: urllib.request.Request, timeout: float):
        seen.append(dict(request.header_items()))
        return urllib.request.urlopen(request, timeout=timeout)

    server.state.files["a.zip"] = payload(2, 1000)
    Fetcher(opener=opener, retries=0, progress=None).download(
        remote("a.zip", server.url("a.zip")), tmp_path
    )
    assert seen == [{"User-agent": USER_AGENT}]
    assert USER_AGENT.startswith("volterra-ml-acquisition/") and "@" not in USER_AGENT


def test_redirect_is_followed_and_final_url_recorded(server: Server, tmp_path: Path, fetcher):
    server.state.files["b.mat"] = payload(3)
    record = fetcher.download(remote("b.mat", server.url("redirect/b.mat")), tmp_path)
    assert record.final_url == server.url("b.mat")
    assert record.source_url == server.url("redirect/b.mat")


def test_interrupted_download_resumes_with_range(server: Server, tmp_path: Path, fetcher):
    data = payload(4)
    server.state.files["c.zip"] = data
    server.state.faults["c.zip"] = ["truncate"]
    record = fetcher.download(remote("c.zip", server.url("c.zip"), data, pin=True), tmp_path)
    assert record.sha256 == sha(data)
    ranges = [r for p, r in server.state.requests if p == "c.zip"]
    assert ranges[0] is None and ranges[1] == f"bytes={len(data) // 2}-"


def test_server_ignoring_range_restarts_from_zero(server: Server, tmp_path: Path, fetcher):
    data = payload(5)
    server.state.files["d.zip"] = data
    (tmp_path / "d.zip.part").write_bytes(data[:1000])
    server.state.faults["d.zip"] = ["ignore-range"]
    record = fetcher.download(remote("d.zip", server.url("d.zip")), tmp_path)
    assert (tmp_path / "d.zip").read_bytes() == data and record.bytes == len(data)


def test_transient_server_errors_are_retried(server: Server, tmp_path: Path, fetcher):
    server.state.files["e.zip"] = payload(6)
    server.state.faults["e.zip"] = ["500", "500"]
    fetcher.download(remote("e.zip", server.url("e.zip")), tmp_path)
    assert len(server.state.requests) == 3


def test_retries_are_bounded(server: Server, tmp_path: Path):
    server.state.files["f.zip"] = payload(7)
    server.state.faults["f.zip"] = ["500"] * 5
    fetcher = Fetcher(retries=2, backoff_s=0.0, sleep=lambda _s: None, progress=io.StringIO())
    with pytest.raises(AcquisitionError, match="gave up after 3 attempts"):
        fetcher.download(remote("f.zip", server.url("f.zip")), tmp_path)
    assert not (tmp_path / "f.zip").exists()


def test_missing_file_is_a_hard_error(server: Server, tmp_path: Path, fetcher):
    with pytest.raises(AcquisitionError, match="HTTP 404"):
        fetcher.download(remote("nope.zip", server.url("nope.zip")), tmp_path)
    assert len(server.state.requests) == 1


def test_unreachable_host_is_retried_then_fails(tmp_path: Path, fetcher):
    with pytest.raises(AcquisitionError, match="gave up"):
        fetcher.download(remote("x.zip", "http://127.0.0.1:9/x.zip"), tmp_path)


def test_checksum_pin_mismatch_discards_the_file(server: Server, tmp_path: Path, fetcher):
    pinned = payload(8)
    server.state.files["g.zip"] = payload(9)  # the source changed
    with pytest.raises(AcquisitionError, match="SHA-256 differs from the registry pin"):
        fetcher.download(remote("g.zip", server.url("g.zip"), pinned, pin=True), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_size_pin_mismatch_discards_the_file(server: Server, tmp_path: Path, fetcher):
    server.state.files["h.zip"] = payload(10, 5000)
    pinned = payload(10, 4000)
    with pytest.raises(AcquisitionError, match="differs from the pinned 4000"):
        fetcher.download(remote("h.zip", server.url("h.zip"), pinned, pin=True), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_complete_partial_file_and_416_counts_as_done(server: Server, tmp_path: Path, fetcher):
    data = payload(11)
    server.state.files["i.zip"] = data
    (tmp_path / "i.zip.part").write_bytes(data)
    server.state.faults["i.zip"] = ["416"]
    record = fetcher.download(remote("i.zip", server.url("i.zip"), data, pin=True), tmp_path)
    assert record.sha256 == sha(data)


def test_stale_partial_file_and_416_restarts(server: Server, tmp_path: Path, fetcher):
    data = payload(12)
    server.state.files["j.zip"] = data
    (tmp_path / "j.zip.part").write_bytes(b"x" * (len(data) + 10))
    server.state.faults["j.zip"] = ["416"]
    record = fetcher.download(remote("j.zip", server.url("j.zip")), tmp_path)
    assert record.sha256 == sha(data)


def test_copy_local_applies_the_same_checks(tmp_path: Path, fetcher):
    data = payload(13)
    source = tmp_path / "manual"
    source.mkdir()
    (source / "k.zip").write_bytes(data)
    dest = tmp_path / "raw"
    record = fetcher.copy_local(
        remote("k.zip", "https://x.invalid/k.zip", data, pin=True), source, dest
    )
    assert record.retrieval_method == "local_copy" and record.final_url is None
    assert (dest / "k.zip").read_bytes() == data and is_read_only(dest / "k.zip")
    assert (source / "k.zip").exists()  # the hand-downloaded original is left alone
    with pytest.raises(AcquisitionError, match="not found"):
        fetcher.copy_local(remote("missing.zip", "https://x.invalid/m"), source, dest)
    (source / "bad.zip").write_bytes(b"tampered")
    with pytest.raises(AcquisitionError, match="SHA-256"):
        fetcher.copy_local(
            remote("bad.zip", "https://x.invalid/b", payload(14, 8), pin=True), source, dest
        )
    assert not (dest / "bad.zip").exists()


def test_content_range_total():
    assert _total_from_content_range("bytes 10-99/100") == 100
    assert _total_from_content_range("bytes 10-99/*") is None
