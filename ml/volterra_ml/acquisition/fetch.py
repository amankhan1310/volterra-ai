"""Download (or copy) one raw file, verify it, and only then publish it read-only.

Bytes land in ``<name>.part`` first. A download that breaks off resumes with an HTTP ``Range``
request; if the server ignores the range, the download restarts from zero. Only after the size
matches the server's announced length and every registry pin (size, SHA-256) does the file get
its final name, atomically, and lose its write permission. A file that fails verification is
deleted and never becomes part of the raw dataset.

Standard library only. Requests carry a generic User-Agent and nothing that identifies the user.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPResponse, IncompleteRead
from pathlib import Path
from typing import IO, Protocol

from volterra_ml.acquisition.manifest import PART_SUFFIX, FileRecord, make_read_only, sha256_file
from volterra_ml.acquisition.sources import RemoteFile

USER_AGENT = "volterra-ml-acquisition/0.1 (battery research data download; python-urllib)"
CHUNK = 1024 * 1024
TIMEOUT_S = 60.0


class AcquisitionError(Exception):
    """A file could not be acquired or failed verification."""


class _RetryableError(Exception):
    """A transient failure worth another attempt (the partial file is kept for resuming)."""


class Opener(Protocol):
    def __call__(self, request: urllib.request.Request, timeout: float) -> HTTPResponse: ...


def _default_opener(request: urllib.request.Request, timeout: float) -> HTTPResponse:
    response: HTTPResponse = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
    return response


@dataclass
class Fetcher:
    opener: Opener = _default_opener
    retries: int = 5
    backoff_s: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    progress: IO[str] | None = sys.stderr
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def download(self, remote: RemoteFile, directory: Path) -> FileRecord:
        directory.mkdir(parents=True, exist_ok=True)
        part = directory / (remote.name + PART_SUFFIX)
        final_url: str | None = None
        etag: str | None = None
        last_modified: str | None = None
        for attempt in range(self.retries + 1):
            try:
                final_url, etag, last_modified = self._attempt(remote, part)
                break
            except _RetryableError as exc:
                if attempt == self.retries:
                    raise AcquisitionError(
                        f"{remote.name}: gave up after {attempt + 1} attempts: {exc}"
                    ) from exc
                self._say(f"{remote.name}: {exc}; retrying ({attempt + 1}/{self.retries})")
                self.sleep(self.backoff_s * (attempt + 1))
        return self._publish(remote, part, "http", final_url, etag, last_modified)

    def copy_local(self, remote: RemoteFile, source_dir: Path, directory: Path) -> FileRecord:
        """Acquire a file someone downloaded by hand (same checks as a download)."""
        source = source_dir / remote.name
        if not source.is_file():
            raise AcquisitionError(f"{remote.name}: not found in the local source folder")
        directory.mkdir(parents=True, exist_ok=True)
        part = directory / (remote.name + PART_SUFFIX)
        shutil.copyfile(source, part)
        return self._publish(remote, part, "local_copy", None, None, None)

    # -- internals -------------------------------------------------------------------------

    def _attempt(self, remote: RemoteFile, part: Path) -> tuple[str, str | None, str | None]:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(remote.url, headers=headers)
        try:
            response = self.opener(request, TIMEOUT_S)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset and remote.bytes == offset:
                return remote.url, None, None  # the partial file is already complete
            if exc.code in (408, 429) or exc.code >= 500:
                raise _RetryableError(f"HTTP {exc.code}") from exc
            if exc.code == 416:
                part.unlink()  # our partial file does not fit the server's copy: start over
                raise _RetryableError("HTTP 416, restarting from zero") from exc
            raise AcquisitionError(f"{remote.name}: HTTP {exc.code} from {remote.url}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise _RetryableError(str(exc)) from exc

        with response:
            status = response.status
            if offset and status == 206:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {offset}-"):
                    part.unlink()
                    raise _RetryableError(f"unexpected Content-Range {content_range!r}")
                mode = "ab"
                total = _total_from_content_range(content_range)
            elif status == 200:
                if offset:
                    self._say(f"{remote.name}: server ignored the range; restarting")
                mode, offset = "wb", 0
                length = response.headers.get("Content-Length")
                total = int(length) if length is not None else None
            else:
                raise AcquisitionError(f"{remote.name}: unexpected HTTP status {status}")
            try:
                self._stream(remote.name, response, part, mode, offset, total)
            except (IncompleteRead, TimeoutError, ConnectionError, OSError) as exc:
                raise _RetryableError(f"transfer interrupted: {exc!r}") from exc
            size = part.stat().st_size
            if total is not None and size != total:
                raise _RetryableError(f"received {size} of {total} bytes")
            return (
                response.geturl(),
                response.headers.get("ETag"),
                response.headers.get("Last-Modified"),
            )

    def _stream(
        self,
        name: str,
        response: HTTPResponse,
        part: Path,
        mode: str,
        offset: int,
        total: int | None,
    ) -> None:
        done = offset
        next_report = 0.0
        with part.open(mode) as out:
            while chunk := response.read(CHUNK):
                out.write(chunk)
                done += len(chunk)
                if total and done / total >= next_report:
                    self._say(f"{name}: {done / 1e6:,.1f} / {total / 1e6:,.1f} MB")
                    next_report += 0.1
            out.flush()
            os.fsync(out.fileno())

    def _publish(
        self,
        remote: RemoteFile,
        part: Path,
        method: str,
        final_url: str | None,
        etag: str | None,
        last_modified: str | None,
    ) -> FileRecord:
        size = part.stat().st_size
        digest = sha256_file(part)
        failure = None
        if remote.bytes is not None and size != remote.bytes:
            failure = f"size {size} differs from the pinned {remote.bytes}"
        elif remote.sha256 is not None and digest != remote.sha256:
            failure = "SHA-256 differs from the registry pin (the source changed or is corrupt)"
        if failure:
            part.unlink()
            raise AcquisitionError(f"{remote.name}: {failure}; the file was discarded")
        target = part.with_name(remote.name)
        os.replace(part, target)
        make_read_only(target)
        retrieved_at = self.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        self._say(f"{remote.name}: {size:,} bytes, sha256 {digest}")
        return FileRecord(
            name=remote.name,
            source_url=remote.url,
            final_url=final_url,
            retrieved_at=retrieved_at,
            retrieval_method="http" if method == "http" else "local_copy",
            bytes=size,
            sha256=digest,
            etag=etag,
            last_modified=last_modified,
        )

    def _say(self, message: str) -> None:
        if self.progress is not None:
            print(message, file=self.progress, flush=True)


def _total_from_content_range(value: str) -> int | None:
    # "bytes 100-199/200" -> 200; "bytes 100-199/*" -> None
    _, _, total = value.rpartition("/")
    return int(total) if total.isdigit() else None
