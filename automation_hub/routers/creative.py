# Creative/PSD processing routes
# Uses automation_hub.core only (no app import to avoid circular deps).

from __future__ import annotations

import json
import os
import secrets
import shutil
import traceback
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

import pandas as pd
from fastapi import File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from automation_hub.core import auth, db
from automation_hub.services.font_manager import (
    MAX_FONT_UPLOAD_BYTES,
    list_fonts,
    resolve_font,
    store_font,
)

try:
    from automation_hub.core.redis_util import redis_available, rate_limit_check
except ImportError:

    def redis_available() -> bool:
        return False

    def rate_limit_check(key: str, limit: int, window_seconds: int):
        return (True, 0, None)


def _db():
    conn = db.db_connect(db.get_db_file())
    return conn


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _rate_limit_abort(
    request: Request, scope: str, identifier: str, limit: int, window_seconds: int = 60
) -> None:
    """If Redis is available and limit exceeded, raise HTTP 429."""
    if not redis_available():
        return
    key = f"{scope}:{identifier}"
    allowed, count, retry_after = rate_limit_check(key, limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after or 60)},
        )


def _check_upload_size(request: Request) -> None:
    """Raise 413 if request body exceeds admin-configured max upload size."""
    from automation_hub.core.settings import get_upload_limits

    max_bytes, _ = get_upload_limits()
    cl = request.headers.get("content-length")
    if cl and int(cl) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413, detail=f"File too large. Maximum size is {mb} MB."
        )


def _gallery_safe_username(username: str) -> str:
    """Safe filesystem segment from username (e.g. email)."""
    safe = "".join(
        c for c in username if c.isalnum() or c in ("-", "_", "@", ".")
    ).strip()
    return safe or "user"


def _gallery_create_placeholder_thumbnail(thumb_path: Path) -> None:
    """Create a 200x200 placeholder PNG for ZIP (e.g. gallery thumbnail)."""
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (200, 200), color=(240, 240, 245))
        d = ImageDraw.Draw(img)
        d.text((100, 90), "ZIP", fill=(100, 100, 120), anchor="mm")
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(thumb_path, "PNG")
    except Exception:
        pass


def _register_gallery_asset(
    username: str,
    source_path: Path,
    *,
    display_name: str,
    job_id: str,
    thumb_path: Optional[Path] = None,
) -> None:
    safe_user = _gallery_safe_username(username)
    user_gallery = GALLERY_DIR / safe_user
    user_gallery.mkdir(parents=True, exist_ok=True)

    if source_path.suffix.lower() == ".zip":
        target_path = user_gallery / source_path.name
    else:
        target_dir = user_gallery / job_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name
    if target_path.resolve() != source_path.resolve():
        shutil.copy2(source_path, target_path)

    rel_file = f"{safe_user}/{target_path.relative_to(user_gallery).as_posix()}"
    rel_thumb = None
    if thumb_path and thumb_path.exists():
        rel_thumb = f"{safe_user}/{thumb_path.relative_to(user_gallery).as_posix()}"

    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO gallery_files (username, file_path, thumbnail_path, display_name, file_size, created_at, job_id)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                username,
                rel_file,
                rel_thumb,
                display_name,
                target_path.stat().st_size if target_path.exists() else None,
                db.utc_now_iso(),
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _register_creative_job_assets(
    username: str,
    job_id: str,
    zip_path: Path,
    results: List[Dict[str, Any]],
) -> bool:
    safe_user = _gallery_safe_username(username)
    user_gallery = GALLERY_DIR / safe_user
    user_gallery.mkdir(parents=True, exist_ok=True)
    thumbs_dir = user_gallery / "thumbs"
    thumbs_dir.mkdir(exist_ok=True)
    thumb_path = thumbs_dir / f"{job_id}.png"
    _gallery_create_placeholder_thumbnail(thumb_path)
    _register_gallery_asset(
        username,
        zip_path,
        display_name=f"{job_id}.zip",
        job_id=job_id,
        thumb_path=thumb_path,
    )
    for result in results:
        if not result.get("success"):
            continue
        for generated_path in (result.get("files") or {}).values():
            asset_path = Path(generated_path)
            if asset_path.is_file():
                _register_gallery_asset(
                    username,
                    asset_path,
                    display_name=asset_path.name,
                    job_id=job_id,
                    thumb_path=thumb_path,
                )
    return True


# Directories (same as app.py)
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
GALLERY_DIR = Path("gallery")
TEMPLATES_PSD_DIR = Path("templates_psd")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
GALLERY_DIR.mkdir(exist_ok=True)
TEMPLATES_PSD_DIR.mkdir(exist_ok=True)


def _resolve_psd_path(psd_file_id: str, username: Optional[str]) -> Path:
    """Resolve PSD path: if it looks like a template path (no 'template_' prefix with random), check TEMPLATES_PSD_DIR."""
    p_upload = UPLOAD_DIR / psd_file_id
    if p_upload.is_file():
        return p_upload
    p_templates = TEMPLATES_PSD_DIR / psd_file_id
    if p_templates.is_file():
        return p_templates
    return UPLOAD_DIR / psd_file_id


def _absolute_url(request: Request, path: str) -> str:
    return f"{str(request.base_url).rstrip('/')}{path}"


def _photopea_cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "https://www.photopea.com",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }


def _public_asset_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }


def _parse_photopea_save_payload(body: bytes) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if len(body) < 2000:
        raise ValueError("Photopea payload is incomplete.")
    header_text = body[:2000].decode("utf-8", errors="ignore")
    header_end = header_text.rfind("}")
    if header_end == -1:
        raise ValueError("Photopea payload header is invalid.")
    payload = json.loads(header_text[: header_end + 1])
    versions = payload.get("versions") or []
    files: List[Dict[str, Any]] = []
    for version in versions:
        fmt = str(version.get("format") or "").split(":", 1)[0].lower()
        start = 2000 + int(version.get("start") or 0)
        size = int(version.get("size") or 0)
        if not fmt or size <= 0:
            continue
        files.append(
            {
                "format": fmt,
                "bytes": body[start : start + size],
            }
        )
    if not files:
        raise ValueError("No exported files were received from Photopea.")
    return payload, files


def _cleanup_expired_editor_sessions() -> None:
    conn = _db()
    try:
        conn.execute(
            "DELETE FROM creative_edit_sessions WHERE expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()


def _get_editor_session(token: str) -> Optional[Dict[str, Any]]:
    _cleanup_expired_editor_sessions()
    conn = _db()
    try:
        row = conn.execute(
            """
            SELECT token, username, source_path, display_name, created_at, expires_at,
                   last_saved_at, last_saved_formats_json
            FROM creative_edit_sessions
            WHERE token = ?
            """,
            (token,),
        ).fetchone()
        return db.row_to_dict(row)
    finally:
        conn.close()


def _run_process_core(
    psd_file_id: str,
    data_file_id: str,
    mapping: Dict[str, str],
    filename_fields_list: List[str],
    output_format: str,
    username: Optional[str],
    psd_processor,
    watermark_config: Optional[Dict[str, Any]] = None,
    font_path: Optional[str] = None,
    layer_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple:
    """Run PSD processing (sync). Returns (job_id, results, zip_path)."""
    psd_path = _resolve_psd_path(psd_file_id, username)
    data_path = UPLOAD_DIR / data_file_id
    if not psd_path.exists() or not data_path.exists():
        raise FileNotFoundError("File not found")
    if data_path.suffix == ".csv":
        df = pd.read_csv(data_path)
    else:
        df = pd.read_excel(data_path)
    job_id = f"job_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
    job_output_dir = OUTPUT_DIR / job_id
    job_output_dir.mkdir(exist_ok=True)
    results = []
    for idx, row in df.iterrows():
        try:
            filename = "_".join(str(row[field]) for field in filename_fields_list)
            filename = "".join(
                c for c in filename if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            output_paths = psd_processor.process_psd(
                str(psd_path),
                row,
                mapping,
                str(job_output_dir),
                filename,
                output_format,
                watermark_config=watermark_config,
                font_path=font_path,
                layer_overrides=layer_overrides,
            )
            results.append(
                {
                    "row": idx + 1,
                    "filename": filename,
                    "success": True,
                    "files": output_paths,
                }
            )
        except Exception as e:
            results.append({"row": idx + 1, "success": False, "error": str(e)})
        finally:
            if progress_callback:
                progress_callback(idx + 1, len(df))
    zip_path = OUTPUT_DIR / f"{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(job_output_dir):
            for file in files:
                file_path = Path(root) / file
                zipf.write(file_path, file_path.relative_to(job_output_dir))
    registration_ok = True
    if username:
        try:
            registration_ok = _register_creative_job_assets(
                username=username,
                job_id=job_id,
                zip_path=zip_path,
                results=results,
            )
        except Exception as exc:
            registration_ok = False
            print(f"[creative] Failed to register gallery assets for {job_id}: {exc}")
            traceback.print_exc()
    if registration_ok:
        shutil.rmtree(job_output_dir, ignore_errors=True)
    return (job_id, results, str(zip_path))


# Router
from fastapi import APIRouter

creative_router = APIRouter(prefix="/api", tags=["creative"])


@creative_router.get("/creative/fonts")
async def get_creative_fonts(request: Request):
    """List all readable application fonts."""
    auth.require_module(request, "creative_psd", auth.get_current_user)
    fonts = await run_in_threadpool(list_fonts)
    return JSONResponse({"success": True, "fonts": fonts})


@creative_router.post("/creative/fonts")
async def upload_creative_font(request: Request, file: UploadFile = File(...)):
    """Validate and store a font for Creative text rendering."""
    auth.require_module(request, "creative_psd", auth.get_current_user)
    user = auth.get_current_user(request)
    ident = user["username"] if user else _client_ip(request)
    _rate_limit_abort(request, "font-upload", ident, 15, 60)

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FONT_UPLOAD_BYTES + 1024 * 1024:
        raise HTTPException(status_code=413, detail="Font upload is too large.")

    content = await file.read(MAX_FONT_UPLOAD_BYTES + 1)
    try:
        font, created = await run_in_threadpool(
            store_font, file.filename or "font", content
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        {"success": True, "font": font, "created": created},
        status_code=201 if created else 200,
    )


@creative_router.post("/upload-psd")
async def upload_psd(request: Request, file: UploadFile = File(...)):
    """Upload PSD template file"""
    _check_upload_size(request)
    auth.require_module(request, "creative_psd", auth.get_current_user)
    user = auth.get_current_user(request)
    ident = user["username"] if user else _client_ip(request)
    _rate_limit_abort(request, "upload", ident, 30, 60)
    psd_processor = getattr(request.app.state, "psd_processor", None)
    if not psd_processor:
        raise HTTPException(status_code=500, detail="PSD processor not available")
    try:
        safe_filename = os.path.basename(file.filename.replace("\\", "/"))
        file_path = UPLOAD_DIR / f"template_{safe_filename}"
        with open(file_path, "wb") as buffer:
            # Wrap file writing in thread pool since copyfileobj can block
            await run_in_threadpool(shutil.copyfileobj, file.file, buffer)

        # Validate PSD file and extract layer info
        try:
            layer_info = await run_in_threadpool(
                psd_processor.get_layer_info, str(file_path)
            )
            return JSONResponse(
                {"success": True, "file_id": file_path.name, "layers": layer_info}
            )
        except Exception as e:
            return JSONResponse(
                {"success": False, "error": f"Invalid PSD file: {str(e)}"},
                status_code=400,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@creative_router.post("/upload-data")
async def upload_data(request: Request, file: UploadFile = File(...)):
    """Upload Excel/CSV data file"""
    _check_upload_size(request)
    auth.require_any_module(
        request,
        ["creative_psd", "messaging_send", "data_excel_to_sql"],
        auth.get_current_user,
    )
    user = auth.get_current_user(request)
    ident = user["username"] if user else _client_ip(request)
    _rate_limit_abort(request, "upload", ident, 30, 60)
    try:
        safe_filename = os.path.basename(file.filename.replace("\\", "/"))
        file_path = UPLOAD_DIR / f"data_{safe_filename}"
        with open(file_path, "wb") as buffer:
            await run_in_threadpool(shutil.copyfileobj, file.file, buffer)

        # Validate with pandas in threadpool
        def _read_data():
            if safe_filename.endswith(".csv"):
                df = pd.read_csv(file_path)
            elif safe_filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(file_path)
            else:
                raise ValueError("Unsupported file type")
            return df.columns.tolist(), len(df)

        # Read and return column names
        try:
            columns, row_count = await run_in_threadpool(_read_data)

            return JSONResponse(
                {
                    "success": True,
                    "file_id": file_path.name,
                    "columns": columns,
                    "row_count": row_count,
                }
            )
        except Exception as e:
            return JSONResponse(
                {"success": False, "error": f"Invalid data file: {str(e)}"},
                status_code=400,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@creative_router.get("/creative/templates")
async def list_psd_templates(request: Request, category: Optional[str] = Query(None)):
    """List PSD templates for the current user. Optional filter: category."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    auth.require_module(request, "creative_psd", auth.get_current_user)
    cat = (category or "").strip()
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT id, name, file_path, created_at, category FROM psd_templates WHERE username = ? ORDER BY created_at DESC",
            (user["username"],),
        ).fetchall()
    finally:
        conn.close()
    rows = [db.row_to_dict(r) for r in rows]
    if cat:
        rows = [r for r in rows if (r.get("category") or "") == cat]
    return JSONResponse(
        {
            "templates": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "file_path": r["file_path"],
                    "created_at": r["created_at"],
                    "category": (r["category"] if "category" in r.keys() else "") or "",
                }
                for r in rows
            ]
        }
    )


@creative_router.post("/creative/templates")
async def save_psd_template(request: Request, payload: Dict[str, Any]):
    """Save current PSD as a named template. Body: { name, file_id }."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    auth.require_module(request, "creative_psd", auth.get_current_user)
    name = (payload.get("name") or "").strip()
    file_id = (payload.get("file_id") or "").strip()
    category = (payload.get("category") or "").strip()
    if not name or not file_id:
        raise HTTPException(status_code=400, detail="name and file_id required")
    src = UPLOAD_DIR / file_id
    if not src.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    safe_user = _gallery_safe_username(user["username"])
    template_dir = TEMPLATES_PSD_DIR / safe_user
    template_dir.mkdir(parents=True, exist_ok=True)
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO psd_templates (username, name, file_path, created_at, category) VALUES (?,?,?,?,?)",
            (user["username"], name, "", now, category or None),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        tid = row["id"]
        conn.commit()
    finally:
        conn.close()
    ext = src.suffix or ".psd"
    dest_path = template_dir / f"template_{tid}{ext}"

    def copy_template():
        shutil.copy2(src, dest_path)

    await run_in_threadpool(copy_template)

    rel_path = f"{safe_user}/template_{tid}{ext}"
    conn = _db()
    try:
        conn.execute(
            "UPDATE psd_templates SET file_path = ?, category = ? WHERE id = ?",
            (rel_path, category or None, tid),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse(
        {
            "success": True,
            "id": tid,
            "name": name,
            "file_path": rel_path,
            "category": category or "",
        }
    )


@creative_router.post("/creative/read-layers")
async def read_creative_layers(request: Request, psd_file_id: str = Form(...)):
    """Read PSD layers for an uploaded file or saved template path."""
    user = auth.get_current_user(request)
    auth.require_module(request, "creative_psd", auth.get_current_user)
    psd_processor = getattr(request.app.state, "psd_processor", None)
    if not psd_processor:
        raise HTTPException(status_code=500, detail="PSD processor not available")
    psd_path = _resolve_psd_path(psd_file_id, user["username"] if user else None)
    if not psd_path.exists():
        raise HTTPException(status_code=404, detail="PSD file not found")
    try:
        layers = await run_in_threadpool(psd_processor.get_layer_info, str(psd_path))
        return JSONResponse(
            {"success": True, "layers": layers, "file_path": str(psd_path)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read PSD layers: {str(e)}"
        )


@creative_router.post("/creative/canvas-preview")
async def creative_canvas_preview(request: Request, psd_file_id: str = Form(...)):
    """Render the PSD canvas before layer overrides are applied."""
    user = auth.get_current_user(request)
    auth.require_module(request, "creative_psd", auth.get_current_user)
    psd_processor = getattr(request.app.state, "psd_processor", None)
    psd_path = _resolve_psd_path(psd_file_id, user["username"] if user else None)
    if not psd_processor or not psd_path.is_file():
        raise HTTPException(status_code=404, detail="PSD file not found")
    preview_id = f"canvas_{secrets.token_hex(8)}"
    preview_dir = OUTPUT_DIR / preview_id
    preview_path = preview_dir / "canvas.png"
    await run_in_threadpool(
        psd_processor.render_composite_preview,
        str(psd_path),
        str(preview_path),
    )
    return JSONResponse(
        {
            "success": True,
            "preview_url": f"/api/download-preview/{preview_id}/canvas.png",
        }
    )


@creative_router.post("/creative/editor-session")
async def create_creative_editor_session(request: Request, psd_file_id: str = Form(...)):
    """Create a tokenized Photopea session for editing a PSD and saving it back to Servexa."""
    user = auth.get_current_user(request)
    auth.require_module(request, "creative_psd", auth.get_current_user)
    psd_path = _resolve_psd_path(psd_file_id, user["username"] if user else None)
    if not psd_path.is_file():
        raise HTTPException(status_code=404, detail="PSD file not found")

    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=4)
    display_name = psd_path.name
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO creative_edit_sessions (
                token, username, source_path, display_name, created_at, expires_at,
                last_saved_at, last_saved_formats_json
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                token,
                (user or {}).get("username") or "anonymous",
                str(psd_path.resolve()),
                display_name,
                now.isoformat(),
                expires_at.isoformat(),
                None,
                "[]",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    source_url = _absolute_url(
        request,
        f"/api/creative/editor-source/{token}/{display_name}",
    )
    save_url = _absolute_url(request, f"/api/creative/editor-save/{token}")
    config = {
        "files": [source_url],
        "server": {
            "version": 1,
            "url": save_url,
            "formats": ["psd:true", "png"],
        },
        "environment": {
            "theme": 1,
        },
    }
    editor_url = (
        "https://www.photopea.com#"
        + quote(json.dumps(config, separators=(",", ":")), safe="")
    )
    return JSONResponse(
        {
            "success": True,
            "session_token": token,
            "editor_url": editor_url,
            "source_url": source_url,
            "save_url": save_url,
            "display_name": display_name,
            "expires_at": expires_at.isoformat(),
        }
    )


@creative_router.get("/creative/editor-session/{token}")
async def get_creative_editor_session_status(token: str, request: Request):
    """Return the latest save status for a PSD editor session."""
    user = auth.get_current_user(request)
    auth.require_module(request, "creative_psd", auth.get_current_user)
    session = _get_editor_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Editor session not found")
    if user and session["username"] != user["username"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return JSONResponse(
        {
            "success": True,
            "session": {
                "token": session["token"],
                "display_name": session["display_name"],
                "created_at": session["created_at"],
                "expires_at": session["expires_at"],
                "last_saved_at": session["last_saved_at"],
                "last_saved_formats": json.loads(
                    session.get("last_saved_formats_json") or "[]"
                ),
            },
        }
    )


@creative_router.options("/creative/editor-source/{token}/{filename:path}")
async def creative_editor_source_options(token: str, filename: str):
    return Response(status_code=204, headers=_public_asset_headers())


@creative_router.get("/creative/editor-source/{token}/{filename:path}")
async def creative_editor_source(token: str, filename: str):
    """Serve a PSD file to Photopea through a short-lived editor token."""
    session = _get_editor_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Editor session not found")
    source_path = Path(session["source_path"])
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="PSD source is missing")
    return FileResponse(
        path=str(source_path),
        media_type="application/octet-stream",
        filename=source_path.name,
        headers=_public_asset_headers(),
    )


@creative_router.options("/creative/editor-save/{token}")
async def creative_editor_save_options(token: str):
    return Response(status_code=204, headers=_photopea_cors_headers())


@creative_router.post("/creative/editor-save/{token}")
async def creative_editor_save(token: str, request: Request):
    """Receive Photopea save payload and write the PSD back to the original source path."""
    session = _get_editor_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Editor session not found")

    source_path = Path(session["source_path"])
    if not source_path.parent.exists():
        source_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload, exported_files = _parse_photopea_save_payload(await request.body())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved_formats: List[str] = []
    preview_png = None
    for exported in exported_files:
        fmt = exported["format"]
        file_bytes = exported["bytes"]
        if fmt == "psd":
            source_path.write_bytes(file_bytes)
            saved_formats.append("psd")
        elif fmt == "png":
            preview_png = source_path.with_suffix(".photopea-preview.png")
            preview_png.write_bytes(file_bytes)
            saved_formats.append("png")
        else:
            extra_path = source_path.with_suffix(f".photopea.{fmt}")
            extra_path.write_bytes(file_bytes)
            saved_formats.append(fmt)

    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            """
            UPDATE creative_edit_sessions
            SET last_saved_at = ?, last_saved_formats_json = ?
            WHERE token = ?
            """,
            (now, json.dumps(saved_formats), token),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(
        {
            "message": f"Saved {session['display_name']} back to Servexa.",
            "newSource": _absolute_url(
                request,
                f"/api/creative/editor-source/{token}/{source_path.name}",
            ),
            "saved_formats": saved_formats,
            "source": payload.get("source"),
            "preview_file": preview_png.name if preview_png else None,
        },
        headers=_photopea_cors_headers(),
    )


@creative_router.get("/creative/templates/{template_id}/layers")
async def get_template_layers(template_id: int, request: Request):
    """Get layer info for a saved template (to build mapping UI)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    auth.require_module(request, "creative_psd", auth.get_current_user)
    psd_processor = getattr(request.app.state, "psd_processor", None)
    if not psd_processor:
        raise HTTPException(status_code=500, detail="PSD processor not available")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, username, file_path FROM psd_templates WHERE id = ? AND username = ?",
            (template_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["file_path"]:
        raise HTTPException(status_code=404, detail="Template not found")
    path = TEMPLATES_PSD_DIR / row["file_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template file not found")
    try:
        layer_info = await run_in_threadpool(psd_processor.get_layer_info, str(path))
        return JSONResponse(
            {"success": True, "layers": layer_info, "file_path": row["file_path"]}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@creative_router.delete("/creative/templates/{template_id}")
async def delete_psd_template(template_id: int, request: Request):
    """Delete a PSD template (current user only)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    auth.require_module(request, "creative_psd", auth.get_current_user)
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, file_path FROM psd_templates WHERE id = ? AND username = ?",
            (template_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    full_path = TEMPLATES_PSD_DIR / row["file_path"]
    if full_path.is_file():
        try:
            full_path.unlink()
        except Exception:
            pass
    conn = _db()
    try:
        conn.execute(
            "DELETE FROM psd_templates WHERE id = ? AND username = ?",
            (template_id, user["username"]),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})


@creative_router.get("/creative/market/templates")
async def list_market_templates(
    request: Request, category: Optional[str] = Query(None)
):
    """List public marketplace templates."""
    auth.require_module(request, "creative_psd", auth.get_current_user)
    cat = (category or "").strip()
    conn = _db()
    try:
        if cat:
            rows = conn.execute(
                """
                SELECT id, slug, title, description, category, tags_json, price, currency, thumbnail_path, file_path
                FROM psd_market_templates
                WHERE is_active = 1 AND category = ?
                ORDER BY created_at DESC
                """,
                (cat,),
            ).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, slug, title, description, category, tags_json, price, currency, thumbnail_path, file_path
                FROM psd_market_templates
                WHERE is_active = 1
                ORDER BY created_at DESC
                """).fetchall()
    finally:
        conn.close()
    templates = [
        {
            "id": r["id"],
            "slug": r["slug"],
            "title": r["title"],
            "description": r["description"],
            "category": r["category"],
            "tags": json.loads(r["tags_json"] or "[]"),
            "price": r["price"] or 0,
            "currency": r["currency"] or "USD",
            "thumbnail_path": r["thumbnail_path"],
            "file_path": r["file_path"],
        }
        for r in rows
    ]
    return JSONResponse({"success": True, "templates": templates})


@creative_router.get("/creative/market/templates/{template_id}")
async def get_market_template(template_id: int, request: Request):
    """Get marketplace template details."""
    auth.require_module(request, "creative_psd", auth.get_current_user)
    conn = _db()
    try:
        row = conn.execute(
            """
            SELECT id, slug, title, description, category, tags_json, price, currency, thumbnail_path, file_path
            FROM psd_market_templates
            WHERE id = ? AND is_active = 1
            """,
            (template_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    template = {
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "tags": json.loads(row["tags_json"] or "[]"),
        "price": row["price"] or 0,
        "currency": row["currency"] or "USD",
        "thumbnail_path": row["thumbnail_path"],
        "file_path": row["file_path"],
    }
    # Get layer info if available
    psd_processor = getattr(request.app.state, "psd_processor", None)
    if psd_processor:
        try:
            path = TEMPLATES_PSD_DIR / row["file_path"]
            if path.exists():
                layer_info = psd_processor.get_layer_info(str(path))
                template["layers"] = layer_info
        except Exception:
            pass
    return JSONResponse({"success": True, "template": template})


@creative_router.post("/creative/market/templates/{template_id}/use")
async def use_market_template(template_id: int, request: Request):
    """Use a marketplace template (copy to user's templates)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    auth.require_module(request, "creative_psd", auth.get_current_user)
    conn = _db()
    try:
        row = conn.execute(
            "SELECT file_path FROM psd_market_templates WHERE id = ? AND is_active = 1",
            (template_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    src_path = TEMPLATES_PSD_DIR / row["file_path"]
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="Template file not found")
    # Copy to user's templates
    safe_user = _gallery_safe_username(user["username"])
    user_template_dir = TEMPLATES_PSD_DIR / safe_user
    user_template_dir.mkdir(parents=True, exist_ok=True)
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO psd_templates (username, name, file_path, created_at, category) VALUES (?,?,?,?,?)",
            (user["username"], f"Market Template #{template_id}", "", now, None),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        tid = row["id"]
        conn.commit()
    finally:
        conn.close()
    ext = src_path.suffix or ".psd"
    dest_path = user_template_dir / f"template_{tid}{ext}"

    def copy_template():
        shutil.copy2(src_path, dest_path)

    await run_in_threadpool(copy_template)

    rel_path = f"{safe_user}/template_{tid}{ext}"
    conn = _db()
    try:
        conn.execute(
            "UPDATE psd_templates SET file_path = ? WHERE id = ?",
            (rel_path, tid),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, "template_id": tid, "file_path": rel_path})


@creative_router.post("/preview")
async def preview_process(request: Request):
    """Process first row only and return preview file URL (sample output for layer mapping)."""
    auth.require_module(request, "creative_psd", auth.get_current_user)
    psd_processor = getattr(request.app.state, "psd_processor", None)
    if not psd_processor:
        raise HTTPException(status_code=500, detail="PSD processor not available")
    try:
        form = await request.form()
        psd_file_id = form.get("psd_file_id") or form.get("psdFileId")
        data_file_id = form.get("data_file_id") or form.get("dataFileId")
        layer_mapping = form.get("layer_mapping") or form.get("layerMapping") or "{}"
        filename_fields = (
            form.get("filename_fields") or form.get("filenameFields") or "[]"
        )
        output_format = form.get("output_format") or form.get("outputFormat") or "png"
        watermark_config_json = (
            form.get("watermark_config") or form.get("watermarkConfig") or "{}"
        )
        font_id = form.get("font_id") or form.get("fontId") or ""
        layer_overrides_json = form.get("layer_overrides") or "{}"
        if not psd_file_id or not data_file_id:
            raise HTTPException(
                status_code=400, detail="psd_file_id and data_file_id required"
            )
        user = auth.get_current_user(request)
        mapping = json.loads(layer_mapping)
        filename_fields_list = json.loads(filename_fields)
        watermark_config = (
            json.loads(watermark_config_json) if watermark_config_json else None
        )
        layer_overrides = json.loads(layer_overrides_json)
        selected_font = resolve_font(str(font_id))
        if font_id and not selected_font:
            raise HTTPException(
                status_code=400, detail="Selected font is not available."
            )
        psd_path = _resolve_psd_path(psd_file_id, user["username"] if user else None)
        data_path = UPLOAD_DIR / data_file_id
        if not psd_path.exists() or not data_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        def process_preview_sync():
            if data_path.suffix == ".csv":
                df = pd.read_csv(data_path)
            else:
                df = pd.read_excel(data_path)
            if len(df) == 0:
                raise ValueError("Data file has no rows")
            row = df.iloc[0]
            filename = (
                "_".join(str(row[field]) for field in filename_fields_list)
                if filename_fields_list
                else "preview"
            )
            filename = (
                "".join(
                    c for c in filename if c.isalnum() or c in (" ", "-", "_")
                ).strip()
                or "preview"
            )
            job_id = f"preview_{secrets.token_hex(8)}"
            job_output_dir = OUTPUT_DIR / job_id
            job_output_dir.mkdir(exist_ok=True)
            output_paths = psd_processor.process_psd(
                str(psd_path),
                row,
                mapping,
                str(job_output_dir),
                filename,
                output_format,
                watermark_config=watermark_config,
                font_path=str(selected_font) if selected_font else None,
                layer_overrides=layer_overrides,
            )
            return job_id, output_paths

        try:
            job_id, output_paths = await run_in_threadpool(process_preview_sync)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        preview_url = None
        if output_paths:
            first_path = (
                output_paths.get("png")
                or output_paths.get("webp")
                or output_paths.get("avif")
                or output_paths.get("pdf")
                or output_paths.get("psd_export")
                or list(output_paths.values())[0]
            )
            if first_path and Path(first_path).exists():
                rel = Path(first_path).name
                preview_url = f"/api/download-preview/{job_id}/{rel}"
        return JSONResponse(
            {"success": True, "preview_url": preview_url, "job_id": job_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@creative_router.get("/creative/jobs")
async def list_creative_jobs(request: Request):
    """List Creative job history. Admins can view all users."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    auth.require_module(request, "creative_psd", auth.get_current_user)
    conn = _db()
    try:
        if user.get("role") == "admin":
            rows = conn.execute(
                """
                SELECT id, username, status, payload_json, result_json, created_at, updated_at
                FROM job_queue
                WHERE job_type = 'creative_psd'
                ORDER BY created_at DESC LIMIT 200
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, username, status, payload_json, result_json, created_at, updated_at
                FROM job_queue
                WHERE username = ? AND job_type = 'creative_psd'
                ORDER BY created_at DESC LIMIT 100
                """,
                (user["username"],),
            ).fetchall()
    finally:
        conn.close()
    jobs = []
    for r in rows:
        payload = {}
        if r["payload_json"]:
            try:
                payload = json.loads(r["payload_json"]) or {}
            except Exception:
                pass
        result = None
        if r["result_json"]:
            try:
                result = json.loads(r["result_json"])
            except Exception:
                pass
        row_count = len((result or {}).get("results") or [])
        zip_link = None
        if result and result.get("zip_file"):
            zip_link = result.get("zip_file")
        elif result and result.get("job_id"):
            zip_link = f"/api/download/{result.get('job_id')}.zip"
        jobs.append(
            {
                "job_id": r["id"],
                "owner": r["username"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "row_count": row_count,
                "zip_link": zip_link,
            }
        )
    return JSONResponse(
        {"success": True, "jobs": jobs, "is_admin": user.get("role") == "admin"}
    )


@creative_router.delete("/creative/jobs/cache")
async def clear_creative_job_cache(request: Request):
    """Admin-only: remove creative job history and cached ZIP entries."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = _db()
    zip_paths: List[str] = []
    deleted_jobs = 0
    deleted_zip_entries = 0
    try:
        rows = conn.execute(
            """
            SELECT file_path
            FROM gallery_files
            WHERE LOWER(file_path) LIKE '%.zip'
            """
        ).fetchall()
        zip_paths = [row["file_path"] for row in rows if row.get("file_path")]
        deleted_zip_entries = conn.execute(
            "DELETE FROM gallery_files WHERE LOWER(file_path) LIKE '%.zip'"
        ).rowcount or 0
        deleted_jobs = conn.execute(
            "DELETE FROM job_queue WHERE job_type = 'creative_psd'"
        ).rowcount or 0
        conn.commit()
    finally:
        conn.close()

    for rel_path in zip_paths:
        try:
            gallery_path = GALLERY_DIR / rel_path
            if gallery_path.is_file():
                gallery_path.unlink()
        except Exception:
            pass

    for zip_file in OUTPUT_DIR.glob("job_*.zip"):
        try:
            zip_file.unlink()
        except Exception:
            pass

    return JSONResponse(
        {
            "success": True,
            "deleted_jobs": deleted_jobs,
            "deleted_zip_entries": deleted_zip_entries,
        }
    )


@creative_router.get("/download-preview/{job_id}/{filename}")
async def download_preview(job_id: str, filename: str):
    """Serve a preview output file (single file from preview job)."""
    # Sanitize job_id to prevent path traversal via base directory
    if ".." in job_id or "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=404, detail="Not found")

    base = OUTPUT_DIR / job_id
    path = base / filename
    try:
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        path_resolved = path.resolve()
        base_resolved = base.resolve()
        if not str(path_resolved).startswith(str(base_resolved)):
            raise HTTPException(status_code=404, detail="Not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path=str(path), filename=filename)


@creative_router.post("/process")
async def process_files(
    request: Request,
    psd_file_id: str = Form(...),
    data_file_id: str = Form(...),
    layer_mapping: str = Form(...),  # JSON string
    filename_fields: str = Form(...),  # JSON string
    output_format: str = Form("both"),  # "psd", "png", "webp", "avif", "pdf", "both"
    watermark_config: str = Form("{}"),  # JSON string
    font_id: str = Form(""),
    layer_overrides: str = Form("{}"),
    async_param: str = Query("0", alias="async"),
):
    """Process PSD files with data mapping. Use ?async=1 to enqueue and poll /api/jobs/{id}."""
    auth.require_module(request, "creative_psd", auth.get_current_user)
    user = auth.get_current_user(request)
    ident = user["username"] if user else _client_ip(request)
    _rate_limit_abort(request, "process", ident, 20, 60)
    psd_processor = getattr(request.app.state, "psd_processor", None)
    if not psd_processor:
        raise HTTPException(status_code=500, detail="PSD processor not available")
    mapping = json.loads(layer_mapping)
    filename_fields_list = json.loads(filename_fields)
    watermark_config_dict = json.loads(watermark_config) if watermark_config else None
    layer_overrides_dict = json.loads(layer_overrides) if layer_overrides else {}
    selected_font = resolve_font(font_id)
    if font_id and not selected_font:
        raise HTTPException(status_code=400, detail="Selected font is not available.")
    username = user["username"] if user else None

    if async_param in ("1", "true", "yes"):
        from automation_hub.services.job_queue import create_job, enqueue_job

        payload = {
            "psd_file_id": psd_file_id,
            "data_file_id": data_file_id,
            "layer_mapping": mapping,
            "filename_fields": filename_fields_list,
            "output_format": output_format,
            "watermark_config": watermark_config_dict,
            "font_id": font_id,
            "layer_overrides": layer_overrides_dict,
            "username": username,
        }
        try:
            qid = create_job(
                username or "anonymous",
                "creative_psd",
                payload,
            )
            enqueue_job(qid)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return JSONResponse(
            {
                "success": True,
                "async": True,
                "job_id": qid,
                "message": "Queued. Poll /api/jobs/" + str(qid),
            }
        )

    try:
        job_id, results, zip_path = await run_in_threadpool(
            _run_process_core,
            psd_file_id,
            data_file_id,
            mapping,
            filename_fields_list,
            output_format,
            username,
            psd_processor,
            watermark_config=watermark_config_dict,
            font_path=str(selected_font) if selected_font else None,
            layer_overrides=layer_overrides_dict,
        )
        return JSONResponse(
            {
                "success": True,
                "async": False,
                "job_id": job_id,
                "results": results,
                "zip_file": f"/api/download/{job_id}.zip",
            }
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
