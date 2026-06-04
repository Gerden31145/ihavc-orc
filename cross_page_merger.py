"""跨页表格合并模块：将多页 OCR 结果智能合并为完整表格。"""

import difflib
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 表头中已知的 OCR 噪声后缀（跨页文字被 OCR 拼进表头）
_KNOWN_HEADER_NOISE = ["录取)", "就读)", "考生)"]


def _normalize(s: str) -> str:
    return "".join(s.split()).lower()


def _clean_cell(cell: str) -> str:
    """去除单元格中被 OCR 错误拼入的已知噪声后缀。"""
    for noise in _KNOWN_HEADER_NOISE:
        if cell.endswith(noise):
            return cell[: -len(noise)]
    return cell


def _is_sparse_data_row(row: List[str], max_filled: int = 2) -> bool:
    """Return True if *row* has ≤ *max_filled* non-empty cells (likely overflow text)."""
    filled = sum(1 for cell in row if cell.strip())
    return 0 < filled <= max_filled


def _is_header_row(row: List[str], reference: List[str], threshold: float = 0.7) -> bool:
    """判断一行是否为表头行（与 clean 后的 reference 模糊匹配）。"""
    if len(row) != len(reference):
        return False
    scores = []
    for a, b in zip(row, reference):
        na = _normalize(_clean_cell(a))
        nb = _normalize(b)
        if not na and not nb:
            scores.append(1.0)
            continue
        if not na or not nb:
            scores.append(0.0)
            continue
        scores.append(difflib.SequenceMatcher(None, na, nb).ratio())
    avg = sum(scores) / len(scores) if scores else 0.0
    return avg >= threshold


def _extract_overflow(row: List[str], clean_ref: List[str]) -> List[str]:
    """
    对比表头行与 clean reference，提取每个单元格中多出的后缀文本。
    """
    overflows: List[str] = []
    for cand, ref in zip(row, clean_ref):
        nc = _normalize(cand)
        nr = _normalize(ref)
        if not nr or not nc:
            overflows.append("")
            continue
        # 用原始 candidate 做 normalized 前缀匹配
        if nc.startswith(nr) and len(nc) > len(nr):
            # 用原始 cand 切割，按 ref 原始长度
            if len(cand) > len(ref):
                overflows.append(cand[len(ref):])
            else:
                overflows.append("")
        else:
            overflows.append("")
    return overflows


def merge_cross_page_tables(
    page_matrices: List[Optional[List[List[str]]]],
    fuzzy_threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    将多页 OCR 矩阵按顺序合并为一个完整表格。

    策略：扫描所有页所有行，任何像表头的行都过滤掉，并提取其中的溢出文本拼回上一行。
    """
    total_pages = len(page_matrices)
    pages_processed = 0
    pages_failed = 0
    warnings: List[str] = []

    # 1. 从第一个有效矩阵取 clean 后的表头作为全局 reference
    clean_ref: List[str] = []
    col_count = 0
    all_rows: List[List[str]] = []

    for matrix in page_matrices:
        if matrix is None or not matrix:
            pages_failed += 1
            continue
        pages_processed += 1
        if not clean_ref:
            clean_ref = [_clean_cell(c) for c in matrix[0]]
            col_count = len(clean_ref)

    if not clean_ref:
        return {
            "headers": [],
            "rows": [],
            "merge_diagnostics": {
                "total_pages": total_pages,
                "pages_processed": 0,
                "pages_failed": pages_failed,
                "page_classifications": [],
                "warnings": ["所有页面识别均失败"],
            },
        }

    # 2. 遍历所有页所有行
    header_count = 0
    for page_idx, matrix in enumerate(page_matrices):
        if matrix is None or not matrix:
            continue
        is_first_data_of_page = True
        for row in matrix:
            # 统一列数
            norm = list(row[:col_count])
            while len(norm) < col_count:
                norm.append("")

            if _is_header_row(norm, clean_ref, fuzzy_threshold):
                header_count += 1
                # 提取溢出文本，拼回上一行
                overflows = _extract_overflow(norm, clean_ref)
                overflow_parts = [s for s in overflows if s.strip()]
                if overflow_parts and all_rows:
                    prev = list(all_rows[-1])
                    for j, suf in enumerate(overflows):
                        if j < len(prev) and suf.strip():
                            prev[j] = prev[j] + suf
                    all_rows[-1] = prev
                    logger.info(f"表头行溢出: {overflow_parts} → 合并到上一行")
                # 跳过表头行本身
                is_first_data_of_page = True
            elif (
                page_idx > 0
                and _is_sparse_data_row(norm)
                and all_rows
            ):
                # 跨页数据行溢出：稀疏行（只有1-2个单元格有文本），
                # 说明是上一行文本的续行（跨行溢出），拼接到上一行。
                # 不仅限于页首行，页中间的稀疏行也可能是 OCR 拆分导致的溢出。
                overflow_text = "".join(c for c in norm if c.strip())
                prev = list(all_rows[-1])
                # 找上一行中最长的非空单元格作为拼接目标
                target_j = max(
                    ((j, len(prev[j].strip())) for j in range(len(prev)) if prev[j].strip()),
                    key=lambda x: x[1],
                    default=(1, 0),
                )[0]
                prev[target_j] = prev[target_j] + overflow_text
                all_rows[-1] = prev
                logger.info(f"跨页数据行溢出: '{overflow_text}' → 合并到上一行列{target_j}")
                is_first_data_of_page = False
            else:
                all_rows.append(norm)
                is_first_data_of_page = False

    logger.info(f"共过滤 {header_count} 个表头行, 保留 {len(all_rows)} 个数据行")

    return {
        "headers": clean_ref,
        "rows": all_rows,
        "merge_diagnostics": {
            "total_pages": total_pages,
            "pages_processed": pages_processed,
            "pages_failed": pages_failed,
            "headers_filtered": header_count,
            "warnings": warnings,
        },
    }
