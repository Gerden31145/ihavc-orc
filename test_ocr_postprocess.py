from ocr_postprocess import repair_table_structure


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


def test_split_packed_score_rank_when_headers_already_separated():
    table = [
        ["投档线", "投档最低排位"],
        ["55469531", ""],
    ]

    repaired = repair_table_structure(table)
    assert repaired["table"][1][0] == "554"
    assert repaired["table"][1][1] == "69531"


def test_split_slash_separated_header_in_second_row():
    """GLM-OCR returns multi-row header with slash-separated '投档线/投档最低排位' in row 1.

    After multi-row header flattening, row[0]+row[1] merge into a single header,
    then Step 0 splits the sticky header. Result:
      row[0] = [..., '投档线', '投档最低排位', ...]  (merged + split)
      row[2] = [..., '614', '17935', ...]            (packed digits split)
    """
    table = [
        ["批次", "", "", "", "", "", ""],
        ["批次", "院校/专业组/专业名称", "投档线", "投档线/投档最低排位", "录取数", "录取最低排位", "录取最低分"],
        ["10295", "江南大学", "", "", "46", "", ""],
        ["203", "专业组203", "14", "61417935", "14", "17935", "614"],
    ]

    repaired = repair_table_structure(table)

    # row[0] (merged header): col 3 split → "投档线" | "投档最低排位"
    assert repaired["table"][0][3] == "投档线"
    assert repaired["table"][0][4] == "投档最低排位"

    # row[2] (data, was row[3]): packed "61417935" split → "614" | "17935"
    assert repaired["table"][2][3] == "614"
    assert repaired["table"][2][4] == "17935"

    assert repaired["corrections"]


def test_preserve_alphanumeric_codes():
    """Letter-prefixed codes like A1, B2 should NOT be stripped to 1, 2."""
    table = [
        ["专业组", "投档线"],
        ["A1", "614"],
        ["B2", "608"],
        ["C10", "595"],
    ]

    repaired = repair_table_structure(table)

    assert repaired["table"][1][0] == "A1"
    assert repaired["table"][2][0] == "B2"
    assert repaired["table"][3][0] == "C10"
    # Numeric column should still be normalized
    assert repaired["table"][1][1] == "614"


def test_flatten_multirow_header_with_outer_frame():
    """GLM-OCR puts outer frame label '本科' in row[0]; real headers are in row[1].

    The sparse row[0] is dropped entirely, row[1] becomes the header.
    """
    table = [
        ["本科", "", "", "", "", ""],
        ["院校代号", "院校名称", "计划数", "投档线", "录取最低排位", "录取数"],
        ["10295", "江南大学", "46", "614", "17935", "30"],
        ["10296", "其他大学", "20", "598", "25000", "18"],
    ]

    repaired = repair_table_structure(table)

    # row[0] ("本科" frame) dropped; row[1] promoted to header
    assert repaired["table"][0] == ["院校代号", "院校名称", "计划数", "投档线", "录取最低排位", "录取数"]
    # Data rows now start at index 1
    assert repaired["table"][1][0] == "10295"
    assert repaired["table"][1][1] == "江南大学"
    assert repaired["table"][2][0] == "10296"

    # Should have a correction about removing the frame row
    assert any("removed" in c.get("reason", "") or "dropped" in c.get("corrected", "") for c in repaired["corrections"])


def test_remove_repeated_header_rows_in_data():
    """Header row reappears in the middle of data — should be removed."""
    table = [
        ["院校代号", "院校名称", "投档线"],
        ["10295", "江南大学", "614"],
        ["院校代号", "院校名称", "投档线"],   # repeated header
        ["10296", "其他大学", "598"],
        ["10297", "又一个大学", "601"],
        ["院校代号", "院校名称", "投档线"],   # another repeated header
        ["10298", "最后大学", "620"],
    ]

    repaired = repair_table_structure(table)

    # Only 5 rows should remain: header + 4 data rows
    assert len(repaired["table"]) == 5
    assert repaired["table"][0] == ["院校代号", "院校名称", "投档线"]
    assert repaired["table"][1][1] == "江南大学"
    assert repaired["table"][2][1] == "其他大学"
    assert repaired["table"][3][1] == "又一个大学"
    assert repaired["table"][4][1] == "最后大学"

    assert any("repeated header" in c.get("reason", "") for c in repaired["corrections"])


def test_remove_repeated_multirow_header_with_sparse_row():
    """Sparse outer frame + header row appear together in data — both removed."""
    table = [
        ["院校代号", "院校名称", "投档线"],
        ["10295", "江南大学", "614"],
        ["", "", ""],                          # sparse row (outer frame)
        ["院校代号", "院校名称", "投档线"],    # repeated header
        ["10296", "其他大学", "598"],
    ]

    repaired = repair_table_structure(table)

    assert len(repaired["table"]) == 3
    assert repaired["table"][0] == ["院校代号", "院校名称", "投档线"]
    assert repaired["table"][1][1] == "江南大学"
    assert repaired["table"][2][1] == "其他大学"

    assert any("repeated header" in c.get("reason", "") for c in repaired["corrections"])
