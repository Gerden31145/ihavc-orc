import difflib
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


def _has_cjk(text: str) -> bool:
    """Return True if *text* contains CJK ideographs (meaningful Chinese text)."""
    return bool(re.search(r"[一-鿿]", text))


def normalize_numeric_text(text: str) -> str:
    normalized = normalize_cell_text(text)
    if not normalized:
        return ""
    tokens = extract_numeric_tokens(normalized)
    if not tokens:
        return normalized
    # If the cell contains CJK characters (e.g. "567（男）"), the text is
    # meaningful annotation — don't strip it down to bare digits.
    if _has_cjk(normalized):
        return normalized
    if "\n" in normalized or " " in normalized or "/" in normalized:
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
    Also handles annotated values like "588(男)36108(男)" → ("588(男)", "36108(男)").
    Assumption: Gaokao scores are typically 3 digits (200..750), rank is remaining digits.
    """
    normalized = normalize_cell_text(value)
    if not normalized:
        return None

    # Try annotated packed value first: "588(男)36108(男)"
    # Each segment is a number optionally followed by parenthesized annotation
    segments = re.findall(r"\d+[（(][^）)]*[）)]|\d+", normalized)
    if len(segments) == 2:
        first_num = re.match(r"(\d+)", segments[0])
        if first_num:
            try:
                score = int(first_num.group(1))
                if 200 <= score <= 750:
                    return segments[0], segments[1]
            except ValueError:
                pass

    # Pure digit packed value: "55469531"
    digits_only = normalized.translate(AMBIGUOUS_DIGIT_MAP)
    digits_only = re.sub(r"[^0-9]", "", digits_only)
    if not digits_only or not re.fullmatch(r"\d{5,}", digits_only):
        return None

    score_part = digits_only[:3]
    rank_part = digits_only[3:]
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


def _count_filled(row: Sequence[str]) -> int:
    """Count non-empty cells in a row."""
    return sum(1 for cell in row if normalize_cell_text(cell))


def _norm_cell_key(cell: Any) -> str:
    """Collapse whitespace for header-cell comparison (case/space-insensitive)."""
    return re.sub(r"\s+", "", normalize_cell_text(cell))


def _detect_repeated_header_blocks(row: Sequence[str], min_block: int = 2) -> Tuple[int, List[str]]:
    """
    If *row* is K>=2 repetitions of an n-col block (n >= min_block), return
    (K, first_block). Otherwise return (1, list(row)).

    Used to detect GLM-OCR gluing two side-by-side same-header tables into one
    wide matrix (header = the n-col header repeated K times).
    """
    cells = [normalize_cell_text(c) for c in row]
    total = len(cells)
    if total < min_block * 2:
        return 1, list(cells)
    # Prefer fewer, wider blocks: try K = 2, 3, ... (narrowing n).
    for k in range(2, total // min_block + 1):
        if total % k != 0:
            continue
        n = total // k
        if n < min_block:
            break
        blocks = [cells[i * n:(i + 1) * n] for i in range(k)]
        first_keys = [_norm_cell_key(c) for c in blocks[0]]
        # All blocks must match the first (exact, after normalization — the
        # duplicated header is byte-identical in the OCR output).
        if all(
            first_keys == [_norm_cell_key(c) for c in block]
            for block in blocks[1:]
        ):
            return k, list(blocks[0])
    return 1, list(cells)


def _chunk_is_real(chunk: Sequence[str]) -> bool:
    """
    Decide whether a split-out column chunk represents a real data row vs. an
    OCR line-bleed fragment (e.g. '学)' or '电子信息科学与技术、通信工程)' leaking
    into the adjacent table's column when a long cell wrapped).

    Real entries always carry at least a 编号 plus one more field (or a name plus
    a number), i.e. >= 2 filled cells. Anything with <= 1 filled cell is a
    fragment/bleed and is dropped to avoid corrupting adjacent rows downstream.
    """
    return sum(1 for c in chunk if normalize_cell_text(c)) >= 2


def split_parallel_tables(
    table: List[List[str]],
) -> Tuple[List[List[str]], List[Dict[str, str]]]:
    """
    Detect side-by-side same-header tables glued into one wide matrix by GLM-OCR
    and split them column-major (read the whole left table top-to-bottom, then
    the right table) into a single n-column table.

    Returns (new_table, corrections). If the input is not a parallel layout it is
    returned unchanged with no corrections.
    """
    if not table:
        return table, []

    # Locate the row carrying a repeated-header block (usually row 0; tolerate a
    # leading sparse frame row).
    header_idx: Optional[int] = None
    k, block = 1, []
    for hi, row in enumerate(table):
        kk, blk = _detect_repeated_header_blocks(row)
        if kk >= 2:
            header_idx, k, block = hi, kk, list(blk)
            break

    if header_idx is None:
        return table, []

    n = len(block)
    body = table[header_idx + 1:]
    new_rows: List[List[str]] = [list(block)]
    dropped = 0
    wrap_corrections: List[Dict[str, str]] = []
    for col in range(k):
        # 收集这一列(并排表之一)的所有行 chunk: 块表头 + 数据行
        col_rows: List[List[str]] = [list(block)]
        for row in body:
            chunk = list(row[col * n:(col + 1) * n])
            while len(chunk) < n:
                chunk.append("")
            if not _chunk_is_real(chunk):
                if any(normalize_cell_text(c) for c in chunk):
                    dropped += 1
                continue
            col_rows.append(chunk)
        # 块内部合并换行续行(空序号的名字片段)。在块内做, 避免并排两表 A/B 互相串位。
        merged_block, wcorr = merge_wrap_continuations(col_rows)
        dropped += len(col_rows) - len(merged_block)
        wrap_corrections.extend(wcorr)
        new_rows.extend(merged_block[1:])  # 跳过块表头, 只追加数据行

    corrections: List[Dict[str, str]] = [{
        "original": f"{len(table)} rows x {len(table[0]) if table else 0} cols "
                    f"(K={k} side-by-side same-header tables)",
        "corrected": f"split column-major into {n}-col table, "
                     f"{len(new_rows) - 1} data rows ({dropped} fragment/wrap rows dropped)",
        "reason": "split side-by-side same-header tables into stacked rows",
    }]
    corrections.extend(wrap_corrections)
    return new_rows, corrections


def _name_paren_balance(name: str) -> int:
    """(开括号数) - (闭括号数)。>0: 名字被截断(有未闭合括号); <0: 多余闭括号(续行片段)。"""
    name = name or ""
    open_count = name.count("(") + name.count("（")
    close_count = name.count(")") + name.count("）")
    return open_count - close_count


def _is_name_fragment(name: str) -> bool:
    """是否像换行续行的"名字片段"(而非完整专业名)。
    信号:
      - 闭括号多于开括号(纯尾部, 如 '校区)'、'实验班)');
      - 平衡的括号注释且较短(如 '(广州番禺校区)'、'(中外合作办学)');
      - 极短(<=4)且以右括号/顿号等结尾。
    完整专业名(如 '数学与应用数学(基地班)' 括号平衡且不以 '(' 开头)不会被误判。"""
    name = normalize_cell_text(name)
    if not name:
        return False
    if _name_paren_balance(name) < 0:
        return True
    if name[:1] in "(（" and name[-1:] in ")）" and len(name) <= 14:
        return True
    if len(name) <= 4 and name[-1] in ")），、。；】":
        return True
    return False


def _is_balanced_note(name: str) -> bool:
    """是否为平衡的括号注释(如 '(广州番禺校区)'), 可作为修饰安全追加到完整父名。"""
    name = normalize_cell_text(name)
    return bool(name) and name[:1] in "(（" and name[-1:] in ")）" and _name_paren_balance(name) == 0


def merge_wrap_continuations(
    table: List[List[str]],
) -> Tuple[List[List[str]], List[Dict[str, str]]]:
    """合并换行续行产生的 artifact 行。

    长"招生院校(专业)"在图上折行时, GLM-OCR 会把折下的尾部单独补成一行
    [空序号, 名字尾部片段, ...(数据, 通常为空或与父行重复)]。这种行单独留在表里
    会显示成"只有一个名字碎片"的错位行(用户反馈的"换行文本成了新的一行")。

    本函数只处理**安全**情形, 其余一律不动, 以保证已有识别的正确性:

      (a) 父行名字被截断(有未闭合括号, 如 '木材科学与工程(一、二年级') 且续行是
          名字尾 -> 把尾部并回父行名字, 丢弃续行; 父行数据全空时用续行数据回填。
      (b) 父名已包含该尾部(冗余) -> 丢弃续行。
      (c1) 续行是平衡括号注释(如 '(广州番禺校区)') 且数据与父行一致(同一词条折行)
          -> 注释追加到父名, 丢弃续行。
      (c2) 续行数据与父行不一致(疑似另一条目名字丢失后的残片) -> 仅丢弃, 不误并到
          父行, 避免把别的条目的数据/校区注释错误归到当前条目。

    真实条目(完整或空的名字, 缺序号)与找不到父行的孤儿片段均不触碰。返回 (新表, corrections)。
    """
    corrections: List[Dict[str, str]] = []
    if not table or len(table) < 2:
        return table, corrections

    header = list(table[0])
    body = [list(r) for r in table[1:]]
    drop = [False] * len(body)

    def cell(row: List[str], i: int) -> str:
        return normalize_cell_text(row[i]) if i < len(row) else ""

    for i in range(len(body)):
        row = body[i]
        if cell(row, 0):
            continue  # 序号非空 -> 不是续行
        name_r = cell(row, 1)
        if not _is_name_fragment(name_r):
            continue  # 名字不是片段 -> 可能是真实条目(缺序号), 不动

        # 扫描回溯到最近一个"有序号且未被丢弃"的父行
        parent_idx = None
        for k in range(i - 1, -1, -1):
            if drop[k]:
                continue
            if cell(body[k], 0):
                parent_idx = k
                break
        if parent_idx is None:
            continue  # 页首孤儿(跨页头丢失) -> 不动

        pname = cell(body[parent_idx], 1)
        rdata = [cell(row, c) for c in range(2, len(row))]
        pdata = [cell(body[parent_idx], c) for c in range(2, len(body[parent_idx]))]
        r_has_data = any(rdata)
        # 续行数据是否与父行一致(为空或等于父行): 一致才说明是同一词条折行
        rdata_matches = all((not rd) or (pd and rd == pd) for rd, pd in zip(rdata, pdata))

        # 情形(a): 父名被截断(开括号多) -> 并回尾部
        if _name_paren_balance(pname) > 0 and name_r and name_r not in pname:
            body[parent_idx][1] = pname + name_r
            if not any(pdata) and r_has_data:
                for c in range(2, len(row)):
                    if c < len(body[parent_idx]):
                        body[parent_idx][c] = row[c]
            drop[i] = True
            corrections.append({
                "original": f"续行 '{name_r}' 单独成行",
                "corrected": f"并入上一行名字 -> '{body[parent_idx][1]}'",
                "reason": "合并换行续行(父名被截断, 补全尾部)",
            })
            continue

        # 情形(b): 父名已含该尾部 -> 冗余, 丢弃续行
        if len(name_r) >= 2 and name_r in pname:
            drop[i] = True
            corrections.append({
                "original": f"续行 '{name_r}' 单独成行",
                "corrected": "丢弃(父名已包含该尾部, 冗余)",
                "reason": "合并换行续行(冗余 artifact)",
            })
            continue

        # 情形(c1): 平衡括号注释 + 数据与父行一致(同一词条折行) -> 追加注释到父名
        if rdata_matches and _is_balanced_note(name_r) and name_r not in pname:
            body[parent_idx][1] = pname + name_r
            drop[i] = True
            corrections.append({
                "original": f"续行 '{name_r}' 单独成行",
                "corrected": f"追加注释到上一行名字 -> '{body[parent_idx][1]}'",
                "reason": "合并换行续行(同条折行, 追加修饰注释)",
            })
            continue

        # 情形(c2): 数据不一致 -> 疑似另一条目名字丢失后的残片, 仅丢弃不误并
        drop[i] = True
        corrections.append({
            "original": f"续行 '{name_r}' 单独成行",
            "corrected": "丢弃(数据与父行不一致, 疑似残片, 不误并)",
            "reason": "合并换行续行(丢弃不可归属残片)",
        })

    if not any(drop):
        return table, corrections

    new_body = [r for r, d in zip(body, drop) if not d]
    return [header] + new_body, corrections


def _flatten_multirow_headers(table: List[List[str]], corrections: List[Dict[str, str]]) -> List[List[str]]:
    """
    Detect and remove GLM-OCR outer frame rows.

    GLM-OCR returns tables where the outer frame label (e.g. "本科") sits
    in row[0] with mostly empty cells, while the real column names are in
    row[1].  This simply drops the sparse row[0] and promotes row[1] to header.

    Detection heuristic:
      - row[0] has ≤ 50% filled cells
      - row[1] has ≥ 67% filled cells
    """
    if len(table) < 2:
        return table

    row0 = table[0]
    row1 = table[1]
    row0_total = max(len(row0), 1)
    row1_total = max(len(row1), 1)
    row0_filled = _count_filled(row0)
    row1_filled = _count_filled(row1)

    # row[0] mostly empty, row[1] mostly full → drop row[0]
    if row0_filled > row0_total // 2 or row1_filled < row1_total * 2 // 3:
        return table

    corrections.append({
        "original": str(row0),
        "corrected": "dropped",
        "reason": "removed sparse outer frame row, promoted row[1] to header",
    })

    return table[1:]


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

    # Step -1: flatten multi-row headers (GLM-OCR outer frame + real headers)
    repaired = _flatten_multirow_headers(repaired, corrections)

    # Save original header (before Step 0 modifies it) for Step 2 matching.
    # Repeated headers in data will match this pre-split version, not the
    # post-split header — which is exactly what we need for reliable detection.
    original_header: List[str] = (
        [normalize_cell_text(c) for c in repaired[0]] if repaired else []
    )

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

            # Detect multi-token BEFORE normalizing — normalization may
            # drop tokens separated by "/" (e.g. "554/69531" → "554").
            tokens = extract_numeric_tokens(current_value)

            if len(tokens) > 1:
                # Split by separator and keep original segments (preserving
                # text annotations like "567（男）" that extract_numeric_tokens
                # would strip to bare "567").
                raw_segments = [
                    s for s in re.split(r"[\s\n/]+", normalize_cell_text(current_value)) if s
                ]

                # Multi-token: try to distribute across columns first
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
                    # Prefer raw segments when they align with numeric tokens
                    # so that text like "（男）" is preserved.
                    values = raw_segments if len(raw_segments) == len(tokens) else tokens
                    for target_index, val in zip(target_columns, values):
                        row[target_index] = val
                    corrections.append(
                        {
                            "original": current_value,
                            "corrected": " | ".join(values),
                            "reason": (
                                f"split packed numeric values across columns "
                                f"{', '.join(str(item + 1) for item in target_columns)}"
                            ),
                        }
                    )
                    continue
                # Cannot distribute — fall through to normalize as single cell

            # Single token (or undistributable multi-token): safe to normalize
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

    # Step 2: remove repeated header rows within data
    # GLM-OCR may produce tables where (sparse row + header row) reappears
    # in the middle of data.  Use SET-based comparison (ignoring column
    # alignment) because Step 0 may have inserted columns that shift data.
    if len(repaired) >= 3 and original_header:
        orig_values = set(
            normalize_cell_text(c) for c in original_header
            if normalize_cell_text(c)
        )
        if orig_values:
            rows_to_remove: List[int] = []
            for row_idx in range(1, len(repaired)):
                row = repaired[row_idx]
                row_values = set(
                    normalize_cell_text(c) for c in row
                    if normalize_cell_text(c)
                )
                if not row_values:
                    continue
                overlap = len(orig_values & row_values) / len(orig_values)
                if overlap >= 0.7:
                    # Also remove preceding sparse row (outer frame label)
                    if row_idx > 1:
                        prev = repaired[row_idx - 1]
                        if _count_filled(prev) < max(len(prev), 1) // 2:
                            rows_to_remove.append(row_idx - 1)
                    rows_to_remove.append(row_idx)

            if rows_to_remove:
                for idx in reversed(sorted(set(rows_to_remove))):
                    removed = repaired.pop(idx)
                    corrections.append({
                        "original": str(removed),
                        "corrected": "removed",
                        "reason": f"removed repeated header row at row {idx + 1}",
                    })

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
