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


def _split_sticky_header_cell(header: str) -> Optional[Tuple[str, str]]:
    normalized = normalize_cell_text(header)
    if not normalized:
        return None

    compact = re.sub(r"\s+", "", normalized)
    for sticky, parts in STICKY_HEADER_SPLIT_RULES:
        if compact == sticky:
            return parts[0], parts[1]

    # Heuristic: "投档线...排位" with no explicit separator.
    if "投档线" in compact and "排位" in compact and "|" not in compact:
        if compact == "投档线投档最低排位":
            return "投档线", "投档最低排位"
        if compact == "投档线最低排位":
            return "投档线", "最低排位"

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

    # Step 0: split sticky headers first, so later numeric-column inference sees the right columns.
    if repaired and repaired[0]:
        headers = repaired[0]
        split_targets: List[Tuple[int, str, str]] = []
        for index, header in enumerate(headers):
            split = _split_sticky_header_cell(header)
            if split:
                split_targets.append((index, split[0], split[1]))

        # Apply from right to left to keep indices stable.
        for index, left_header, right_header in reversed(split_targets):
            original_header = headers[index]
            headers[index] = left_header
            headers.insert(index + 1, right_header)
            corrections.append(
                {
                    "original": original_header,
                    "corrected": f"{left_header} | {right_header}",
                    "reason": f"split sticky header at column {index + 1}",
                }
            )

            for row_index in range(1, len(repaired)):
                row = repaired[row_index]
                if index >= len(row):
                    continue
                row.insert(index + 1, "")
                packed = _split_packed_score_rank(row[index])
                if packed and not normalize_cell_text(row[index + 1]):
                    original_value = row[index]
                    row[index], row[index + 1] = packed[0], packed[1]
                    corrections.append(
                        {
                            "original": original_value,
                            "corrected": f"{packed[0]} | {packed[1]}",
                            "reason": (
                                f"split packed score/rank at row {row_index + 1}, "
                                f"columns {index + 1}-{index + 2}"
                            ),
                        }
                    )

    # Step 0.5: If headers are already separated (score column + rank column),
    # split packed digits like "55469531" when rank cell is blank.
    if repaired and repaired[0] and len(repaired[0]) >= 2:
        headers = repaired[0]
        for row_index in range(1, len(repaired)):
            row = repaired[row_index]
            for col in range(min(len(headers) - 1, len(row) - 1)):
                if not (_is_score_header(headers[col]) and _is_rank_header(headers[col + 1])):
                    continue
                if normalize_cell_text(row[col + 1]):
                    continue
                packed = _split_packed_score_rank(row[col])
                if not packed:
                    continue
                original_value = row[col]
                row[col], row[col + 1] = packed[0], packed[1]
                corrections.append(
                    {
                        "original": original_value,
                        "corrected": f"{packed[0]} | {packed[1]}",
                        "reason": (
                            f"split packed score/rank at row {row_index + 1}, "
                            f"columns {col + 1}-{col + 2}"
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


def _cell_span_area(cell: Dict[str, Any]) -> int:
    rs = int(cell.get("row_start", 0))
    re = int(cell.get("row_end", rs))
    cs = int(cell.get("col_start", 0))
    ce = int(cell.get("col_end", cs))
    return max(1, re - rs + 1) * max(1, ce - cs + 1)


def build_table_from_cells(cells: Sequence[Dict[str, Any]]) -> List[List[str]]:
    if not cells:
        return []

    max_row = max(cell["row_end"] for cell in cells) + 1
    max_col = max(cell["col_end"] for cell in cells) + 1
    matrix = [["" for _ in range(max_col)] for _ in range(max_row)]

    # 百度合并格只在 (row_start, col_start) 给一份 words；若我们曾按 rowspan 向下复制，
    # 多行会出现相同投档数字，与原书「一格占多行、不逐行重复」不一致。
    # 横向 colspan 也不能铺到右侧，否则表头整行同字会触发 table_splitter 误判多表。
    sorted_cells = sorted(cells, key=_cell_span_area, reverse=True)
    for cell in sorted_cells:
        text = normalize_cell_text(cell.get("words", ""))
        if not text:
            continue
        rs = int(cell["row_start"])
        cs = int(cell["col_start"])
        if rs < max_row and cs < max_col:
            matrix[rs][cs] = text

    return matrix


def _expand_table_row_indices(indices: Sequence[int], margin: int = 2) -> set:
    expanded: set = set()
    for idx in indices:
        for d in range(-margin, margin + 1):
            v = idx + d
            if v >= 0:
                expanded.add(v)
    return expanded


def _cell_row_range(cell: Dict[str, Any]) -> Tuple[int, int]:
    rs = cell.get("row_start")
    if rs is None:
        return (0, 0)
    rs = int(rs)
    re_raw = cell.get("row_end")
    re = int(re_raw) if re_raw is not None else rs
    return (rs, max(rs, re))


def _cell_touches_rows(cell: Dict[str, Any], row_set: set) -> bool:
    if not row_set:
        return True
    rs, re = _cell_row_range(cell)
    return any(r in row_set for r in range(rs, re + 1))


def compact_ocr_context(ocr_result: Dict[str, Any], focus_rows: Optional[Sequence[int]] = None) -> str:
    tables = ocr_result.get("tables_result", [])
    if not tables:
        return ""

    base_rows = set(int(r) for r in (focus_rows or []) if r is not None)
    row_filter = _expand_table_row_indices(sorted(base_rows)) if base_rows else set()
    lines: List[str] = []
    for table_index, table in enumerate(tables, start=1):
        lines.append(f"table {table_index}:")
        for cell in table.get("body", []):
            if row_filter and not _cell_touches_rows(cell, row_filter):
                continue
            value = normalize_cell_text(cell.get("words", ""))
            if not value:
                continue
            rs, re = _cell_row_range(cell)
            cs = int(cell.get("col_start", 0))
            ce_raw = cell.get("col_end")
            ce = int(ce_raw) if ce_raw is not None else cs
            if re > rs or ce > cs:
                span = f"r{rs}-{re}c{cs}-{ce}"
            else:
                span = f"r{rs}c{cs}"
            lines.append(f"  {span}={value}")
    return "\n".join(lines[:500])
