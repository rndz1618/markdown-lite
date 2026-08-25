#!/usr/bin/env python3
"""
Markdown Lite - Lightweight self-hosted Markdown Viewer & Editor
Modern UI, secure path handling, configurable storage root.
"""

import os
import re
import secrets
from functools import wraps
from pathlib import Path
from urllib.parse import unquote

from flask import (
    Flask, request, jsonify, render_template, send_from_directory,
    abort, Response, redirect, url_for, session
)
from dotenv import load_dotenv
import markdown
import bleach

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ============== CONFIG ==============
MD_ROOT = Path(os.environ.get("MD_ROOT", "./data")).resolve()
USERNAME = os.environ.get("MD_USER", "admin")
PASSWORD = os.environ.get("MD_PASS", "changeme")
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")
ENABLE_AUTH = os.environ.get("ENABLE_AUTH", "true").lower() in ("1", "true", "yes")

# Allowed tags for safe HTML rendering (XSS protection)
ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
    "img", "hr", "br", "span", "div", "strong", "em", "del", "a", "sup", "sub"
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

# Ensure root exists
MD_ROOT.mkdir(parents=True, exist_ok=True)


def check_auth(username, password):
    return username == USERNAME and password == PASSWORD


def authenticate():
    return Response(
        "Authentication required.\n", 401,
        {"WWW-Authenticate": 'Basic realm="Markdown Lite"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ENABLE_AUTH:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def safe_path(rel_path: str) -> Path:
    """Resolve path relative to MD_ROOT and prevent path traversal."""
    if not rel_path or rel_path in (".", "/"):
        return MD_ROOT

    # Normalize and strip leading slashes
    rel_path = unquote(rel_path).lstrip("/").replace("\\", "/")
    # Remove any .. components
    parts = [p for p in rel_path.split("/") if p and p != ".." and p != "."]
    candidate = MD_ROOT.joinpath(*parts).resolve()

    # Must stay inside MD_ROOT
    try:
        candidate.relative_to(MD_ROOT)
    except ValueError:
        abort(403, description="Path outside allowed directory")

    return candidate


def is_md_file(path: Path) -> bool:
    return path.suffix.lower() in (".md", ".markdown", ".mdown", ".mkd")


def list_directory(rel: str = ""):
    """Return sorted list of files and folders under relative path."""
    base = safe_path(rel)
    if not base.is_dir():
        abort(404)

    items = []
    for entry in sorted(base.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        if entry.name.startswith("."):
            continue
        rel_entry = str(entry.relative_to(MD_ROOT)).replace("\\", "/")
        items.append({
            "name": entry.name,
            "path": rel_entry,
            "is_dir": entry.is_dir(),
            "size": entry.stat().st_size if entry.is_file() else 0,
            "mtime": int(entry.stat().st_mtime),
        })
    return items


def render_md(content: str) -> str:
    """Convert Markdown to sanitized HTML."""
    html = markdown.markdown(
        content,
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "nl2br",
            "sane_lists",
            "codehilite",
        ],
        extension_configs={
            "codehilite": {"css_class": "highlight", "linenums": False}
        }
    )
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


# ============== ROUTES ==============

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
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/read")
@requires_auth
def api_read():
    path = request.args.get("path", "")
    target = safe_path(path)
    if not target.is_file() or not is_md_file(target):
        return jsonify({"ok": False, "error": "Not a markdown file"}), 404
    try:
        content = target.read_text(encoding="utf-8")
        return jsonify({
            "ok": True,
            "path": path,
            "content": content,
            "html": render_md(content),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/save", methods=["POST"])
@requires_auth
def api_save():
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    content = data.get("content", "")

    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400

    target = safe_path(path)
    if target.exists() and target.is_dir():
        return jsonify({"ok": False, "error": "Path is a directory"}), 400

    # Force .md extension if missing
    if not is_md_file(target):
        target = target.with_suffix(".md")
        path = str(target.relative_to(MD_ROOT)).replace("\\", "/")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return jsonify({"ok": True, "path": path, "message": "Saved"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/create", methods=["POST"])
@requires_auth
def api_create():
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    is_dir = data.get("is_dir", False)

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
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {target.stem}\n\n", encoding="utf-8")
        rel = str(target.relative_to(MD_ROOT)).replace("\\", "/")
        return jsonify({"ok": True, "path": rel})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
@requires_auth
def api_delete():
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400

    target = safe_path(path)
    if target == MD_ROOT:
        return jsonify({"ok": False, "error": "Cannot delete root"}), 400

    try:
        if target.is_dir():
            # Only empty dirs or force? For safety, only empty
            if any(target.iterdir()):
                return jsonify({"ok": False, "error": "Directory not empty"}), 400
            target.rmdir()
        elif target.is_file():
            target.unlink()
        else:
            return jsonify({"ok": False, "error": "Not found"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/rename", methods=["POST"])
@requires_auth
def api_rename():
    data = request.get_json(force=True) or {}
    old_path = data.get("old_path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not old_path or not new_name:
        return jsonify({"ok": False, "error": "old_path and new_name required"}), 400

    # Sanitize new_name
    new_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", new_name).strip()
    if not new_name:
        return jsonify({"ok": False, "error": "Invalid name"}), 400

    old = safe_path(old_path)
    if not old.exists() or old == MD_ROOT:
        return jsonify({"ok": False, "error": "Not found"}), 404

    new = old.parent / new_name
    # Re-validate
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
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/view/<path:filepath>")
@requires_auth
def view_file(filepath):
    """Server-side rendered view (fallback / shareable)."""
    target = safe_path(filepath)
    if not target.is_file() or not is_md_file(target):
        abort(404)
    content = target.read_text(encoding="utf-8")
    html = render_md(content)
    return render_template("view.html", title=target.name, content=html, path=filepath)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "root": str(MD_ROOT)})


if __name__ == "__main__":
    print(f"Markdown Lite running on http://{HOST}:{PORT}")
    print(f"Storage root: {MD_ROOT}")
    print(f"Auth enabled: {ENABLE_AUTH}")
    app.run(host=HOST, port=PORT, debug=False)
