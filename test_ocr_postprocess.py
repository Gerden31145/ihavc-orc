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
    """GLM-OCR returns multi-row header with slash-separated '投档线/投档最低排位' in row 1."""
    table = [
        ["批次", "", "", "", "", "", ""],
        ["批次", "院校/专业组/专业名称", "投档线", "投档线/投档最低排位", "录取数", "录取最低排位", "录取最低分"],
        ["10295", "江南大学", "", "", "46", "", ""],
        ["203", "专业组203", "14", "61417935", "14", "17935", "614"],
    ]

    repaired = repair_table_structure(table)

    # row[1] column 3 should be split: "投档线/投档最低排位" → "投档线" | "投档最低排位"
    assert repaired["table"][1][3] == "投档线"
    assert repaired["table"][1][4] == "投档最低排位"

    # row[3] packed data "61417935" should be split → "614" | "17935"
    assert repaired["table"][3][3] == "614"
    assert repaired["table"][3][4] == "17935"

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
