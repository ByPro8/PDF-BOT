import hashlib
import io
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


# -------------------------
# Helpers
# -------------------------


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} kB"
    return f"{n / (1024 * 1024):.2f} MB"


def _safe_stat_time(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).astimezone().strftime("%Y:%m:%d %H:%M:%S%z")
    except Exception:
        return ""


def _pdf_header_version(pdf_bytes: bytes) -> str:
    m = re.match(rb"%PDF-(\d\.\d)", pdf_bytes[:16])
    return m.group(1).decode("ascii", errors="ignore") if m else ""


def _detect_linearized(pdf_bytes: bytes) -> bool:
    return b"/Linearized" in pdf_bytes[:4096]


def _detect_signatures(pdf_bytes: bytes) -> bool:
    return (b"/ByteRange" in pdf_bytes) and (
        b"/Sig" in pdf_bytes or b"/Adobe.PPKLite" in pdf_bytes
    )


def _count_startxref(pdf_bytes: bytes) -> int:
    return pdf_bytes.count(b"startxref")


def _startxref_value(pdf_bytes: bytes) -> str:
    # last startxref value in file
    m = re.findall(rb"startxref\s+(\d+)\s+%%EOF", pdf_bytes, flags=re.S)
    if not m:
        return ""
    try:
        return m[-1].decode("ascii", errors="ignore")
    except Exception:
        return ""


def _count_eof(pdf_bytes: bytes) -> int:
    return pdf_bytes.count(b"%%EOF")


def _estimate_obj_count(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"\n\d+\s+\d+\s+obj\b", pdf_bytes))


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


# -------------------------
# Python Meta (fingerprints)
# -------------------------


def _format_python_meta(
    pdf_path: Path,
    display_name: str,
    pdf_bytes: Optional[bytes] = None,
    reader: Optional[PdfReader] = None,
) -> str:
    if pdf_bytes is None:
        pdf_bytes = pdf_path.read_bytes()
    st = pdf_path.stat()

    sha256 = _sha256(pdf_bytes)
    md5 = _md5(pdf_bytes)

    first1k_sha256 = _sha256(pdf_bytes[:1024])
    last1k_sha256 = (
        _sha256(pdf_bytes[-1024:]) if len(pdf_bytes) >= 1024 else _sha256(pdf_bytes)
    )

    pdf_ver = _pdf_header_version(pdf_bytes)
    is_linearized = _detect_linearized(pdf_bytes)
    has_sigs = _detect_signatures(pdf_bytes)
    startxref_count = _count_startxref(pdf_bytes)
    startxref_val = _startxref_value(pdf_bytes)
    eof_count = _count_eof(pdf_bytes)
    obj_est = _estimate_obj_count(pdf_bytes)
    if reader is None:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
        except Exception:
            reader = PdfReader(str(pdf_path))
    pages = len(reader.pages)
    encrypted = bool(getattr(reader, "is_encrypted", False))

    info = {}
    try:
        info = dict(reader.metadata or {})
    except Exception:
        info = {}

    trailer_keys = []
    try:
        trailer_keys = list(reader.trailer.keys())
    except Exception:
        trailer_keys = []

    doc_id = None
    try:
        doc_id = reader.trailer.get("/ID")
    except Exception:
        doc_id = None

    # Page0 fingerprints
    page0_content_sha256 = ""
    page0_fonts = []
    page0_xobjects = []
    page0_images_count = 0

    try:
        p0 = reader.pages[0]

        c = p0.get_contents()
        if c is not None:
            data = c.get_data()
            page0_content_sha256 = hashlib.sha256(data).hexdigest()

        res = p0.get("/Resources") or {}
        fonts = res.get("/Font") or {}
        page0_fonts = list(getattr(fonts, "keys", lambda: [])())

        xobj = res.get("/XObject") or {}
        page0_xobjects = list(getattr(xobj, "keys", lambda: [])())

        try:
            for k in page0_xobjects:
                xo = xobj[k]
                try:
                    if str(xo.get("/Subtype")) == "/Image":
                        page0_images_count += 1
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass

    lines = []
    lines.append("---- PythonMeta ----")
    lines.append("---- System ----")
    lines.append(f"File Name                     : {display_name}")
    lines.append(f"Directory                     : {str(pdf_path.parent)}")
    lines.append(
        f"File Size                     : {_fmt_bytes(len(pdf_bytes))} ({len(pdf_bytes)} bytes)"
    )
    lines.append(f"File Modify Date              : {_safe_stat_time(st.st_mtime)}")
    lines.append(f"File Access Date              : {_safe_stat_time(st.st_atime)}")
    lines.append(f"File Inode Change Date        : {_safe_stat_time(st.st_ctime)}")
    lines.append("")

    lines.append("---- Hashes ----")
    lines.append(f"SHA256                        : {sha256}")
    lines.append(f"MD5                           : {md5}")
    lines.append(f"First 1KB SHA256              : {first1k_sha256}")
    lines.append(f"Last  1KB SHA256              : {last1k_sha256}")
    lines.append("")

    lines.append("---- PDF ----")
    lines.append(f"PDF Header Version            : {pdf_ver}")
    lines.append(f"Pages                         : {pages}")
    lines.append(f"Encrypted                     : {encrypted}")
    lines.append(f"Linearized (heuristic)        : {is_linearized}")
    lines.append(f"Signatures Present (heuristic): {has_sigs}")
    lines.append(f"%%EOF count                   : {eof_count}")
    lines.append(f"startxref count               : {startxref_count}")
    lines.append(f"startxref value (last)        : {startxref_val or '(none)'}")
    lines.append(f"Object count (estimated)      : {obj_est}")
    lines.append("")

    lines.append("---- PDF Info (Document Metadata) ----")
    if info:
        for k in sorted(info.keys()):
            v = info.get(k)
            lines.append(f"{str(k).lstrip('/'):28}: {v}")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("---- Trailer ----")
    lines.append(
        f"Trailer Keys                  : {', '.join(map(str, trailer_keys)) if trailer_keys else '(none)'}"
    )
    if doc_id is not None:
        try:
            parts = []
            for item in doc_id:
                if isinstance(item, (bytes, bytearray)):
                    parts.append(item.hex())
                else:
                    parts.append(str(item))
            lines.append(f"Document ID                   : {parts}")
        except Exception:
            lines.append(f"Document ID                   : {doc_id}")
    lines.append("")

    lines.append("---- Page0 Fingerprints ----")
    lines.append(f"Page0 Content SHA256          : {page0_content_sha256 or '(none)'}")
    lines.append(
        f"Page0 Fonts                   : {', '.join(map(str, page0_fonts)) if page0_fonts else '(none)'}"
    )
    lines.append(
        f"Page0 XObjects                : {', '.join(map(str, page0_xobjects)) if page0_xobjects else '(none)'}"
    )
    lines.append(f"Page0 Images Count            : {page0_images_count}")
    lines.append("")

    return "\n".join(lines).strip()


# -------------------------
# ExifTool
# -------------------------


def _exiftool_version(exe: str) -> str:
    try:
        p = subprocess.run([exe, "-ver"], capture_output=True, text=True, timeout=6)
        v = (p.stdout or "").strip()
        return v
    except Exception:
        return ""


def _format_exiftool_grouped(raw: str, display_name: str, exif_ver: str) -> str:
    # raw lines: [System] FileName : something
    groups: Dict[str, list[str]] = {}
    order: list[str] = []

    for line in raw.splitlines():
        line = line.rstrip("\n")
        m = re.match(r"^\[(.+?)\]\s*(.+?)\s*:\s*(.*)$", line)
        if not m:
            continue

        g = m.group(1).strip()
        tag = m.group(2).strip()
        val = m.group(3)

        # keep user filename for templates
        if g.lower() == "system" and tag.lower() in ("filename", "file name"):
            val = display_name

        if g not in groups:
            groups[g] = []
            order.append(g)

        groups[g].append(f"{tag:28}: {val}")

    out = []
    out.append("---- ExifTool ----")
    out.append(f"ExifTool Version              : {exif_ver or '(unknown)'}")
    out.append("")

    for g in order:
        out.append(f"---- {g} ----")
        out.extend(groups[g])
        out.append("")

    return "\n".join(out).strip()


def _run_exiftool(pdf_path: Path, display_name: str) -> str:
    # Priority:
    # 1) bundled repo exiftool (perl script) via bin/exiftool/run_exiftool.sh
    # 2) system exiftool if available
    bundled = (
        Path(__file__).resolve().parents[2] / "bin" / "exiftool" / "run_exiftool.sh"
    )
    if bundled.exists():
        try:
            proc = subprocess.run(
                [str(bundled), "-a", "-G0:1", "-s", "-sort", str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            raw = proc.stdout or ""
            if not raw.strip():
                err = (proc.stderr or "").strip()
                return f"ExifTool returned no output. {('ERR: ' + err) if err else ''}".strip()

            # version
            try:
                pv = subprocess.run(
                    [str(bundled), "-ver"], capture_output=True, text=True, timeout=6
                )
                ver = (pv.stdout or "").strip()
            except Exception:
                ver = ""

            return _format_exiftool_grouped(
                raw, display_name=display_name, exif_ver=ver
            )

        except subprocess.TimeoutExpired:
            return "ExifTool timed out."
        except Exception as e:
            return f"ExifTool failed: {type(e).__name__}: {e}"

    exe = shutil.which("exiftool")
    if not exe:
        return "ExifTool not available on server (not installed and no bundled exiftool found)."

    try:
        proc = subprocess.run(
            [exe, "-a", "-G0:1", "-s", "-sort", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=12,
        )
        raw = proc.stdout or ""
        if not raw.strip():
            err = (proc.stderr or "").strip()
            return (
                f"ExifTool returned no output. {('ERR: ' + err) if err else ''}".strip()
            )

        ver = _exiftool_version(exe)
        return _format_exiftool_grouped(raw, display_name=display_name, exif_ver=ver)

    except subprocess.TimeoutExpired:
        return "ExifTool timed out."
    except Exception as e:
        return f"ExifTool failed: {type(e).__name__}: {e}"


# -------------------------
# Public API
# -------------------------


def extract_metadata_logs(
    pdf_path: Path,
    display_name: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    pdf_reader: Optional[PdfReader] = None,
) -> Dict[str, str]:
    name = display_name or pdf_path.name

    try:
        py = _format_python_meta(pdf_path, name, pdf_bytes=pdf_bytes, reader=pdf_reader)
    except Exception as e:
        py = f"PythonMeta failed: {type(e).__name__}: {e}"

    ex = _run_exiftool(pdf_path, name)
    return {"python": py, "exiftool": ex}
