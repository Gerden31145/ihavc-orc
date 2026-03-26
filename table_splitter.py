import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


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

    # 尝试找到重复模式
    # 从最小可能的模式长度开始检查
    max_pattern_length = len(headers) // 2

    for pattern_length in range(1, max_pattern_length + 1):
        # 检查是否能被整除
        if len(headers) % pattern_length != 0:
            continue

        # 提取第一个模式
        pattern = headers[:pattern_length]

        # 检查是否重复
        is_repeated = True
        repeat_count = len(headers) // pattern_length

        for i in range(1, repeat_count):
            start = i * pattern_length
            end = start + pattern_length
            current_segment = headers[start:end]

            # 比较每个字段
            for j in range(pattern_length):
                if pattern[j] != current_segment[j]:
                    is_repeated = False
                    break

            if not is_repeated:
                break

        if is_repeated:
            logger.info(f"检测到表头重复模式，模式长度: {pattern_length}, 重复次数: {repeat_count}")
            logger.info(f"模式: {pattern}")
            return True, repeat_count

    return False, 1


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
