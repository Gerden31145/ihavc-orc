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
