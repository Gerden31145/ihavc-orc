from ocr_postprocess import build_table_from_cells, compact_ocr_context, repair_table_structure


def test_split_packed_numeric_values_across_blank_numeric_columns():
    table = [
        ["院校", "计划", "投档线", "位次"],
        ["江南大学", "14", "614\n17935", ""],
    ]

    repaired = repair_table_structure(table)

    assert repaired["table"][1][2] == "614"
    assert repaired["table"][1][3] == "17935"
    assert repaired["corrections"]


def test_normalize_ambiguous_numeric_characters():
    table = [
        ["专业", "投档线"],
        ["人工智能", "6I4"],
    ]

    repaired = repair_table_structure(table)

    assert repaired["table"][1][1] == "614"


def test_split_sticky_header_and_packed_score_rank_digits():
    table = [
        ["院校", "投档线投档最低排位"],
        ["某大学", "55469531"],
    ]

    repaired = repair_table_structure(table)

    assert repaired["table"][0] == ["院校", "投档线", "投档最低排位"]
    assert repaired["table"][1][1] == "554"
    assert repaired["table"][1][2] == "69531"
    assert repaired["corrections"]


def test_split_sticky_header_with_newline_and_packed_digits():
    table = [
        ["院校", "投档线投档最低排\n位"],
        ["某大学", "55469531"],
    ]

    repaired = repair_table_structure(table)
    assert repaired["table"][0] == ["院校", "投档线", "投档最低排位"]
    assert repaired["table"][1][1] == "554"
    assert repaired["table"][1][2] == "69531"


def test_build_table_from_cells_rowspan_only_writes_anchor():
    cells = [
        {"words": "代码", "row_start": 0, "col_start": 0, "row_end": 0, "col_end": 0},
        {"words": "投档数", "row_start": 0, "col_start": 1, "row_end": 0, "col_end": 1},
        {"words": "21", "row_start": 1, "col_start": 1, "row_end": 3, "col_end": 1},
        {"words": "201", "row_start": 1, "col_start": 0, "row_end": 1, "col_end": 0},
        {"words": "202", "row_start": 2, "col_start": 0, "row_end": 2, "col_end": 0},
        {"words": "203", "row_start": 3, "col_start": 0, "row_end": 3, "col_end": 0},
    ]
    matrix = build_table_from_cells(cells)
    assert matrix[1][1] == "21"
    assert matrix[2][1] == "" and matrix[3][1] == ""


def test_build_table_from_cells_header_rowspan_does_not_leak_to_row1():
    cells = [
        {"words": "代码", "row_start": 0, "col_start": 0, "row_end": 0, "col_end": 0},
        {"words": "名称", "row_start": 0, "col_start": 1, "row_end": 0, "col_end": 1},
        {"words": "投档数", "row_start": 0, "col_start": 2, "row_end": 1, "col_end": 2},
        {"words": "029", "row_start": 1, "col_start": 0, "row_end": 1, "col_end": 0},
        {"words": "生态学", "row_start": 1, "col_start": 1, "row_end": 1, "col_end": 1},
    ]
    matrix = build_table_from_cells(cells)
    assert matrix[0][2] == "投档数"
    assert matrix[1][2] == ""


def test_build_table_from_cells_colspan_only_sets_anchor_cell():
    cells = [
        {"words": "宽表头", "row_start": 0, "col_start": 0, "row_end": 0, "col_end": 7},
    ]
    matrix = build_table_from_cells(cells)
    assert matrix[0][0] == "宽表头"
    assert matrix[0][1] == "" and matrix[0][7] == ""


def test_compact_ocr_context_includes_merged_cell_touching_focus_row():
    ocr = {
        "tables_result": [
            {
                "body": [
                    {
                        "words": "合并投档",
                        "row_start": 1,
                        "col_start": 2,
                        "row_end": 4,
                        "col_end": 2,
                    },
                ]
            }
        ]
    }
    text = compact_ocr_context(ocr, focus_rows=[3])
    assert "合并投档" in text
    assert "r1-4c2-2" in text or "r1c2" in text


def test_split_packed_score_rank_when_headers_already_separated():
    table = [
        ["投档线", "投档最低排位"],
        ["55469531", ""],
    ]

    repaired = repair_table_structure(table)
    assert repaired["table"][1][0] == "554"
    assert repaired["table"][1][1] == "69531"
