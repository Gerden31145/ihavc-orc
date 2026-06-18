from typing import List
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
import io
import json
import re
import asyncio
import httpx
import uvicorn
import logging
from llm_enhancer import LLMEnhancer
from table_splitter import split_table_by_repeated_headers, merge_split_results
from cross_page_merger import merge_cross_page_tables
from ocr_postprocess import repair_table_structure, split_parallel_tables

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="高考分数线OCR服务")

# 添加CORS支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GLM-OCR 配置
GLM_API_KEY = "c44dfa4e72224ccbb0e0eb497cf58bcb.JneopyysoxFdcx2U"
GLM_OCR_URL = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
GLM_OCR_MODEL = "glm-ocr"

# DeepSeek LLM API信息
DEEPSEEK_API_KEY = "sk-d114b6faaa5942969eaaba903080c713"

# 初始化LLM增强器
llm_enhancer = LLMEnhancer(api_key=DEEPSEEK_API_KEY)


async def call_glm_ocr(image_data):
    """调用智谱 GLM-OCR 同步文档解析，返回识别文本。遇到 429 自动重试。"""
    max_retries = 3
    try:
        img_fmt = _detect_image_format(image_data)
        b64 = base64.b64encode(image_data).decode("utf-8")
        file_url = f"data:image/{img_fmt};base64,{b64}"

        payload = {"model": GLM_OCR_MODEL, "file": file_url}
        headers = {
            "Authorization": f"Bearer {GLM_API_KEY}",
            "Content-Type": "application/json",
        }

        logger.info(f"调用 GLM-OCR, 图片大小: {len(image_data)} 字节")

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            for attempt in range(max_retries):
                resp = await client.post(GLM_OCR_URL, headers=headers, json=payload)
                logger.info(f"GLM-OCR 状态码: {resp.status_code}")

                if resp.status_code == 200:
                    break

                if resp.status_code == 429 and attempt < max_retries - 1:
                    wait = 3 * (attempt + 1)
                    logger.warning(f"GLM-OCR 限流(429), 第{attempt+1}次重试, 等待{wait}秒...")
                    await asyncio.sleep(wait)
                    continue

                logger.error(f"GLM-OCR 调用失败: {resp.status_code} - {resp.text[:500]}")
                return None

        result = resp.json()
        content = _extract_glm_ocr_content(result)
        logger.info(f"GLM-OCR 结果长度: {len(content)} 字符")
        return content

    except Exception as e:
        logger.error(f"GLM-OCR 调用异常: {e}")
        return None


def _extract_glm_ocr_content(result):
    """从 GLM-OCR 响应中提取文本内容。"""
    if isinstance(result, dict):
        # 优先取 md_results（HTML/Markdown 格式）
        md = result.get("md_results", "")
        if md:
            return md
        # layout_details 中各区域的 content
        layout = result.get("layout_details", [])
        if isinstance(layout, list) and layout:
            parts = []
            for page in layout:
                if isinstance(page, list):
                    for block in page:
                        if isinstance(block, dict):
                            content = block.get("content", "")
                            if content:
                                parts.append(content)
                elif isinstance(page, dict):
                    content = page.get("content", "")
                    if content:
                        parts.append(content)
            if parts:
                return "\n".join(parts)
        # 其他 fallback
        for key in ("content", "text", "markdown", "output"):
            val = result.get(key, "")
            if val:
                return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, str):
        return result
    return str(result)


def parse_table_text_to_matrix(text):
    """将 OCR 返回的表格文本（Markdown 或 HTML）解析为 List[List[str]] 矩阵。"""
    if not text:
        return None

    # 尝试 HTML 表格解析
    if "<table" in text.lower():
        matrix = _parse_html_table(text)
        if matrix:
            # GLM-OCR 有时在 </table> 之后仍然输出纯文本格式的表格行，
            # 尝试解析这些附加行并拼接到主矩阵。
            remainder = _extract_post_table_text(text)
            if remainder and remainder.strip():
                extra_rows = _parse_plain_text_rows(remainder, len(matrix[0]) if matrix else 0)
                if extra_rows:
                    matrix.extend(extra_rows)
        return matrix

    # fallback: Markdown 解析
    return _parse_markdown_table(text)


def _extract_post_table_text(html_text: str) -> str:
    """提取 </table> 之后的文本内容。"""
    close_idx = html_text.lower().rfind("</table>")
    if close_idx < 0:
        return ""
    return html_text[close_idx + len("</table>"):]


def _parse_plain_text_rows(text: str, col_count: int) -> list:
    """
    将纯文本解析为表格行。处理 GLM-OCR 在 </table> 之后输出的行。
    策略：跳过看起来像表头/噪声的行，将每行拆分为单元格。
    """
    if col_count <= 0 or not text.strip():
        return []

    lines = text.strip().split("\n")
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳过看起来像表头重复的行（包含已知列名）
        if "编号" in line and "招生院校" in line:
            continue
        # 尝试按空格拆分，但保留括号/方括号内的空格
        cells = _smart_split_line(line, col_count)
        if cells and len(cells) >= 2:
            # 补齐列数
            while len(cells) < col_count:
                cells.append("")
            rows.append(cells[:col_count])

    return rows


def _smart_split_line(line: str, col_count: int) -> list:
    """
    智能拆分纯文本行为单元格。
    策略：第一列通常是短编号(如 '22', '1B')，后面是描述文本。
    """
    # 尝试找到第一个 token（编号/代码）
    # 编号通常是 2-4 位的字母数字组合
    m = re.match(r'^([A-Za-z0-9]{1,4})\s+(.+)$', line)
    if m:
        return [m.group(1), m.group(2)]
    # 如果没有明确的编号前缀，整行作为一列
    return [line]


def _parse_html_table(html_text):
    """解析 HTML <table> 为矩阵。支持 colspan 属性。"""
    rows = []
    for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html_text, re.IGNORECASE | re.DOTALL):
        tr_content = tr_match.group(1)
        cells = []
        for td_match in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_content, re.IGNORECASE | re.DOTALL):
            cell_text = re.sub(r"<[^>]+>", "", td_match.group(1)).strip()
            # Handle colspan: detect colspan="N" and insert the cell text + (N-1) empty cells
            tag_attrs = td_match.group(0)[:td_match.group(0).index(">") + 1]
            colspan_m = re.search(r'colspan\s*=\s*["\']?(\d+)', tag_attrs, re.IGNORECASE)
            colspan = int(colspan_m.group(1)) if colspan_m else 1
            cells.append(cell_text)
            for _ in range(colspan - 1):
                cells.append("")
        if cells:
            rows.append(cells)

    if not rows:
        return None

    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    return rows


def _parse_markdown_table(markdown_text):
    """解析 Markdown 表格为矩阵。"""
    lines = markdown_text.strip().split('\n')
    rows = []
    for line in lines:
        line = line.strip()
        if not line or not line.startswith('|'):
            continue
        if re.match(r'^\|[\s\-:]+\|$', line):
            continue
        parts = line.split('|')
        if parts and parts[0] == '':
            parts = parts[1:]
        if parts and parts[-1] == '':
            parts = parts[:-1]
        cells = [p.strip() for p in parts]
        if cells:
            rows.append(cells)

    if not rows:
        return None

    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    return rows


def _detect_image_format(data):
    """从图片二进制数据检测格式。"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "png"
    elif data[:2] == b'\xff\xd8':
        return "jpeg"
    return "jpeg"


async def run_table_recognition_pipeline(image_data):
    """
    识别主流程：
    1. GLM-OCR 主识别
    2. 表格结构修复（投档线/排位拆分等）
    """
    ocr_text = await call_glm_ocr(image_data)
    # Debug: save raw OCR text
    if ocr_text:
        logger.info(f"[DEBUG] raw OCR text length: {len(ocr_text)}")
        logger.info(f"[DEBUG] raw OCR text (first 2000 chars): {ocr_text[:2000]}")
        # Check for 园林 in raw text
        if '园林' in ocr_text:
            idx = ocr_text.index('园林')
            logger.info(f"[DEBUG] 园林 in raw OCR at pos {idx}: ...{ocr_text[max(0,idx-50):idx+200]}...")
    matrix = parse_table_text_to_matrix(ocr_text) if ocr_text else None

    # 表格结构修复：拆分粘连表头、粘连数字等
    repair_corrections = []
    if matrix:
        # 并排同表头表格拆分：GLM 偶尔会把一张图上并排的两张同表头表格粘成
        # 一张宽表（表头 = n 列重复 K 次）。按列优先（读完左列再读右列）
        # 拆成一张干净的 n 列表，丢弃换行串位产生的碎片行。
        matrix, split_corrections = split_parallel_tables(matrix)
        repair_corrections.extend(split_corrections)
        if split_corrections:
            logger.info(f"[DEBUG] 并排表格拆分: {split_corrections[0]['corrected']}")

        logger.info(f"[DEBUG] repair 前 headers: {matrix[0] if matrix else 'N/A'}")
        for i, row in enumerate(matrix[:4]):
            logger.info(f"[DEBUG] repair 前 row[{i}]: {row}")
        repair_result = repair_table_structure(matrix)
        matrix = repair_result["table"]
        repair_corrections.extend(repair_result.get("corrections", []))
        if repair_result.get("corrections"):
            logger.info(f"表格结构修复: {len(repair_result['corrections'])} 项修正")
            for c in repair_result["corrections"]:
                logger.info(f"[DEBUG] correction: {c}")
        else:
            logger.info(f"[DEBUG] repair 未产生任何修正, numeric_columns={repair_result.get('numeric_columns', [])}")
        logger.info(f"[DEBUG] repair 后 total rows: {len(matrix)}")
        logger.info(f"[DEBUG] repair 后 headers: {matrix[0] if matrix else 'N/A'}")
        for i, row in enumerate(matrix[:4]):
            logger.info(f"[DEBUG] repair 后 row[{i}]: {row}")

    meta = {
        "source_engine": "glm-ocr",
        "repair_corrections": repair_corrections,
    }
    return matrix, meta


@app.post("/api/ocr")
async def ocr_table(file: UploadFile = File(...), enhance: bool = True):
    """
    OCR识别表格图片，可选择是否使用LLM增强
    """
    # 验证文件类型
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="只支持图片文件")

    # 读取图片
    try:
        image_data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    try:
        data_matrix, recognition_meta = await run_table_recognition_pipeline(image_data)
        if data_matrix:
            # 如果启用LLM增强
            if enhance:
                try:
                    # 先调用LLM增强整个表格
                    enhanced_result = llm_enhancer.enhance_table_data(data_matrix, None)

                    # 合并结构修复的 corrections
                    if recognition_meta.get("repair_corrections"):
                        if "corrections" not in enhanced_result:
                            enhanced_result["corrections"] = []
                        enhanced_result["corrections"] = recognition_meta["repair_corrections"] + enhanced_result["corrections"]

                    # 检查LLM增强后的表格是否有重复表头
                    enhanced_table = enhanced_result.get("enhanced_table", data_matrix)
                    if enhanced_table and len(enhanced_table) > 0:
                        enhanced_header = enhanced_table[0]
                        logger.info(f"LLM增强后表头: {enhanced_header}")

                        # 检测并拆分重复表头的表格
                        split_tables = split_table_by_repeated_headers(enhanced_table)

                        if len(split_tables) > 1:
                            logger.info(f"LLM增强后的表格被拆分为 {len(split_tables)} 个子表格")

                            # 构建拆分后的结果
                            split_results = []
                            for split_table in split_tables:
                                # 为每个子表格创建结果（使用相同的corrections和structure）
                                split_results.append({
                                    "enhanced_table": split_table,
                                    "corrections": enhanced_result.get("corrections", []),
                                    "table_structure": {
                                        "headers": split_table[0] if split_table else [],
                                        "data_types": [],
                                        "estimated_columns": len(split_table[0]) if split_table else 0
                                    }
                                })

                            # 合并所有子表格
                            enhanced_result = merge_split_results(split_results)

                    # 使用增强后的表格数据
                    enhanced_table = enhanced_result.get("enhanced_table", data_matrix)
                    split_info = enhanced_result.get("split_info", {})

                    # 如果表格被拆分，返回拆分后的多个表格
                    if split_info.get("was_split") and split_info.get("table_count", 0) > 1:
                        # 重新获取拆分后的独立表格
                        split_tables = split_table_by_repeated_headers(enhanced_table)

                        return {
                            "success": True,
                            "data": {
                                "tables": [
                                    {
                                        "headers": table[0] if table else [],
                                        "rows": table[1:] if len(table) > 1 else []
                                    }
                                    for table in split_tables
                                ],
                                "is_split": True,
                                "table_count": len(split_tables),
                                "meta": recognition_meta,
                            },
                            "enhancement": {
                                "applied": True,
                                "corrections": enhanced_result.get("corrections", []),
                                "table_structure": enhanced_result.get("table_structure", {}),
                                "split_info": split_info,
                                "error": enhanced_result.get("error")
                            }
                        }
                    # 未拆分，返回单个表格（保持原有格式）
                    return {
                        "success": True,
                        "data": {
                            "headers": enhanced_table[0] if enhanced_table else [],
                            "rows": enhanced_table[1:] if len(enhanced_table) > 1 else [],
                            "original_headers": data_matrix[0] if data_matrix else [],
                            "original_rows": data_matrix[1:] if len(data_matrix) > 1 else [],
                            "meta": recognition_meta,
                        },
                        "enhancement": {
                            "applied": True,
                            "corrections": enhanced_result.get("corrections", []),
                            "table_structure": enhanced_result.get("table_structure", {}),
                            "split_info": split_info,
                            "error": enhanced_result.get("error")
                        }
                    }
                except Exception as e:
                    print(f"LLM增强失败，返回原始数据: {e}")
                    # LLM增强失败时返回原始数据
                    return {
                        "success": True,
                        "data": {
                            "headers": data_matrix[0] if data_matrix else [],
                            "rows": data_matrix[1:] if len(data_matrix) > 1 else [],
                            "meta": recognition_meta,
                        },
                        "enhancement": {
                            "applied": False,
                            "error": f"LLM增强失败: {str(e)}"
                        }
                    }
            # 不使用LLM增强
            return {
                "success": True,
                "data": {
                    "headers": data_matrix[0] if data_matrix else [],
                    "rows": data_matrix[1:] if len(data_matrix) > 1 else [],
                    "meta": recognition_meta,
                },
                "enhancement": {
                    "applied": False
                }
            }
        return {
            "success": False,
            "error": "未能提取到有效表格内容"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR服务调用失败: {str(e)}")


@app.post("/api/ocr-batch")
async def ocr_batch(files: List[UploadFile] = File(...), enhance: bool = True):
    """
    批量OCR：按顺序识别多张图片，智能合并跨页表格。
    """
    # 验证所有文件
    for f in files:
        if not f.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {f.filename}")

    # 读取所有图片
    images: List[bytes] = []
    for f in files:
        try:
            images.append(await f.read())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    try:
        # 并发识别所有图片（保留原始顺序，限流避免 GLM 服务端排队）
        # 实测：并发 5 为最优——超过后单图延迟从 ~29s 飙升到 47-64s，总耗时反而更长
        OCR_CONCURRENCY = 5
        page_matrices: List[list | None] = [None] * len(images)
        all_repair_corrections: list = []
        semaphore = asyncio.Semaphore(OCR_CONCURRENCY)
        progress_lock = asyncio.Lock()
        done_count = 0

        async def process_one(idx: int, img_data: bytes):
            nonlocal done_count
            async with semaphore:
                logger.info(f"批量OCR: 正在处理第{idx+1}/{len(images)}张图片")
                matrix, page_meta = await run_table_recognition_pipeline(img_data)
                page_matrices[idx] = matrix
                async with progress_lock:
                    done_count += 1
                    logger.info(f"批量OCR: 已完成 {done_count}/{len(images)}")
                return page_meta.get("repair_corrections", [])

        corrections_per_page = await asyncio.gather(
            *[process_one(i, img) for i, img in enumerate(images)]
        )
        for corrections in corrections_per_page:
            if corrections:
                all_repair_corrections.extend(corrections)

        # 合并跨页表格
        # Debug: log each page matrix
        for pi, pm in enumerate(page_matrices):
            if pm:
                logger.info(f"[DEBUG] page {pi+1}: {len(pm)} rows, {len(pm[0]) if pm else 0} cols, header={pm[0] if pm else 'N/A'}")
            else:
                logger.info(f"[DEBUG] page {pi+1}: None")
        merged = merge_cross_page_tables(page_matrices)
        headers = merged["headers"]
        rows = merged["rows"]
        diagnostics = merged["merge_diagnostics"]
        logger.info(f"[DEBUG] merged: headers={headers}, total_rows={len(rows)}, diagnostics={diagnostics}")
        if rows:
            for i in range(min(3, len(rows))):
                logger.info(f"[DEBUG] merged row[{i}]: {rows[i]}")
            logger.info(f"[DEBUG] merged row[-1]: {rows[-1]}")
            # Log the last 5 rows of page 1 (before page 2 data starts)
            page1_data_count = sum(1 for r in page_matrices[0][1:] if r is not None) if page_matrices[0] else 0
            logger.info(f"[DEBUG] page1 data rows count: {page1_data_count}")
            # Find "园林" rows
            for i, row in enumerate(rows):
                if any('园林' in str(cell) for cell in row):
                    logger.info(f"[DEBUG] 园林 row at merged[{i}]: {row}")
            # Find row that contains "常者不宜"
            for i, row in enumerate(rows):
                if any('常者不宜' in str(cell) for cell in row):
                    logger.info(f"[DEBUG] 常者不宜 row at merged[{i}]: {row}")
            # Log last 3 rows of what would be page1 boundary
            if len(rows) > page1_data_count:
                boundary = page1_data_count
                for i in range(max(0, boundary-2), min(len(rows), boundary+3)):
                    logger.info(f"[DEBUG] boundary row[{i}]: {rows[i]}")

        if not headers:
            return {"success": False, "error": "未能提取到有效表格内容"}

        data_matrix = [headers] + rows

        # LLM 增强（复用 /api/ocr 的逻辑）
        if enhance:
            try:
                enhanced_result = llm_enhancer.enhance_table_data(data_matrix, None)
                enhanced_table = enhanced_result.get("enhanced_table", data_matrix)

                # 合并结构修复的 corrections
                if all_repair_corrections:
                    if "corrections" not in enhanced_result:
                        enhanced_result["corrections"] = []
                    enhanced_result["corrections"] = all_repair_corrections + enhanced_result["corrections"]

                if enhanced_table and len(enhanced_table) > 0:
                    split_tables = split_table_by_repeated_headers(enhanced_table)

                    if len(split_tables) > 1:
                        split_results = []
                        for st in split_tables:
                            split_results.append({
                                "enhanced_table": st,
                                "corrections": enhanced_result.get("corrections", []),
                                "table_structure": {
                                    "headers": st[0] if st else [],
                                    "data_types": [],
                                    "estimated_columns": len(st[0]) if st else 0,
                                },
                            })
                        enhanced_result = merge_split_results(split_results)

                enhanced_table = enhanced_result.get("enhanced_table", data_matrix)
                split_info = enhanced_result.get("split_info", {})

                if split_info.get("was_split") and split_info.get("table_count", 0) > 1:
                    final_tables = split_table_by_repeated_headers(enhanced_table)
                    return {
                        "success": True,
                        "data": {
                            "tables": [
                                {"headers": t[0] if t else [], "rows": t[1:] if len(t) > 1 else []}
                                for t in final_tables
                            ],
                            "is_split": True,
                            "table_count": len(final_tables),
                            "meta": {"source_engine": "glm-ocr", "merge_diagnostics": diagnostics},
                        },
                        "enhancement": {
                            "applied": True,
                            "corrections": enhanced_result.get("corrections", []),
                            "table_structure": enhanced_result.get("table_structure", {}),
                            "split_info": split_info,
                            "error": enhanced_result.get("error"),
                        },
                    }

                return {
                    "success": True,
                    "data": {
                        "headers": enhanced_table[0] if enhanced_table else [],
                        "rows": enhanced_table[1:] if len(enhanced_table) > 1 else [],
                        "original_headers": headers,
                        "original_rows": rows,
                        "meta": {"source_engine": "glm-ocr", "merge_diagnostics": diagnostics},
                    },
                    "enhancement": {
                        "applied": True,
                        "corrections": enhanced_result.get("corrections", []),
                        "table_structure": enhanced_result.get("table_structure", {}),
                        "split_info": split_info,
                        "error": enhanced_result.get("error"),
                    },
                }
            except Exception as e:
                logger.warning(f"批量OCR LLM增强失败: {e}")

        # 无 LLM 增强
        return {
            "success": True,
            "data": {
                "headers": headers,
                "rows": rows,
                "meta": {"source_engine": "glm-ocr", "merge_diagnostics": diagnostics},
            },
            "enhancement": {"applied": False},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量OCR服务调用失败: {str(e)}")


@app.post("/api/synthesize")
async def synthesize_table(text: str):
    """
    从文本内容中合成表格
    """
    if not text or len(text.strip()) < 10:
        return {
            "success": False,
            "error": "文本内容过短，无法合成表格"
        }
    
    try:
        # 使用LLM从文本中合成表格
        synthesis_result = llm_enhancer.synthesize_table_from_text(text)
        
        synthesized_table = synthesis_result.get("synthesized_table", [])
        confidence = synthesis_result.get("confidence", 0.0)
        
        if synthesized_table and len(synthesized_table) > 0:
            return {
                "success": True,
                "data": {
                    "headers": synthesized_table[0] if synthesized_table else [],
                    "rows": synthesized_table[1:] if len(synthesized_table) > 1 else []
                },
                "synthesis": {
                    "confidence": confidence,
                    "extracted_info": synthesis_result.get("extracted_info", {}),
                    "error": synthesis_result.get("error")
                }
            }
        else:
            return {
                "success": False,
                "error": "无法从文本中合成表格",
                "detail": synthesis_result.get("error", "未知错误")
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"表格合成失败: {str(e)}"
        }


@app.get("/")
async def root():
    return {"message": "高考分数线OCR服务API（支持LLM增强）"}


if __name__ == '__main__':
    print("启动OCR服务...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
