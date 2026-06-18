"""split_parallel_tables 单元测试：passthrough 安全性 + 拆分正确性。"""
from ocr_postprocess import split_parallel_tables, _detect_repeated_header_blocks

def filled_post(post):
    return post[1:]  # data rows

# 1) 单张 6 列表 -> 不拆
single = [
    ["编号","招生院校(专业)","计划","选科","学制","学费"],
    ["01","轻工类","4","物理","4","6380"],
    ["09","食品科学与工程","2","物理","4","5800"],
]
post, corr = split_parallel_tables([list(r) for r in single])
assert not corr, f"单表不应拆, got corr={corr}"
assert post == single, "单表应原样返回"
print("[OK] 1) 单张6列表原样穿透")

# 2) 真·12列异表头 -> 不拆 (块不匹配)
wide_distinct = [
    ["A","B","C","D","E","F","G","H","I","J","K","L"],
    ["1","2","3","4","5","6","7","8","9","10","11","12"],
]
post, corr = split_parallel_tables([list(r) for r in wide_distinct])
assert not corr, f"异表头12列不应拆"
assert post == wide_distinct
print("[OK] 2) 真·12列异表头原样穿透")

# 3) 并行同表头 12列 -> 拆成6列, 列优先
parallel = [
    ["编号","招生院校(专业)","计划","选科","学制","学费","编号","招生院校(专业)","计划","选科","学制","学费"],
    ["09","轻工类","4","物理","4","6380","90","信息管理","2","不限","4","5720"],   # A+B 各一
    ["10","合成生物学","2","物理","4","5800","","","","","",""],                        # 仅 A
    ["","","","","","","05","水产类","1","物理","4","2500"],                            # 仅 B
    ["17","环境科学(...)","4","物理","4","5800","","学)","","","",""],                  # A + B碎片
]
post, corr = split_parallel_tables([list(r) for r in parallel])
assert corr, "并行应拆分"
assert len(post[0])==6, f"拆后应6列, got {len(post[0])}"
# 期望: header + [A09, A10, A17] + [B90, B05]  (B碎片 '学)' dropped, A empty dropped)
data = post[1:]
codes = [r[0] for r in data]
print("  拆后编号顺序:", codes)
assert codes == ["09","10","17","90","05"], f"列优先顺序错: {codes}"
# 碎片 '学)' 不应出现
assert all("学)" != r[1] for r in data), "碎片未被丢弃"
print("[OK] 3) 并行同表头按列优先拆分, 碎片丢弃")

# 4) _detect_repeated_header_blocks 边界
assert _detect_repeated_header_blocks(["a","b","a","b"])[0]==2
assert _detect_repeated_header_blocks(["a","b","c","d"])[0]==1
assert _detect_repeated_header_blocks(["a","b","c"])[0]==1  # 奇数无法等分
print("[OK] 4) 块检测正确")

# 5) 空/极小矩阵不崩
assert split_parallel_tables([])[0]==[]
assert split_parallel_tables([["a"]])[1]==[]  # 1列, 不拆
print("[OK] 5) 边界输入安全")

print("\nALL UNIT TESTS PASSED")
