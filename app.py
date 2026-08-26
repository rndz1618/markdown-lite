#!/usr/bin/env python3
"""
Markdown Lite - Lightweight self-hosted Markdown Viewer & Editor
Modern UI, secure path handling, configurable storage root.
"""

import logging
import os
import re
import secrets
import tempfile
from functools import wraps
from pathlib import Path
from urllib.parse import unquote

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    abort,
    redirect,
    url_for,
    session,
)
from dotenv import load_dotenv
import markdown
import bleach

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("markdown-lite")

app = Flask(__name__)

# ============== CONFIG ==============
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    log.warning(
        "SECRET_KEY not set — using ephemeral key. "
        "Sessions will reset on restart. Set SECRET_KEY in .env for production."
    )
app.secret_key = SECRET_KEY
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7  # 7 days
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Limit request body size (1 MB is plenty for Markdown notes)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 1 * 1024 * 1024))

MD_ROOT = Path(os.environ.get("MD_ROOT", "./data")).resolve()
USERNAME = os.environ.get("MD_USER", "admin")
PASSWORD = os.environ.get("MD_PASS", "changeme")
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")
ENABLE_AUTH = os.environ.get("ENABLE_AUTH", "true").lower() in ("1", "true", "yes")

# Fail-fast on default credentials when auth is enabled
if ENABLE_AUTH and PASSWORD in ("changeme", "password", "admin", ""):
    log.error(
        "INSECURE DEFAULT PASSWORD DETECTED. "
        "Set a strong MD_PASS in .env before running in production."
    )
    if os.environ.get("FORCE_SECURE", "").lower() in ("1", "true", "yes"):
        raise SystemExit("Refusing to start with default password (FORCE_SECURE=1).")

ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
    "img", "hr", "br", "span", "div", "strong", "em", "del", "a", "sup", "sub",
]
ALLOWED_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "img": ["src", "alt", "title"],
    "a": ["href", "title", "rel"],
    "code": ["class"],
    "span": ["class"],
    "div": ["class"],
    "td": ["align"],
    "th": ["align"],
}

MD_ROOT.mkdir(parents=True, exist_ok=True)

BUILTIN_TEMPLATES = {
    "blank": {"name": "Kosong", "body": "# {{title}}\n\n"},
    "catatan": {
        "name": "Catatan harian",
        "body": (
            "# {{title}}\n\n"
            "> Tanggal: {{date}}\n\n"
            "## Ringkasan\n\n"
            "- \n\n"
            "## Detail\n\n"
        ),
    },
    "rapat": {
        "name": "Notulen rapat",
        "body": (
            "# {{title}}\n\n"
            "- **Tanggal:** {{date}}\n"
            "- **Peserta:** \n"
            "- **Agenda:** \n\n"
            "## Pembahasan\n\n"
            "1. \n\n"
            "## Keputusan\n\n"
            "- \n\n"
            "## Tindak lanjut\n\n"
            "| Item | PIC | Deadline |\n"
            "| --- | --- | --- |\n"
            "|  |  |  |\n"
        ),
    },
    "todo": {
        "name": "Daftar tugas",
        "body": (
            "# {{title}}\n\n"
            "- [ ] Tugas 1\n"
            "- [ ] Tugas 2\n"
            "- [ ] Tugas 3\n"
        ),
    },
}
TEMPLATES_DIR_NAME = "_templates"
SUPPORTED_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd")


def check_credentials(username: str, password: str) -> bool:
    return secrets.compare_digest(username, USERNAME) and secrets.compare_digest(
        password, PASSWORD
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ENABLE_AUTH:
            return f(*args, **kwargs)
        if session.get("logged_in"):
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return redirect(url_for("login", next=request.path))
    return decorated


def check_csrf():
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return
    host = request.host_url.rstrip("/")
    if not (origin == host or origin.startswith(host + "/")):
        abort(403, description="CSRF check failed")


def safe_path(rel_path: str) -> Path:
    if not rel_path or rel_path in (".", "/"):
        return MD_ROOT
    rel_path = unquote(rel_path).lstrip("/").replace("\\", "/")
    parts = [p for p in rel_path.split("/") if p and p != ".." and p != "."]
    candidate = (MD_ROOT.joinpath(*parts)).resolve()
    try:
        candidate.relative_to(MD_ROOT)
    except ValueError:
        abort(403, description="Path outside allowed directory")
    return candidate


def is_md_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def list_templates():
    items = [
        {"id": tid, "name": meta["name"], "source": "builtin"}
        for tid, meta in BUILTIN_TEMPLATES.items()
    ]
    tdir = MD_ROOT / TEMPLATES_DIR_NAME
    if tdir.is_dir():
        for entry in sorted(tdir.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_file() and is_md_file(entry):
                items.append({
                    "id": f"custom:{entry.stem}",
                    "name": entry.stem.replace("-", " ").replace("_", " ").title(),
                    "source": "custom",
                })
    return items


def resolve_template_body(template_id: str, title: str) -> str:
    from datetime import date
    date_str = date.today().isoformat()
    body = None
    if template_id and template_id.startswith("custom:"):
        stem = re.sub(r"[^a-zA-Z0-9_\-]", "", template_id.split(":", 1)[1])
        candidate = (MD_ROOT / TEMPLATES_DIR_NAME / f"{stem}.md").resolve()
        try:
            candidate.relative_to((MD_ROOT / TEMPLATES_DIR_NAME).resolve())
            if candidate.is_file():
                body = candidate.read_text(encoding="utf-8")
        except (ValueError, OSError):
            body = None
    elif template_id in BUILTIN_TEMPLATES:
        body = BUILTIN_TEMPLATES[template_id]["body"]
    if body is None:
        body = BUILTIN_TEMPLATES["blank"]["body"]
    return body.replace("{{title}}", title).replace("{{date}}", date_str)


def list_directory(rel: str = ""):
    """Hanya folder + file Markdown yang didukung."""
    base = safe_path(rel)
    if not base.is_dir():
        abort(404)
    items = []
    for entry in sorted(base.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        name = entry.name
        if name.startswith(".") or name.startswith("__"):
            continue
        if entry.is_dir() and name in (TEMPLATES_DIR_NAME, "venv", "node_modules"):
            continue
        if entry.is_file():
            if not is_md_file(entry):
                continue
        elif not entry.is_dir():
            continue
        try:
            entry.resolve().relative_to(MD_ROOT)
        except (ValueError, OSError):
            continue
        rel_entry = str(entry.relative_to(MD_ROOT)).replace("\\", "/")
        try:
            st = entry.stat()
            size = st.st_size if entry.is_file() else 0
            mtime = int(st.st_mtime)
        except OSError:
            size, mtime = 0, 0
        items.append({"name": name, "path": rel_entry, "is_dir": entry.is_dir(), "size": size, "mtime": mtime})
    return items


def render_md(content: str) -> str:
    html = markdown.markdown(
        content,
        extensions=["fenced_code", "tables", "toc", "nl2br", "sane_lists", "codehilite"],
        extension_configs={"codehilite": {"css_class": "highlight", "linenums": False}},
    )
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def get_json_body():
    data = request.get_json(silent=True)
    return data or {}


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://maxcdn.bootstrapcdn.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://maxcdn.bootstrapcdn.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'"
    )
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ENABLE_AUTH:
        return redirect(url_for("index"))
    if session.get("logged_in"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if check_credentials(username, password):
            session.clear()
            session["logged_in"] = True
            session["user"] = username
            session.permanent = True
            nxt = request.args.get("next") or request.form.get("next") or "/"
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/"
            return redirect(nxt)
        error = "Username atau password salah."
        log.warning("Failed login attempt for user=%s", username)
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@requires_auth
def index():
    return render_template("index.html")


@app.route("/api/list")
@requires_auth
def api_list():
    path = request.args.get("path", "")
    try:
        items = list_directory(path)
        return jsonify({"ok": True, "path": path, "items": items})
    except Exception:
        log.exception("list failed for path=%s", path)
        return jsonify({"ok": False, "error": "Failed to list directory"}), 400


@app.route("/api/read")
@requires_auth
def api_read():
    path = request.args.get("path", "")
    target = safe_path(path)
    if not target.is_file() or not is_md_file(target):
        return jsonify({"ok": False, "error": "Not a markdown file"}), 404
    try:
        content = target.read_text(encoding="utf-8")
        return jsonify({"ok": True, "path": path, "content": content, "html": render_md(content)})
    except Exception:
        log.exception("read failed for path=%s", path)
        return jsonify({"ok": False, "error": "Failed to read file"}), 500


@app.route("/api/save", methods=["POST"])
@requires_auth
def api_save():
    check_csrf()
    data = get_json_body()
    path = (data.get("path") or "").strip()
    content = data.get("content", "")
    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400
    if not isinstance(content, str):
        return jsonify({"ok": False, "error": "Invalid content"}), 400
    target = safe_path(path)
    if target.exists() and target.is_dir():
        return jsonify({"ok": False, "error": "Path is a directory"}), 400
    if not is_md_file(target):
        target = target.with_suffix(".md")
        path = str(target.relative_to(MD_ROOT)).replace("\\", "/")
    try:
        atomic_write(target, content)
        return jsonify({"ok": True, "path": path, "message": "Saved"})
    except Exception:
        log.exception("save failed for path=%s", path)
        return jsonify({"ok": False, "error": "Failed to save file"}), 500


@app.route("/api/create", methods=["POST"])
@requires_auth
def api_create():
    check_csrf()
    data = get_json_body()
    path = (data.get("path") or "").strip()
    is_dir = bool(data.get("is_dir", False))
    template_id = (data.get("template") or "blank").strip()
    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400
    target = safe_path(path)
    if target.exists():
        return jsonify({"ok": False, "error": "Already exists"}), 400
    try:
        if is_dir:
            target.mkdir(parents=True, exist_ok=False)
        else:
            if not is_md_file(target):
                target = target.with_suffix(".md")
            content = resolve_template_body(template_id, target.stem)
            atomic_write(target, content)
        rel = str(target.relative_to(MD_ROOT)).replace("\\", "/")
        return jsonify({"ok": True, "path": rel})
    except Exception:
        log.exception("create failed for path=%s", path)
        return jsonify({"ok": False, "error": "Failed to create"}), 500


@app.route("/api/config")
@requires_auth
def api_config():
    folders = []
    try:
        for entry in sorted(MD_ROOT.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir() and not entry.name.startswith(".") and entry.name != TEMPLATES_DIR_NAME:
                try:
                    entry.resolve().relative_to(MD_ROOT)
                except ValueError:
                    continue
                folders.append({"name": entry.name, "path": str(entry.relative_to(MD_ROOT)).replace("\\", "/")})
    except OSError:
        pass
    return jsonify({
        "ok": True,
        "templates": list_templates(),
        "folders": folders,
        "root_label": MD_ROOT.name or str(MD_ROOT),
        "default_template": os.environ.get("DEFAULT_TEMPLATE", "blank"),
        "default_folder": os.environ.get("DEFAULT_FOLDER", ""),
    })


@app.route("/api/delete", methods=["POST"])
@requires_auth
def api_delete():
    check_csrf()
    data = get_json_body()
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400
    target = safe_path(path)
    if target == MD_ROOT:
        return jsonify({"ok": False, "error": "Cannot delete root"}), 400
    try:
        if target.is_dir():
            if any(target.iterdir()):
                return jsonify({"ok": False, "error": "Directory not empty"}), 400
            target.rmdir()
        elif target.is_file():
            target.unlink()
        else:
            return jsonify({"ok": False, "error": "Not found"}), 404
        log.info("deleted path=%s", path)
        return jsonify({"ok": True})
    except Exception:
        log.exception("delete failed for path=%s", path)
        return jsonify({"ok": False, "error": "Failed to delete"}), 500


@app.route("/api/rename", methods=["POST"])
@requires_auth
def api_rename():
    check_csrf()
    data = get_json_body()
    old_path = (data.get("old_path") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    if not old_path or not new_name:
        return jsonify({"ok": False, "error": "old_path and new_name required"}), 400
    new_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", new_name).strip()
    if not new_name:
        return jsonify({"ok": False, "error": "Invalid name"}), 400
    old = safe_path(old_path)
    if not old.exists() or old == MD_ROOT:
        return jsonify({"ok": False, "error": "Not found"}), 404
    new = old.parent / new_name
    try:
        new.resolve().relative_to(MD_ROOT)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid target"}), 403
    if new.exists():
        return jsonify({"ok": False, "error": "Target already exists"}), 400
    try:
        old.rename(new)
        rel = str(new.relative_to(MD_ROOT)).replace("\\", "/")
        return jsonify({"ok": True, "path": rel})
    except Exception:
        log.exception("rename failed %s -> %s", old_path, new_name)
        return jsonify({"ok": False, "error": "Failed to rename"}), 500


@app.route("/view/<path:filepath>")
@requires_auth
def view_file(filepath):
    target = safe_path(filepath)
    if not target.is_file() or not is_md_file(target):
        abort(404)
    content = target.read_text(encoding="utf-8")
    html = render_md(content)
    return render_template("view.html", title=target.name, content=html, path=filepath)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print(f"Markdown Lite running on http://{HOST}:{PORT}")
    print(f"Storage root: {MD_ROOT}")
    print(f"Auth enabled: {ENABLE_AUTH}")
    app.run(host=HOST, port=PORT, debug=False)
