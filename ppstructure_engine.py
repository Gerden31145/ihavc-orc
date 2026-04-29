import io
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class PPStructureDiagnostics:
    engine: str
    model_loaded: bool
    timing_ms: Dict[str, int]
    tables_found: int
    blocks_found: int
    error: Optional[str] = None


_ppstructure_singleton = {"engine": None}


def _lazy_load_engine() -> Tuple[Optional[Any], Optional[str]]:
    """
    Lazy-load PP-Structure engine to avoid importing heavy deps at module import time.
    Returns (engine, error_message).
    """
    if _ppstructure_singleton["engine"] is not None:
        return _ppstructure_singleton["engine"], None

    try:
        from paddleocr import PPStructure  # type: ignore
    except Exception as exc:  # pragma: no cover
        return None, f"paddleocr_unavailable:{exc}"

    try:
        # show_log=False to keep API logs clean.
        engine = PPStructure(show_log=False)
        _ppstructure_singleton["engine"] = engine
        return engine, None
    except Exception as exc:  # pragma: no cover
        return None, f"ppstructure_init_failed:{exc}"


def _html_table_to_matrix(html: str) -> List[List[str]]:
    """
    Convert PP-Structure table HTML into a 2D string matrix.
    Uses pandas.read_html when available, otherwise falls back to a minimal parser.
    """
    html = (html or "").strip()
    if not html:
        return []

    # Fast path: pandas.read_html (requires lxml or bs4 backend)
    try:
        import pandas as pd  # type: ignore

        dfs = pd.read_html(html)
        if not dfs:
            return []
        df = dfs[0].fillna("")
        matrix: List[List[str]] = [list(map(str, df.columns.tolist()))]
        matrix.extend(df.astype(str).values.tolist())
        # When the HTML already includes header rows, pandas may auto-generate columns like 0..N.
        # If headers are purely numeric and first row looks like header text, promote row0.
        if matrix and matrix[0] and all(str(c).isdigit() for c in matrix[0]):
            if len(matrix) >= 2 and any(cell.strip() for cell in matrix[1]):
                promoted = [str(cell) for cell in matrix[1]]
                matrix = [promoted] + matrix[2:]
        return [[cell.strip() for cell in row] for row in matrix]
    except Exception:
        pass

    # Fallback: very small HTML table parser using stdlib only.
    # This intentionally keeps dependencies optional; it handles basic <tr><td>/<th>.
    import re

    def strip_tags(text: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</(p|div|span)>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"[ \t]+", " ", text).strip()

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S)
    matrix: List[List[str]] = []
    for row_html in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S)
        if cells:
            matrix.append([strip_tags(cell) for cell in cells])

    return matrix


def run_ppstructure(image_bytes: bytes) -> Tuple[List[List[str]], Dict[str, Any], PPStructureDiagnostics]:
    """
    Run PP-Structure on image bytes and return:
      - best table matrix (headers + rows)
      - raw structured blocks (lightweight)
      - diagnostics
    """
    started = time.perf_counter()
    engine, load_error = _lazy_load_engine()
    if not engine:
        diag = PPStructureDiagnostics(
            engine="ppstructure",
            model_loaded=False,
            timing_ms={"load": int((time.perf_counter() - started) * 1000)},
            tables_found=0,
            blocks_found=0,
            error=load_error,
        )
        return [], {"blocks": []}, diag

    load_done = time.perf_counter()

    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover
        diag = PPStructureDiagnostics(
            engine="ppstructure",
            model_loaded=True,
            timing_ms={"load": int((load_done - started) * 1000)},
            tables_found=0,
            blocks_found=0,
            error=f"pillow_required:{exc}",
        )
        return [], {"blocks": []}, diag

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        diag = PPStructureDiagnostics(
            engine="ppstructure",
            model_loaded=True,
            timing_ms={"load": int((load_done - started) * 1000)},
            tables_found=0,
            blocks_found=0,
            error=f"image_decode_failed:{exc}",
        )
        return [], {"blocks": []}, diag

    try:
        result: Sequence[Dict[str, Any]] = engine(image)  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover
        diag = PPStructureDiagnostics(
            engine="ppstructure",
            model_loaded=True,
            timing_ms={
                "load": int((load_done - started) * 1000),
                "infer": int((time.perf_counter() - load_done) * 1000),
            },
            tables_found=0,
            blocks_found=0,
            error=f"ppstructure_infer_failed:{exc}",
        )
        return [], {"blocks": []}, diag

    infer_done = time.perf_counter()

    blocks: List[Dict[str, Any]] = []
    tables: List[List[List[str]]] = []
    for item in result or []:
        block_type = item.get("type")
        res = item.get("res") or {}
        blocks.append(
            {
                "type": block_type,
                "bbox": item.get("bbox"),
                "score": item.get("score"),
                "text": res.get("text") if isinstance(res, dict) else None,
                "html": res.get("html") if isinstance(res, dict) else None,
            }
        )
        if block_type == "table":
            html = res.get("html") if isinstance(res, dict) else None
            table_matrix = _html_table_to_matrix(html or "")
            if table_matrix:
                tables.append(table_matrix)

    # Choose the biggest table by (rows * cols)
    best_table: List[List[str]] = []
    if tables:
        best_table = max(tables, key=lambda t: (len(t) * (len(t[0]) if t and t[0] else 0)))

    diag = PPStructureDiagnostics(
        engine="ppstructure",
        model_loaded=True,
        timing_ms={
            "load": int((load_done - started) * 1000),
            "infer": int((infer_done - load_done) * 1000),
            "total": int((infer_done - started) * 1000),
        },
        tables_found=len(tables),
        blocks_found=len(blocks),
    )
    return best_table, {"blocks": blocks}, diag

