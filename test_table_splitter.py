#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试表格拆分功能"""

from table_splitter import detect_repeated_headers, split_table_by_repeated_headers, merge_split_results


def test_detect_repeated_headers():
    """测试表头重复检测"""
    print("测试1: 正常表头（无重复）")
    headers1 = ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费"]
    is_repeated, repeat_count = detect_repeated_headers(headers1)
    print(f"结果: is_repeated={is_repeated}, repeat_count={repeat_count}")
    assert not is_repeated
    print("[OK] Passed\n")

    print("测试2: 重复表头（2次重复）")
    headers2 = ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费",
                "编号", "招生院校（专业）", "计划", "选科", "学制", "学费"]
    is_repeated, repeat_count = detect_repeated_headers(headers2)
    print(f"结果: is_repeated={is_repeated}, repeat_count={repeat_count}")
    assert is_repeated and repeat_count == 2
    print("[OK] Passed\n")

    print("测试3: 重复表头（3次重复）")
    headers3 = ["A", "B", "C", "A", "B", "C", "A", "B", "C"]
    is_repeated, repeat_count = detect_repeated_headers(headers3)
    print(f"结果: is_repeated={is_repeated}, repeat_count={repeat_count}")
    assert is_repeated and repeat_count == 3
    print("[OK] Passed\n")

    print("测试4: 不完全重复（应该检测为不重复）")
    headers4 = ["A", "B", "C", "A", "X", "C"]  # 中间有不同
    is_repeated, repeat_count = detect_repeated_headers(headers4)
    print(f"结果: is_repeated={is_repeated}, repeat_count={repeat_count}")
    assert not is_repeated
    print("[OK] Passed\n")


def test_split_table():
    """测试表格拆分"""
    print("测试5: 拆分重复表头表格")

    # 模拟一个包含两个表格的OCR结果（并排的表格被合并）
    table_data = [
        ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费", "编号", "招生院校（专业）", "计划", "选科", "学制", "学费"],
        ["01", "金融学", "3", "不限", "4", "25000", "07", "电子商务", "2", "不限", "4", "25000"],
        ["02", "会计学", "5", "不限", "4", "26000", "08", "旅游管理", "2", "不限", "4", "25000"],
    ]

    print(f"原始表格: {len(table_data)} 行 x {len(table_data[0])} 列")
    print(f"表头: {table_data[0]}")

    split_tables = split_table_by_repeated_headers(table_data)

    print(f"\n拆分结果: {len(split_tables)} 个表格")
    for i, table in enumerate(split_tables):
        print(f"\n表格 {i + 1}: {len(table)} 行 x {len(table[0])} 列")
        print(f"表头: {table[0]}")
        print(f"数据行示例: {table[1] if len(table) > 1 else '无'}")

    assert len(split_tables) == 2
    assert len(split_tables[0][0]) == 6  # 每个表格应该有6列
    assert len(split_tables[1][0]) == 6
    print("[OK] Passed\n")


def test_merge_split_results():
    """测试结果合并"""
    print("测试6: 合并拆分表格的处理结果")

    # 模拟两个表格的增强结果
    result1 = {
        "enhanced_table": [
            ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费"],
            ["01", "金融学", "3", "不限", "4", "25000"],
            ["02", "会计学", "5", "不限", "4", "26000"],
        ],
        "corrections": [
            {"original": "O1", "corrected": "01", "reason": "纠正数字识别错误"}
        ],
        "table_structure": {
            "headers": ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费"],
            "data_types": ["string", "string", "integer", "string", "integer", "integer"],
            "estimated_columns": 6
        }
    }

    result2 = {
        "enhanced_table": [
            ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费"],
            ["07", "电子商务", "2", "不限", "4", "25000"],
            ["08", "旅游管理", "2", "不限", "4", "25000"],
        ],
        "corrections": [
            {"original": "O7", "corrected": "07", "reason": "纠正数字识别错误"}
        ],
        "table_structure": {
            "headers": ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费"],
            "data_types": ["string", "string", "integer", "string", "integer", "integer"],
            "estimated_columns": 6
        }
    }

    merged = merge_split_results([result1, result2])

    print(f"合并后的表格: {len(merged['enhanced_table'])} 行 x {len(merged['enhanced_table'][0])} 列")
    print(f"合并后的corrections数量: {len(merged['corrections'])}")
    print(f"拆分信息: {merged['split_info']}")

    assert len(merged["enhanced_table"]) == 3  # 应该有3行（包括表头）
    assert len(merged["enhanced_table"][0]) == 12  # 应该有12列（6+6）
    assert len(merged["corrections"]) == 2  # 应该有2个修正记录
    assert merged["split_info"]["was_split"] == True
    assert merged["split_info"]["table_count"] == 2

    print("[OK] Passed\n")


def test_no_split_needed():
    """测试不需要拆分的情况"""
    print("测试7: 无需拆分的表格")

    table_data = [
        ["编号", "招生院校（专业）", "计划", "选科", "学制", "学费"],
        ["01", "金融学", "3", "不限", "4", "25000"],
        ["02", "会计学", "5", "不限", "4", "26000"],
    ]

    split_tables = split_table_by_repeated_headers(table_data)

    print(f"结果: {len(split_tables)} 个表格")
    assert len(split_tables) == 1
    assert split_tables[0] == table_data
    print("[OK] Passed\n")


if __name__ == "__main__":
    print("=" * 60)
    print("开始测试表格拆分功能")
    print("=" * 60 + "\n")

    try:
        test_detect_repeated_headers()
        test_split_table()
        test_merge_split_results()
        test_no_split_needed()

        print("=" * 60)
        print("[SUCCESS] All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n[FAILED] Test error: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n[ERROR] Exception occurred: {e}")
        import traceback
        traceback.print_exc()
