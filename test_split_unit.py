"""split_parallel_tables 单元测试：passthrough 安全性 + 拆分正确性。"""
from ocr_postprocess import (
    split_parallel_tables,
    _detect_repeated_header_blocks,
    merge_wrap_continuations,
)

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

# === merge_wrap_continuations 测试：只合并安全的换行续行，不碰真实条目 ===
HDR = ["编号", "招生院校(专业)", "计划", "选科", "学制", "学费"]

# 6) 父名已完整 + 冗余尾部(数据为父行子集) -> 丢弃续行 (img6 "校区)" 模式)
m6 = [
    list(HDR),
    ["2F", "计算机科学与技术(广州番禺校区)", "3", "化学", "4", "6850"],
    ["", "校区)", "", "化学", "4", "6850"],
    ["30", "下一个专业", "2", "物理", "4", "5800"],
]
post, corr = merge_wrap_continuations([list(r) for r in m6])
assert corr, "冗余续行应被丢弃"
assert len(post) == 3, f"应剩表头+2数据行, got {len(post)}"
assert post[1][1] == "计算机科学与技术(广州番禺校区)", "父行名字不应被改动"
assert all("校区)" != r[1] for r in post[1:]), "冗余 '校区)' 应被丢弃"
print("[OK] 6) 父名完整+冗余尾部 -> 丢弃续行")

# 7) 父名被截断(开括号未闭合) + 尾部 -> 并回父名 (img27 模式)
m7 = [
    list(HDR),
    ["26", "木材科学与工程(一、二年级", "2", "化学", "4", "6380"],
    ["", "新庄校区)", "", "", "", ""],
]
post, corr = merge_wrap_continuations([list(r) for r in m7])
assert corr, "截断父名应补全"
assert len(post) == 2, "续行应并入父行"
assert post[1][1] == "木材科学与工程(一、二年级新庄校区)", f"名字应补全, got {post[1][1]}"
print("[OK] 7) 父名截断+尾部 -> 并回父名")

# 8) 真实条目缺序号(完整名字) -> 不合并 (img12 计算机类 模式)
m8 = [
    list(HDR),
    ["46", "电子信息类(含基地班)(电子信息科学与技术、通信工程)", "5", "化学", "4", "5800"],
    ["", "计算机类(含基地班)(计算机科学与技术、数据科学与大数据技术)", "4", "化学", "4", "5800"],
]
post, corr = merge_wrap_continuations([list(r) for r in m8])
assert not corr, "完整名字的真实条目缺序号不应被合并"
assert len(post) == 3, "真实条目必须保留"
print("[OK] 8) 真实条目缺序号 -> 不动")

# 9) 父名已含尾部(冗余) -> 丢弃, 即使数据略异 (img5/img6 "实验班)"/"区)" 模式)
m9 = [
    list(HDR),
    ["50", "国际经济与贸易(数字贸易实验班)", "3", "不限", "4", "28000"],
    ["", "实验班)", "2", "不限", "4", "28000"],
]
post, corr = merge_wrap_continuations([list(r) for r in m9])
assert corr, "父名已含的冗余续行应丢弃"
assert len(post) == 2, f"应剩表头+1数据行, got {len(post)}"
assert post[1][1] == "国际经济与贸易(数字贸易实验班)", "父名不应被改"
print("[OK] 9) 父名已含尾部 -> 丢弃冗余续行")

# 9b) 平衡括号注释 + 数据不一致(疑似另一条目残片) -> 仅丢弃, 不误并 (img6 "(广州番禺校区)" 模式)
m9b = [
    list(HDR),
    ["41", "中药学(不招收色盲色弱考生)", "2", "化学", "4", "12000"],
    ["", "(广州番禺校区)", "", "不限", "4", "6850"],
    ["43", "国际经济与贸易(全英语教学)", "2", "化学", "4", "12000"],
]
post, corr = merge_wrap_continuations([list(r) for r in m9b])
assert corr, "数据不一致的注释残片应丢弃"
assert len(post) == 3, "应剩表头+2数据行(残片丢弃)"
assert post[1][1] == "中药学(不招收色盲色弱考生)", "数据不一致时不应把注释误并到父名"
print("[OK] 9b) 注释残片+数据不一致 -> 仅丢弃不误并")

# 9c) 平衡括号注释 + 数据与父行一致(同条折行) -> 追加注释到父名
m9c = [
    list(HDR),
    ["41", "中药学", "2", "化学", "4", "12000"],
    ["", "(不招收色盲色弱考生)", "2", "化学", "4", "12000"],
]
post, corr = merge_wrap_continuations([list(r) for r in m9c])
assert corr, "同条折行的注释应追加"
assert post[1][1] == "中药学(不招收色盲色弱考生)", f"应追加注释, got {post[1][1]}"
print("[OK] 9c) 同条折行注释+数据一致 -> 追加到父名")

# 10) 孤儿片段(页首无父行) -> 不合并
m10 = [
    list(HDR),
    ["", "管理)", "8", "化学", "4", "26000"],
    ["35", "金融学(中外合作办学)", "3", "不限", "4", "32000"],
]
post, corr = merge_wrap_continuations([list(r) for r in m10])
assert not corr, "页首孤儿片段找不到父行不应合并"
assert len(post) == 3
print("[OK] 10) 孤儿片段 -> 不动")

# 11) 空表/单行 安全
assert merge_wrap_continuations([])[0] == []
assert merge_wrap_continuations([list(HDR)])[1] == []
print("[OK] 11) 空表/单行安全")

print("\nALL UNIT TESTS PASSED")
