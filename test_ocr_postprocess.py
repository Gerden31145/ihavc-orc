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
