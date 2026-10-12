"""Local browser UI for MarkItDown with a MinerU OCR fallback for scanned PDFs."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from markitdown import MarkItDown
from pydantic import BaseModel
from pypdf import PdfReader

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
STATIC_DIR = Path(__file__).parent / "static"

MINERU_BIN = Path(os.environ.get("MINERU_BIN", Path.home() / "mineru-env" / "bin" / "mineru"))
MINERU_TIMEOUT_S = 3600
# A PDF with less text than this per page is likely a scan, so it goes to OCR.
MIN_TEXT_CHARS_PER_PAGE = 100

app = FastAPI(title="markitdown workbench")

# Each worker thread gets its own converter instance (they hold loaded models).
_local = threading.local()


def get_converter() -> MarkItDown:
    converter = getattr(_local, "converter", None)
    if converter is None:
        converter = MarkItDown(enable_plugins=False)
        _local.converter = converter
    return converter


def run_conversion(fn, *args) -> str:
    try:
        result = fn(*args)
    except Exception as exc:
        raise HTTPException(422, f"{type(exc).__name__}: {exc}") from exc
    return getattr(result, "markdown", "") or ""


def pdf_page_count(path: Path) -> int:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def mineru_ocr(path: Path) -> str | None:
    if not MINERU_BIN.exists():
        return None
    out_md = path.with_suffix(".md")
    try:
        proc = subprocess.run(
            [
                str(MINERU_BIN), "parse", str(path),
                "-p", "all", "--tier", "standard",
                "-o", str(out_md), "--force", "--wait", str(MINERU_TIMEOUT_S),
            ],
            capture_output=True,
            text=True,
            timeout=MINERU_TIMEOUT_S,
        )
    except Exception:
        return None
    if proc.returncode == 0 and out_md.exists():
        return out_md.read_text(encoding="utf-8", errors="replace")
    return None


@app.post("/api/convert")
def convert(file: UploadFile = File(...)) -> dict:
    """Convert an uploaded file; scanned PDFs fall back to MinerU OCR."""
    original_name = Path(file.filename or "file").name
    suffix = Path(original_name).suffix

    with tempfile.TemporaryDirectory(prefix="markitdown-") as tmp_dir:
        tmp_path = Path(tmp_dir) / f"input{suffix}"
        size = 0
        with tmp_path.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File is larger than the 100 MB limit.")
                out.write(chunk)

        if size == 0:
            raise HTTPException(400, "The file is empty.")

        markdown = run_conversion(get_converter().convert_local, str(tmp_path))
        engine = "markitdown"

        if suffix.lower() == ".pdf":
            pages = pdf_page_count(tmp_path)
            if pages and len(markdown.strip()) / pages < MIN_TEXT_CHARS_PER_PAGE:
                ocr_text = mineru_ocr(tmp_path)
                if ocr_text and ocr_text.strip():
                    markdown = ocr_text
                    engine = "mineru-ocr"

    return {"name": original_name, "markdown": markdown, "engine": engine}


class UrlIn(BaseModel):
    url: str


@app.post("/api/convert-url")
def convert_url(body: UrlIn) -> dict:
    """Convert a web page or YouTube URL to Markdown."""
    url = body.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(400, "Enter a valid http:// or https:// URL.")

    markdown = run_conversion(get_converter().convert_url, url)
    name = Path(parsed.path).name or parsed.netloc
    return {"name": name, "markdown": markdown}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
