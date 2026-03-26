#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""端到端测试：OCR识别重复表头表格的完整流程"""

import json
from table_splitter import split_table_by_repeated_headers, merge_split_results


def test_real_world_scenario():
    """模拟真实的OCR场景：两个并排的表格被识别为一个表格"""
    print("模拟真实OCR场景：两个并排的表格")
    print("=" * 60)

    # 模拟OCR返回的结果（两个表格被合并）
    mock_ocr_result = {
        "tables_result": [
            {
                "body": [
                    # 表头
                    {"words": "编号", "row_start": 0, "col_start": 0, "row_end": 0, "col_end": 0},
                    {"words": "招生院校", "row_start": 0, "col_start": 1, "row_end": 0, "col_end": 1},
                    {"words": "计划", "row_start": 0, "col_start": 2, "row_end": 0, "col_end": 2},
                    {"words": "编号", "row_start": 0, "col_start": 3, "row_end": 0, "col_end": 3},
                    {"words": "招生院校", "row_start": 0, "col_start": 4, "row_end": 0, "col_end": 4},
                    {"words": "计划", "row_start": 0, "col_start": 5, "row_end": 0, "col_end": 5},

                    # 数据行1
                    {"words": "01", "row_start": 1, "col_start": 0, "row_end": 1, "col_end": 0},
                    {"words": "北京大学", "row_start": 1, "col_start": 1, "row_end": 1, "col_end": 1},
                    {"words": "10", "row_start": 1, "col_start": 2, "row_end": 1, "col_end": 2},
                    {"words": "02", "row_start": 1, "col_start": 3, "row_end": 1, "col_end": 3},
                    {"words": "清华大学", "row_start": 1, "col_start": 4, "row_end": 1, "col_end": 4},
                    {"words": "5", "row_start": 1, "col_start": 5, "row_end": 1, "col_end": 5},

                    # 数据行2
                    {"words": "03", "row_start": 2, "col_start": 0, "row_end": 2, "col_end": 0},
                    {"words": "复旦大学", "row_start": 2, "col_start": 1, "row_end": 2, "col_end": 1},
                    {"words": "8", "row_start": 2, "col_start": 2, "row_end": 2, "col_end": 2},
                    {"words": "04", "row_start": 2, "col_start": 3, "row_end": 2, "col_end": 3},
                    {"words": "上海交大", "row_start": 2, "col_start": 4, "row_end": 2, "col_end": 4},
                    {"words": "6", "row_start": 2, "col_start": 5, "row_end": 2, "col_end": 5},
                ]
            }
        ]
    }

    # 处理OCR结果，转换为二维表格
    from ocr_api import process_single_table

    cells = mock_ocr_result["tables_result"][0]["body"]
    data_matrix = process_single_table(cells)

    print(f"\n原始OCR结果:")
    print(f"表格大小: {len(data_matrix)} 行 x {len(data_matrix[0])} 列")
    print(f"表头: {data_matrix[0]}")
    print(f"数据行数: {len(data_matrix) - 1}")

    # 拆分表格
    split_tables = split_table_by_repeated_headers(data_matrix)

    print(f"\n拆分结果:")
    print(f"拆分数量: {len(split_tables)} 个表格")

    for i, table in enumerate(split_tables):
        print(f"\n表格 {i + 1}:")
        print(f"  大小: {len(table)} 行 x {len(table[0])} 列")
        print(f"  表头: {table[0]}")
        for j, row in enumerate(table[1:], 1):
            print(f"  行 {j}: {row}")

    # 模拟LLM增强结果
    def mock_llm_enhance(table_data, ocr_result):
        """模拟LLM增强处理"""
        return {
            "enhanced_table": table_data,  # 这里简单返回原始数据
            "corrections": [],
            "table_structure": {
                "headers": table_data[0] if table_data else [],
                "data_types": [],
                "estimated_columns": len(table_data[0]) if table_data else 0
            }
        }

    # 对每个表格调用模拟的LLM增强
    print("\n模拟LLM增强处理...")
    split_results = []
    for i, split_table in enumerate(split_tables):
        print(f"处理表格 {i + 1}/{len(split_tables)}")
        result = mock_llm_enhance(split_table, mock_ocr_result)
        split_results.append(result)

    # 合并结果
    merged_result = merge_split_results(split_results)

    print(f"\n最终合并结果:")
    print(f"表格大小: {len(merged_result['enhanced_table'])} 行 x {len(merged_result['enhanced_table'][0])} 列")
    print(f"表头: {merged_result['enhanced_table'][0]}")
    for i, row in enumerate(merged_result['enhanced_table'][1:], 1):
        print(f"行 {i}: {row}")

    print(f"\n拆分信息:")
    print(f"  是否被拆分: {merged_result['split_info']['was_split']}")
    print(f"  拆分数量: {merged_result['split_info']['table_count']}")
    print(f"  原始列数: {merged_result['split_info']['original_columns']}")

    # 验证结果
    assert len(split_tables) == 2, "应该拆分为2个表格"
    assert len(merged_result['enhanced_table'][0]) == 6, "合并后应该有6列"
    assert merged_result['split_info']['was_split'] == True, "应该标记为已拆分"

    print("\n[OK] 端到端测试通过!")
    return merged_result


def test_no_split_scenario():
    """测试不需要拆分的场景"""
    print("\n\n测试不拆分场景：单个表格")
    print("=" * 60)

    # 模拟单个表格的OCR结果
    mock_ocr_result = {
        "tables_result": [
            {
                "body": [
                    # 表头
                    {"words": "编号", "row_start": 0, "col_start": 0, "row_end": 0, "col_end": 0},
                    {"words": "招生院校", "row_start": 0, "col_start": 1, "row_end": 0, "col_end": 1},
                    {"words": "计划", "row_start": 0, "col_start": 2, "row_end": 0, "col_end": 2},

                    # 数据行1
                    {"words": "01", "row_start": 1, "col_start": 0, "row_end": 1, "col_end": 0},
                    {"words": "北京大学", "row_start": 1, "col_start": 1, "row_end": 1, "col_end": 1},
                    {"words": "10", "row_start": 1, "col_start": 2, "row_end": 1, "col_end": 2},

                    # 数据行2
                    {"words": "02", "row_start": 2, "col_start": 0, "row_end": 2, "col_end": 0},
                    {"words": "清华大学", "row_start": 2, "col_start": 1, "row_end": 2, "col_end": 1},
                    {"words": "5", "row_start": 2, "col_start": 2, "row_end": 2, "col_end": 2},
                ]
            }
        ]
    }

    from ocr_api import process_single_table

    cells = mock_ocr_result["tables_result"][0]["body"]
    data_matrix = process_single_table(cells)

    print(f"原始表格: {len(data_matrix)} 行 x {len(data_matrix[0])} 列")
    print(f"表头: {data_matrix[0]}")

    # 尝试拆分
    split_tables = split_table_by_repeated_headers(data_matrix)

    print(f"拆分结果: {len(split_tables)} 个表格")
    assert len(split_tables) == 1, "不应该拆分"
    assert split_tables[0] == data_matrix, "应该保持原样"

    print("[OK] 不拆分测试通过!")


if __name__ == "__main__":
    print("\n开始端到端集成测试\n")

    try:
        test_real_world_scenario()
        test_no_split_scenario()

        print("\n" + "=" * 60)
        print("[SUCCESS] All integration tests passed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAILED] Test error: {e}")
        import traceback
        traceback.print_exc()
