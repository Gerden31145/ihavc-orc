import io
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - optional dependency
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None


NUMERIC_HEADER_HINTS = (
    "投档",
    "分数",
    "最低",
    "最高",
    "位次",
    "排名",
    "计划",
    "人数",
    "学费",
    "排位",
    "线差",
)

STICKY_HEADER_SPLIT_RULES = (
    # Common Gaokao table sticky headers (no separator between two concepts)
    ("投档线投档最低排位", ("投档线", "投档最低排位")),
    ("投档线最低排位", ("投档线", "最低排位")),
)

AMBIGUOUS_DIGIT_MAP = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "B": "8",
        "G": "6",
    }
)


def preprocess_image_for_ocr(image_bytes: bytes) -> Tuple[bytes, Dict[str, Any]]:
    if not Image:
        return image_bytes, {"applied": False, "reason": "pillow_unavailable"}

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image).convert("L")

        width, height = image.size
        scale = 1.0
        long_side = max(width, height)
        if long_side < 1800:
            scale = min(2.2, 1800 / max(long_side, 1))
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        image = ImageOps.autocontrast(image)
        image = ImageEnhance.Contrast(image).enhance(1.35)
        image = image.filter(ImageFilter.MedianFilter(size=3))
        image = ImageEnhance.Sharpness(image).enhance(1.6)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), {
            "applied": True,
            "mode": "grayscale_autocontrast_sharpen",
            "scale": round(scale, 2),
            "output_format": "PNG",
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        return image_bytes, {"applied": False, "reason": f"preprocess_failed:{exc}"}


def normalize_cell_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def extract_numeric_tokens(text: str) -> List[str]:
    normalized = normalize_cell_text(text)
    if not normalized:
        return []

    chunks = re.split(r"[\s\n/]+", normalized)
    tokens = []
    for chunk in chunks:
        candidate = chunk.translate(AMBIGUOUS_DIGIT_MAP)
        candidate = re.sub(r"[^0-9.\-]", "", candidate)
        if candidate and re.fullmatch(r"-?\d+(?:\.\d+)?", candidate):
            tokens.append(candidate)
    return tokens


def looks_numeric(text: str) -> bool:
    tokens = extract_numeric_tokens(text)
    if not tokens:
        return False
    # Alphanumeric codes like "A1", "B2" are NOT numeric values
    compact = re.sub(r"\s+", "", normalize_cell_text(text))
    if _ALPHANUMERIC_CODE_RE.match(compact):
        return False
    joined = "".join(tokens)
    return len(joined) >= max(1, len(compact) // 2)


def infer_numeric_columns(table: Sequence[Sequence[str]]) -> List[int]:
    if not table:
        return []

    headers = table[0]
    numeric_columns: List[int] = []
    for index, header in enumerate(headers):
        values = [
            normalize_cell_text(row[index])
            for row in table[1:]
            if index < len(row) and normalize_cell_text(row[index])
        ]
        header_hit = any(hint in normalize_cell_text(header) for hint in NUMERIC_HEADER_HINTS)
        numeric_ratio = (
            sum(1 for value in values if looks_numeric(value)) / len(values)
            if values
            else 0.0
        )
        if header_hit or numeric_ratio >= 0.65:
            numeric_columns.append(index)
    return numeric_columns


# Alphanumeric codes like "A1", "B2", "C10" — NOT numeric values
_ALPHANUMERIC_CODE_RE = re.compile(r"^[a-zA-Z]+\d+$|^\d+[a-zA-Z]+$")


def normalize_numeric_text(text: str) -> str:
    normalized = normalize_cell_text(text)
    if not normalized:
        return ""
    tokens = extract_numeric_tokens(normalized)
    if not tokens:
        return normalized
    if "\n" in normalized or " " in normalized:
        return "\n".join(tokens)
    # Don't strip letter prefixes from alphanumeric codes like "A1", "B2"
    compact = re.sub(r"\s+", "", normalized)
    if _ALPHANUMERIC_CODE_RE.match(compact):
        return normalized
    return tokens[0]


def _split_sticky_header_cell(header: str) -> Optional[Tuple[str, str]]:
    normalized = normalize_cell_text(header)
    if not normalized:
        return None

    compact = re.sub(r"\s+", "", normalized)

    # 1) Exact match against rules
    for sticky, parts in STICKY_HEADER_SPLIT_RULES:
        if compact == sticky:
            return parts[0], parts[1]

    # 2) Strip common separators (/ or |) and try rules again
    stripped = re.sub(r"[/|]", "", compact)
    for sticky, parts in STICKY_HEADER_SPLIT_RULES:
        if stripped == sticky:
            return parts[0], parts[1]

    # 3) Heuristic: contains both 投档线 and 排位 keywords
    if "投档线" in stripped and "排位" in stripped:
        if stripped == "投档线投档最低排位":
            return "投档线", "投档最低排位"
        if stripped == "投档线最低排位":
            return "投档线", "最低排位"
        # Generic fallback: "投档线/..." with slash → split by slash
        if "/" in compact:
            parts = [p for p in compact.split("/") if p]
            if len(parts) == 2:
                return parts[0], parts[1]

    return None


def _split_packed_score_rank(value: str) -> Optional[Tuple[str, str]]:
    """
    Split a packed numeric token like "55469531" into ("554", "69531") when plausible.
    Assumption: Gaokao scores are typically 3 digits (200..750), rank is remaining digits.
    """
    normalized = normalize_cell_text(value).translate(AMBIGUOUS_DIGIT_MAP)
    if not normalized or not re.fullmatch(r"\d{5,}", normalized):
        return None

    score_part = normalized[:3]
    rank_part = normalized[3:]
    try:
        score = int(score_part)
        if 200 <= score <= 750 and int(rank_part) >= 0:
            return score_part, rank_part
    except Exception:
        return None
    return None


def _is_score_header(text: str) -> bool:
    header = re.sub(r"\s+", "", normalize_cell_text(text))
    if not header:
        return False
    return "投档线" in header or "最低分" in header or header.endswith("分")


def _is_rank_header(text: str) -> bool:
    header = re.sub(r"\s+", "", normalize_cell_text(text))
    if not header:
        return False
    return "排位" in header or "位次" in header or "排名" in header


def repair_table_structure(table: List[List[str]]) -> Dict[str, Any]:
    if not table:
        return {
            "table": [],
            "corrections": [],
            "suspicious_rows": [],
            "numeric_columns": [],
        }

    repaired = [[normalize_cell_text(cell) for cell in row] for row in table]
    corrections: List[Dict[str, str]] = []

    # Step 0: split sticky headers — scan ALL rows (not just row 0),
    # because GLM-OCR may produce multi-row headers where the real
    # column names sit in row 1 or deeper.
    if repaired:
        split_targets: List[Tuple[int, str, str]] = []
        seen_cols: set = set()
        for row in repaired:
            for col_idx, cell in enumerate(row):
                if col_idx in seen_cols:
                    continue
                split = _split_sticky_header_cell(cell)
                if split:
                    split_targets.append((col_idx, split[0], split[1]))
                    seen_cols.add(col_idx)

        # Apply from right to left to keep indices stable.
        for col_idx, left_header, right_header in reversed(split_targets):
            for row_idx in range(len(repaired)):
                row = repaired[row_idx]
                if col_idx >= len(row):
                    continue

                cell = row[col_idx]
                cell_split = _split_sticky_header_cell(cell)
                if cell_split:
                    # This row has the sticky header — replace with two columns
                    row[col_idx] = left_header
                    row.insert(col_idx + 1, right_header)
                    corrections.append(
                        {
                            "original": cell,
                            "corrected": f"{left_header} | {right_header}",
                            "reason": f"split sticky header at row {row_idx + 1}, column {col_idx + 1}",
                        }
                    )
                else:
                    # Data row — insert empty cell and try to split packed digits
                    row.insert(col_idx + 1, "")
                    packed = _split_packed_score_rank(row[col_idx])
                    if packed and not normalize_cell_text(row[col_idx + 1]):
                        original_value = row[col_idx]
                        row[col_idx], row[col_idx + 1] = packed[0], packed[1]
                        corrections.append(
                            {
                                "original": original_value,
                                "corrected": f"{packed[0]} | {packed[1]}",
                                "reason": (
                                    f"split packed score/rank at row {row_idx + 1}, "
                                    f"columns {col_idx + 1}-{col_idx + 2}"
                                ),
                            }
                        )

    # Step 0.5: If headers are already separated (score column + rank column),
    # split packed digits like "55469531" when rank cell is blank.
    # Scan ALL rows to identify score/rank columns (multi-row header support).
    if repaired and len(repaired) >= 2:
        # Build a map: col_idx -> "score" or "rank" by scanning all rows
        col_types: Dict[int, str] = {}
        for row in repaired:
            for col_idx in range(len(row)):
                if col_idx in col_types:
                    continue
                if _is_score_header(row[col_idx]):
                    col_types[col_idx] = "score"
                elif _is_rank_header(row[col_idx]):
                    col_types[col_idx] = "rank"

        # For each adjacent (score, rank) pair, try to split packed data
        for col_idx in sorted(col_types.keys()):
            if col_types[col_idx] != "score":
                continue
            next_col = col_idx + 1
            if next_col not in col_types or col_types[next_col] != "rank":
                continue

            for row_idx in range(len(repaired)):
                row = repaired[row_idx]
                if next_col >= len(row):
                    continue
                # Skip rows where these columns look like headers
                if _is_score_header(row[col_idx]) or _is_rank_header(row[next_col]):
                    continue
                if normalize_cell_text(row[next_col]):
                    continue
                packed = _split_packed_score_rank(row[col_idx])
                if not packed:
                    continue
                original_value = row[col_idx]
                row[col_idx], row[next_col] = packed[0], packed[1]
                corrections.append(
                    {
                        "original": original_value,
                        "corrected": f"{packed[0]} | {packed[1]}",
                        "reason": (
                            f"split packed score/rank at row {row_idx + 1}, "
                            f"columns {col_idx + 1}-{col_idx + 2}"
                        ),
                    }
                )

    suspicious_rows = set()
    numeric_columns = infer_numeric_columns(repaired)

    for row_index in range(1, len(repaired)):
        row = repaired[row_index]
        blank_numeric_columns = [
            column
            for column in numeric_columns
            if column < len(row) and not normalize_cell_text(row[column])
        ]

        for column in numeric_columns:
            if column >= len(row):
                continue

            current_value = row[column]
            normalized_value = normalize_numeric_text(current_value)
            if current_value and normalized_value != current_value:
                row[column] = normalized_value
                corrections.append(
                    {
                        "original": current_value,
                        "corrected": normalized_value,
                        "reason": f"normalized numeric cell at row {row_index + 1}, column {column + 1}",
                    }
                )

            tokens = extract_numeric_tokens(row[column])
            if len(tokens) <= 1:
                continue

            target_columns = [column]
            for later_column in range(column + 1, len(row)):
                if normalize_cell_text(row[later_column]):
                    if len(target_columns) > 1:
                        break
                    continue
                if later_column in numeric_columns or later_column == column + len(target_columns):
                    target_columns.append(later_column)
                if len(target_columns) == len(tokens):
                    break

            if len(target_columns) == len(tokens) and len(target_columns) > 1:
                original_value = row[column]
                for target_index, token in zip(target_columns, tokens):
                    row[target_index] = token
                corrections.append(
                    {
                        "original": original_value,
                        "corrected": " | ".join(tokens),
                        "reason": (
                            f"split packed numeric values across columns "
                            f"{', '.join(str(item + 1) for item in target_columns)}"
                        ),
                    }
                )

        if any("\n" in normalize_cell_text(cell) for cell in row):
            suspicious_rows.add(row_index)

        filled_values = sum(1 for cell in row if normalize_cell_text(cell))
        if len(row) and filled_values <= max(1, len(row) // 3):
            suspicious_rows.add(row_index)

        blank_numeric_count = sum(
            1 for column in numeric_columns if column < len(row) and not normalize_cell_text(row[column])
        )
        if blank_numeric_count:
            suspicious_rows.add(row_index)

    return {
        "table": repaired,
        "corrections": corrections,
        "suspicious_rows": sorted(suspicious_rows),
        "numeric_columns": numeric_columns,
    }


def summarize_row_issues(table: Sequence[Sequence[str]], suspicious_rows: Sequence[int]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if not table:
        return issues

    headers = table[0]
    for row_index in suspicious_rows:
        if row_index >= len(table):
            continue
        row = table[row_index]
        issue_types = []
        for column, value in enumerate(row):
            text = normalize_cell_text(value)
            if "\n" in text:
                issue_types.append(f"multiline:{headers[column] if column < len(headers) else column}")
            if not text:
                issue_types.append(f"blank:{headers[column] if column < len(headers) else column}")
        issues.append(
            {
                "row_index": row_index,
                "row": row,
                "issues": issue_types or ["structure_uncertain"],
            }
        )
    return issues


def build_table_from_cells(cells: Sequence[Dict[str, Any]]) -> List[List[str]]:
    if not cells:
        return []

    max_row = max(cell["row_end"] for cell in cells) + 1
    max_col = max(cell["col_end"] for cell in cells) + 1
    matrix = [["" for _ in range(max_col)] for _ in range(max_row)]

    for cell in cells:
        row_index = cell["row_start"]
        column_index = cell["col_start"]
        matrix[row_index][column_index] = normalize_cell_text(cell.get("words", ""))

    return matrix


def compact_ocr_context(ocr_result: Dict[str, Any], focus_rows: Optional[Sequence[int]] = None) -> str:
    tables = ocr_result.get("tables_result", [])
    if not tables:
        return ""

    row_filter = set(focus_rows or [])
    lines: List[str] = []
    for table_index, table in enumerate(tables, start=1):
        lines.append(f"table {table_index}:")
        for cell in table.get("body", []):
            row_start = cell.get("row_start")
            if row_filter and row_start not in row_filter:
                continue
            value = normalize_cell_text(cell.get("words", ""))
            if not value:
                continue
            lines.append(
                "  "
                f"r{cell.get('row_start', '?')}c{cell.get('col_start', '?')}="
                f"{value}"
            )
    return "\n".join(lines[:200])
