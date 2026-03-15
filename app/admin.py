"""Admin routes for non-technical contributor data entry.

Provides a browser-based form at /admin for adding new trivia pages
without editing spreadsheets or running CLI tools directly.

Set the ADMIN_PASSWORD environment variable to protect the endpoint.
If unset, the form is unprotected (suitable for local / dev use only).
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ingest.py lives at the project root; importable when uvicorn runs from there.
import ingest as _ingest

from .domain.models import Page

logger = logging.getLogger(__name__)

BOOKS_DIR = os.getenv("BOOKS_DIR", "books")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PreviewRequest(BaseModel):
    url: str
    book_id: str
    page_id: str
    password: str = ""


class AddPageRequest(BaseModel):
    url: str
    book_id: str
    page_id: str
    title: str = ""
    description: str = ""
    password: str = ""


# ---------------------------------------------------------------------------
# HTML — single-page admin form
# ---------------------------------------------------------------------------

_ADMIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Barbooks — Add Trivia Page</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 700px; margin: 40px auto;
           padding: 0 20px; color: #222; }
    h1 { font-size: 1.5rem; }
    label { display: block; margin-top: 14px; font-weight: 600; font-size: .9rem; }
    input, select { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box;
                    border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; }
    .row { display: flex; gap: 12px; }
    .row > * { flex: 1; }
    button { margin-top: 16px; padding: 10px 24px; font-size: 1rem; cursor: pointer;
             border: none; border-radius: 4px; }
    #btn-preview { background: #0066cc; color: #fff; }
    #btn-save    { background: #28a745; color: #fff; display: none; }
    #status { margin-top: 16px; padding: 12px; border-radius: 4px; display: none; }
    .ok  { background: #d4edda; border: 1px solid #28a745; }
    .err { background: #f8d7da; border: 1px solid #dc3545; }
    pre  { background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto;
           font-size: .85rem; white-space: pre-wrap; }
    #preview-box { display: none; margin-top: 20px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px;
            font-size: .85rem; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f0f0f0; }
  </style>
</head>
<body>
  <h1>Barbooks — Add Trivia Page</h1>
  <p>Fill in the fields below, click <strong>Preview</strong> to validate the source,
     then <strong>Save</strong> to write it to the spreadsheet.</p>

  <div class="row">
    <div>
      <label for="book_id">Book ID</label>
      <input id="book_id" placeholder="e.g. nfl" value="nfl">
    </div>
    <div>
      <label for="page_id">Page #</label>
      <input id="page_id" placeholder="e.g. 10" type="number" min="1">
    </div>
  </div>

  <label for="url">Source URL (Answer Key)</label>
  <input id="url" type="url" placeholder="https://www.espn.com/nfl/history/leaders/...">

  <label for="password">Admin Password
    <span style="font-weight:400">(leave blank if not set)</span></label>
  <input id="password" type="password" placeholder="">

  <br>
  <button id="btn-preview" onclick="doPreview()">Preview</button>
  <button id="btn-save"    onclick="doSave()">Save to Spreadsheet</button>

  <div id="status"></div>

  <div id="preview-box">
    <h2>Preview</h2>
    <table id="meta-table"></table>
    <h3>Items (first 10)</h3>
    <table id="items-table"></table>
  </div>

  <script>
    let _lastPreview = null;

    function showStatus(msg, ok) {
      const el = document.getElementById('status');
      el.textContent = msg;
      el.className = ok ? 'ok' : 'err';
      el.style.display = 'block';
    }

    function val(id) { return document.getElementById(id).value.trim(); }

    async function doPreview() {
      document.getElementById('preview-box').style.display = 'none';
      document.getElementById('btn-save').style.display = 'none';
      _lastPreview = null;
      showStatus('Fetching source URL — this may take a few seconds…', true);

      const payload = {
        url: val('url'), book_id: val('book_id'),
        page_id: val('page_id'), password: val('password')
      };

      try {
        const res = await fetch('/api/v1/admin/preview', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
          showStatus('Error: ' + (data.detail || res.statusText), false);
          return;
        }
        _lastPreview = data;
        renderPreview(data);
        showStatus('Preview loaded. Review the data below, then click Save.', true);
        document.getElementById('btn-save').style.display = 'inline-block';
      } catch (e) {
        showStatus('Network error: ' + e.message, false);
      }
    }

    function renderPreview(p) {
      const mt = document.getElementById('meta-table');
      mt.innerHTML = '<tr><th>Field</th><th>Value</th></tr>' + [
        ['Page ID',      p.page_id],
        ['Title',        p.title],
        ['Description',  p.description],
        ['URL',          p.url],
        ['Type',         p.type],
        ['Clue style',   p.clue_style],
        ['Item count',   p.item_count],
        ['Stat label',   p.stat_label],
      ].map(([k,v]) => `<tr><td>${k}</td><td>${v||'—'}</td></tr>`).join('');

      const it = document.getElementById('items-table');
      const items = (p.items || []).slice(0, 10);
      if (items.length === 0) {
        it.innerHTML = '<tr><td>(no items parsed)</td></tr>';
      } else {
        const hdr = '<tr><th>#</th><th>Key</th><th>Name</th><th>Stat</th></tr>';
        it.innerHTML = hdr + items.map(i => '<tr>'
          + `<td>${i.rank??''}</td><td>${i.key}</td>`
          + `<td>${i.name}</td>`
          + `<td>${i.stat_value} ${i.stat_label}</td></tr>`
        ).join('');
      }
      document.getElementById('preview-box').style.display = 'block';
    }

    async function doSave() {
      if (!_lastPreview) { showStatus('Run Preview first.', false); return; }
      showStatus('Saving…', true);

      const payload = {
        url: val('url'), book_id: val('book_id'),
        page_id: val('page_id'), password: val('password')
      };

      try {
        const res = await fetch('/api/v1/admin/add-page', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
          showStatus('Error: ' + (data.detail || res.statusText), false);
          return;
        }
        showStatus('✓ Page saved to spreadsheet: ' + data.message, true);
        document.getElementById('btn-save').style.display = 'none';
      } catch (e) {
        showStatus('Network error: ' + e.message, false);
      }
    }
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_password(pw: str) -> None:
    expected = ADMIN_PASSWORD
    if expected and pw != expected:
        raise HTTPException(status_code=401, detail="Invalid admin password")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
async def admin_form() -> str:
    """Serve the admin data-entry form."""
    return _ADMIN_HTML


@router.post("/api/v1/admin/preview")
async def preview_page(req: PreviewRequest) -> dict:
    """Fetch and parse the source URL; return a Page preview (no write)."""
    _check_password(req.password)

    try:
        html = await _ingest._fetch_html(req.url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")

    page: Page = _ingest.parse_page_data(req.url, req.book_id, req.page_id, html)
    return page.model_dump()


@router.post("/api/v1/admin/add-page")
async def add_page(req: AddPageRequest) -> dict:
    """Fetch, parse, and write a new page row to the spreadsheet."""
    _check_password(req.password)

    try:
        html = await _ingest._fetch_html(req.url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")

    page: Page = _ingest.parse_page_data(req.url, req.book_id, req.page_id, html)

    # Allow caller to override auto-detected title/description
    if req.title:
        page = page.model_copy(update={"title": req.title})
    if req.description:
        page = page.model_copy(update={"description": req.description})

    xlsx_path = _ingest._find_xlsx(BOOKS_DIR, req.book_id)
    if xlsx_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No spreadsheet found for book '{req.book_id}' in {BOOKS_DIR}/",
        )

    try:
        _ingest._write_page_to_spreadsheet(page, xlsx_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to write page to spreadsheet")
        raise HTTPException(status_code=500, detail=str(exc))

    logger.info("Admin wrote page %s/%s from %s", req.book_id, req.page_id, req.url)
    return {
        "message": f"Page {req.page_id} written to {xlsx_path}",
        "book_id": req.book_id,
        "page_id": req.page_id,
        "title": page.title,
    }
