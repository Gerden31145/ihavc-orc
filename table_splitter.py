import logging
import re
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def _normalize_header_token(text: str) -> str:
    value = "" if text is None else str(text)
    value = re.sub(r"\s+", "", value.strip())
    return value.casefold()


def detect_repeated_headers(headers: List[str]) -> Tuple[bool, int]:
    """
    检测表头是否存在重复模式

    Args:
        headers: 表头列表

    Returns:
        (is_repeated, repeat_count): 是否重复, 重复次数
    """
    if not headers or len(headers) < 2:
        return False, 1

    normalized = [_normalize_header_token(h) for h in headers]
    max_pattern_length = len(normalized) // 2

    for pattern_length in range(1, max_pattern_length + 1):
        if len(normalized) % pattern_length != 0:
            continue

        pattern = normalized[:pattern_length]
        is_repeated = True
        repeat_count = len(normalized) // pattern_length

        for i in range(1, repeat_count):
            start = i * pattern_length
            end = start + pattern_length
            current_segment = normalized[start:end]

            for j in range(pattern_length):
                if pattern[j] != current_segment[j]:
                    is_repeated = False
                    break

            if not is_repeated:
                break

        if is_repeated and repeat_count >= 2:
            logger.info(
                "检测到表头重复模式，模式长度: %s, 重复次数: %s, 模式: %s",
                pattern_length,
                repeat_count,
                headers[:pattern_length],
            )
            return True, repeat_count

    return False, 1


def compress_repeated_header_columns(table: List[List[str]]) -> List[List[str]]:
    """横向重复表头时只保留第一段列（用于导出/API 响应）。"""
    if not table or not table[0]:
        return table

    header_row = table[0]
    is_repeated, repeat_count = detect_repeated_headers(header_row)
    if not is_repeated or repeat_count <= 1:
        return table

    pattern_len = len(header_row) // repeat_count
    compressed = [header_row[:pattern_len]]
    for row in table[1:]:
        if len(row) >= pattern_len:
            compressed.append(row[:pattern_len])
        else:
            compressed.append(row + [""] * (pattern_len - len(row)))
    return compressed


def _joined_header_tokens(cells: List[str]) -> str:
    return "".join(_normalize_header_token(c) for c in cells if _normalize_header_token(c))


def row_looks_like_score_header_labels(row: List[str]) -> bool:
    """仅根据单元格文案判断是否为高考表头行（不依赖已有 headers）。"""
    if not row:
        return False
    label_hits = 0
    for cell in row:
        text = "" if cell is None else str(cell).strip()
        if not text or len(text) > 24:
            continue
        if any(k in text for k in ("院校", "专业", "投档", "录取", "排位", "最低分")):
            label_hits += 1
    if label_hits < 3:
        return False
    numeric_cells = sum(
        1 for cell in row if re.fullmatch(r"\d{3,}", re.sub(r"\s+", "", str(cell or "")))
    )
    return numeric_cells <= 1


def row_looks_like_header_row(row: List[str], headers: List[str]) -> bool:
    """判断一行是否为与已知表头重复的嵌入表头行。"""
    ref = [_normalize_header_token(h) for h in headers if _normalize_header_token(h)]
    if not ref or not row:
        return False

    cells = [_normalize_header_token(c) for c in row]
    compare_len = min(len(ref), len(cells))
    if compare_len > 0:
        matched = sum(1 for i in range(compare_len) if ref[i] == cells[i])
        if matched / len(ref) >= 0.75:
            return True

    ref_joined = _joined_header_tokens(headers)
    row_joined = _joined_header_tokens(row)
    if row_joined and ref_joined:
        if row_joined == ref_joined:
            return True
        shorter = min(len(row_joined), len(ref_joined))
        longer = max(len(row_joined), len(ref_joined))
        if longer and shorter / longer >= 0.85 and (
            ref_joined in row_joined or row_joined in ref_joined
        ):
            return True

    return False


def ensure_table_has_header_row(table: List[List[str]]) -> List[List[str]]:
    """若首行无有效表头，尝试将首个表头样式的行提升为表头。"""
    if not table:
        return table
    if any(_normalize_header_token(cell) for cell in table[0]):
        return table
    for index in range(1, min(len(table), 4)):
        if row_looks_like_score_header_labels(table[index]):
            logger.info("将第 %s 行提升为表头", index + 1)
            return [table[index]] + table[1:index] + table[index + 1 :]
    return table


def strip_duplicate_header_rows(headers: List[str], rows: List[List[str]]) -> List[List[str]]:
    if not headers:
        return rows
    return [row for row in rows if not row_looks_like_header_row(row, headers)]


def split_table_by_repeated_headers(table_data: List[List[str]]) -> List[List[List[str]]]:
    """
    根据重复表头拆分表格

    Args:
        table_data: 二维表格数据

    Returns:
        拆分后的表格列表
    """
    if not table_data or not table_data[0]:
        logger.warning("表格数据为空，无法拆分")
        return [table_data] if table_data else []

    headers = table_data[0]

    # 检测表头重复
    is_repeated, repeat_count = detect_repeated_headers(headers)

    if not is_repeated or repeat_count == 1:
        logger.info("未检测到表头重复，无需拆分")
        return [table_data]

    # 计算每个表格的列数
    columns_per_table = len(headers) // repeat_count

    logger.info(f"开始拆分表格，总共 {len(headers)} 列，每个子表格 {columns_per_table} 列")

    # 拆分表格
    split_tables = []

    for table_idx in range(repeat_count):
        # 计算当前表格的列范围
        start_col = table_idx * columns_per_table
        end_col = start_col + columns_per_table

        # 提取当前表格的所有行
        current_table = []
        for row in table_data:
            # 处理行长度不足的情况
            if len(row) >= end_col:
                current_table.append(row[start_col:end_col])
            elif len(row) >= start_col:
                # 如果行长度不足，用空字符串填充
                padded_row = row[start_col:] + [""] * (end_col - len(row))
                current_table.append(padded_row)
            else:
                # 如果行太短，填充整行
                current_table.append([""] * columns_per_table)

        split_tables.append(current_table)
        logger.info(f"拆分表格 {table_idx + 1}: {len(current_table)} 行 x {columns_per_table} 列")

    return split_tables


def merge_split_results(split_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    合并多个拆分表格的LLM增强结果

    Args:
        split_results: 每个拆分表格的增强结果列表

    Returns:
        合并后的结果
    """
    if not split_results:
        return {
            "enhanced_table": [],
            "corrections": [],
            "table_structure": {},
            "split_info": {
                "was_split": False,
                "table_count": 0
            }
        }

    if len(split_results) == 1:
        result = split_results[0].copy()
        result["split_info"] = {
            "was_split": False,
            "table_count": 1
        }
        return result

    # 合并增强后的表格数据
    merged_table = []

    # 获取第一个表格作为基础
    first_table = split_results[0]["enhanced_table"]

    # 如果有多个表格，按行合并
    # 假设所有表格行数相同，按行拼接
    if first_table:
        max_rows = max(len(result["enhanced_table"]) for result in split_results)

        for row_idx in range(max_rows):
            merged_row = []
            for table_result in split_results:
                table = table_result["enhanced_table"]
                if row_idx < len(table):
                    merged_row.extend(table[row_idx])
                else:
                    # 如果某表格行数不足，填充空值
                    if row_idx == 0:  # 表头行
                        merged_row.extend([""] * len(table[0]) if table else [])
                    else:
                        merged_row.extend([""] * len(table[0]) if table else [])

            merged_table.append(merged_row)

    # 合并corrections
    merged_corrections = []
    for table_result in split_results:
        corrections = table_result.get("corrections", [])
        merged_corrections.extend(corrections)

    # 合并table_structure
    first_structure = split_results[0].get("table_structure", {})
    merged_structure = {
        "headers": merged_table[0] if merged_table else [],
        "data_types": [],  # 数据类型需要重新推断
        "estimated_columns": len(merged_table[0]) if merged_table else 0,
        "split_table_headers": [result.get("table_structure", {}).get("headers", [])
                               for result in split_results]
    }

    return {
        "enhanced_table": merged_table,
        "corrections": merged_corrections,
        "table_structure": merged_structure,
        "split_info": {
            "was_split": True,
            "table_count": len(split_results),
            "original_columns": len(merged_table[0]) if merged_table else 0
        }
    }
