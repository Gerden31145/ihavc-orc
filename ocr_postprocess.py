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
    joined = "".join(tokens)
    return len(joined) >= max(1, len(re.sub(r"\s+", "", normalize_cell_text(text))) // 2)


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


def normalize_numeric_text(text: str) -> str:
    normalized = normalize_cell_text(text)
    if not normalized:
        return ""
    tokens = extract_numeric_tokens(normalized)
    if not tokens:
        return normalized
    if "\n" in normalized or " " in normalized:
        return "\n".join(tokens)
    return tokens[0]


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
