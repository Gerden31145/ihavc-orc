from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
import io
import json
import re
import time
import requests
import uvicorn
import logging
from llm_enhancer import LLMEnhancer
from table_splitter import split_table_by_repeated_headers, merge_split_results

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

# Gitee AI DeepSeek-OCR-2 配置
GITEE_API_KEY = "YNDQSJY1R3VRLUVZTW12OCWFUFBLXBGVZ5ATDUZ4"
GITEE_BASE_URL = "https://ai.gitee.com/v1"
GITEE_OCR_MODEL = "DeepSeek-OCR"

# DeepSeek LLM API信息
DEEPSEEK_API_KEY = "sk-d114b6faaa5942969eaaba903080c713"

# 初始化LLM增强器
llm_enhancer = LLMEnhancer(api_key=DEEPSEEK_API_KEY)
_pp_structure_engine = None


def call_deepseek_ocr(image_data):
    """调用 Gitee AI DeepSeek-OCR 异步文档解析，返回识别文本。"""
    submit_url = f"{GITEE_BASE_URL}/async/documents/parse"
    auth_headers = {"Authorization": f"Bearer {GITEE_API_KEY}"}

    try:
        logger.info(f"提交 OCR 任务: {submit_url}, 图片大小: {len(image_data)} 字节")

        img_fmt = _detect_image_format(image_data)
        mime = "image/png" if img_fmt == "png" else "image/jpeg"
        files = {"file": (f"image.{img_fmt}", image_data, mime)}
        data = {"model": GITEE_OCR_MODEL}

        resp = requests.post(submit_url, headers=auth_headers, files=files, data=data, timeout=120)
        logger.info(f"OCR 任务提交状态码: {resp.status_code}")

        if resp.status_code not in (200, 201):
            logger.error(f"OCR 任务提交失败: {resp.status_code} - {resp.text[:500]}")
            return None

        result = resp.json()
        task_id = result.get("task_id")
        if not task_id:
            logger.error(f"未获取到 task_id: {json.dumps(result, ensure_ascii=False)[:500]}")
            return None

        # 优先使用返回的轮询 URL
        poll_url = (result.get("urls", {}).get("get")
                    or f"https://ai.gitee.com/api/v1/task/{task_id}")
        logger.info(f"OCR 任务已提交, task_id={task_id}, 轮询URL={poll_url}")

        for i in range(60):
            time.sleep(2)
            pr = requests.get(poll_url, headers=auth_headers, timeout=30)
            if pr.status_code != 200:
                logger.warning(f"轮询第{i+1}次失败: {pr.status_code}")
                continue

            pr_result = pr.json()
            status = pr_result.get("status", "unknown")
            logger.info(f"轮询第{i+1}次, 状态: {status}")

            if status in ("completed", "success"):
                output = pr_result.get("output", {})
                content = _extract_async_ocr_output(output)
                logger.info(f"OCR 结果长度: {len(content)} 字符")

                with open("debug_ocr_output.txt", "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("原始OCR输出已保存到 debug_ocr_output.txt")
                return content

            elif status in ("failed", "error", "cancelled"):
                logger.error(f"OCR 任务失败: {json.dumps(pr_result, ensure_ascii=False)[:500]}")
                return None

        logger.error("OCR 任务超时（轮询次数耗尽）")
        return None

    except Exception as e:
        logger.error(f"DeepSeek-OCR 调用异常: {e}")
        return None


def _extract_async_ocr_output(output):
    """从异步任务 output.pages[].text_result 中提取文本。"""
    if isinstance(output, dict):
        pages = output.get("pages", [])
        if pages:
            parts = []
            for page in pages:
                text = page.get("text_result", "") if isinstance(page, dict) else str(page)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        # fallback
        return (output.get("text", "")
                or output.get("markdown", "")
                or output.get("content", "")
                or json.dumps(output, ensure_ascii=False))
    if isinstance(output, str):
        return output
    return str(output)


def _extract_ocr_output(output):
    """从异步任务 output 中提取文本内容。"""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return (output.get("text", "")
                or output.get("markdown", "")
                or output.get("content", "")
                or json.dumps(output, ensure_ascii=False))
    if isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, dict):
                parts.append(item.get("text", "") or item.get("markdown", "") or json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(output)


def parse_table_text_to_matrix(text):
    """将 OCR 返回的表格文本（Markdown 或 HTML）解析为 List[List[str]] 矩阵。"""
    if not text:
        return None

    # 尝试 HTML 表格解析
    if "<table" in text.lower():
        return _parse_html_table(text)

    # fallback: Markdown 解析
    return _parse_markdown_table(text)


def _parse_html_table(html_text):
    """解析 HTML <table> 为矩阵。"""
    rows = []
    for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html_text, re.IGNORECASE | re.DOTALL):
        tr_content = tr_match.group(1)
        cells = []
        for td_match in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_content, re.IGNORECASE | re.DOTALL):
            cell_text = re.sub(r"<[^>]+>", "", td_match.group(1)).strip()
            cells.append(cell_text)
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


def extract_table_regions_with_ppstructure(image_data):
    """
    使用 PP-Structure 提取表格区域。
    返回: (regions, meta)
      regions: list[bytes]，每个元素是裁剪后的图片字节
      meta: 辅助诊断信息
    """
    global _pp_structure_engine
    meta = {
        "enabled": False,
        "available": False,
        "region_count": 0,
        "fallback_reason": "",
        "error": None,
    }

    try:
        import cv2
        import numpy as np
        from paddleocr import PPStructure
    except Exception as exc:
        meta["fallback_reason"] = "pp_structure_not_installed"
        meta["error"] = str(exc)
        return [], meta

    meta["available"] = True

    try:
        if _pp_structure_engine is None:
            _pp_structure_engine = PPStructure(show_log=False, layout=False, ocr=False)

        image_np = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        if image_np is None:
            meta["fallback_reason"] = "invalid_image"
            return [], meta

        result = _pp_structure_engine(image_np)
        regions = []
        height, width = image_np.shape[:2]
        for block in result:
            if block.get("type") != "table":
                continue
            bbox = block.get("bbox") or []
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            x1 = max(0, min(x1, width - 1))
            x2 = max(0, min(x2, width))
            y1 = max(0, min(y1, height - 1))
            y2 = max(0, min(y2, height))
            if x2 <= x1 or y2 <= y1:
                continue
            crop = image_np[y1:y2, x1:x2]
            ok, encoded = cv2.imencode(".png", crop)
            if ok:
                regions.append(encoded.tobytes())

        meta["enabled"] = True
        meta["region_count"] = len(regions)
        if not regions:
            meta["fallback_reason"] = "no_table_region_detected"
        return regions, meta
    except Exception as exc:
        meta["enabled"] = True
        meta["fallback_reason"] = "pp_structure_runtime_error"
        meta["error"] = str(exc)
        return [], meta


def merge_table_matrices(matrices):
    """合并多个矩阵表，沿用最长表头并拼接数据行。"""
    if not matrices:
        return None
    if len(matrices) == 1:
        return matrices[0]

    headers = [table[0] for table in matrices if table]
    if not headers:
        return None
    max_header = max(headers, key=len)
    merged = [max_header]
    for table in matrices:
        if table and len(table) > 1:
            merged.extend(table[1:])
    return merged


def _detect_image_format(data):
    """从图片二进制数据检测格式。"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "png"
    elif data[:2] == b'\xff\xd8':
        return "jpeg"
    return "jpeg"


def run_table_recognition_pipeline(image_data):
    """
    识别主流程：
    1. PP-Structure 辅助切表
    2. DeepSeek-OCR-2 主识别
    3. 失败/无区域时回退整图识别
    """
    regions, pp_meta = extract_table_regions_with_ppstructure(image_data)
    candidate_images = regions if regions else [image_data]
    fallback_used = not bool(regions)
    matrices = []

    for candidate in candidate_images:
        ocr_text = call_deepseek_ocr(candidate)
        if ocr_text:
            matrix = parse_table_text_to_matrix(ocr_text)
            if matrix:
                matrices.append(matrix)

    if not matrices and regions:
        ocr_text = call_deepseek_ocr(image_data)
        if ocr_text:
            matrix = parse_table_text_to_matrix(ocr_text)
            if matrix:
                matrices.append(matrix)
                fallback_used = True

    merged_matrix = merge_table_matrices(matrices)
    meta = {
        "source_engine": "deepseek-ocr-2",
        "pp_structure": {
            **pp_meta,
            "fallback_used": fallback_used,
        },
        "candidate_count": len(candidate_images),
    }
    return merged_matrix, meta


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
        data_matrix, recognition_meta = run_table_recognition_pipeline(image_data)
        if data_matrix:
            # 如果启用LLM增强
            if enhance:
                try:
                    # 先调用LLM增强整个表格
                    enhanced_result = llm_enhancer.enhance_table_data(data_matrix, None)

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
