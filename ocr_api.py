from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
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

# 百度云API信息
API_KEY = "oRirY5AYCHC7giulzzLj4jFV"
SECRET_KEY = "OHkKy4zC8rSKulma0XQOQ04mn1RACtfl"

# DeepSeek LLM API信息
DEEPSEEK_API_KEY = "sk-d114b6faaa5942969eaaba903080c713"

# 初始化LLM增强器
llm_enhancer = LLMEnhancer(api_key=DEEPSEEK_API_KEY)
_pp_structure_engine = None


def get_access_token():
    """获取百度API访问令牌"""
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY
    }
    try:
        res = requests.post(url, params=params)
        return res.json().get("access_token")
    except Exception as e:
        print(f"获取token失败: {e}")
        return None


def process_single_table(cells):
    """
    处理单个表格的单元格数据
    """
    if not cells:
        return None

    # 找出最大行和最大列，确定表格大小
    max_row = max([cell['row_end'] for cell in cells]) + 1
    max_col = max([cell['col_end'] for cell in cells]) + 1

    # 初始化一个空白矩阵
    matrix = [["" for _ in range(max_col)] for _ in range(max_row)]

    # 填充数据
    for cell in cells:
        r = cell['row_start']
        c = cell['col_start']
        text = cell['words']
        matrix[r][c] = text

    return matrix


def process_table_data(tables_result):
    """
    处理百度OCR返回的表格数据，支持多个表格
    如果有多个表格，会尝试合并它们（假设表头相同）
    """
    if not tables_result:
        return None

    all_tables = []

    # 处理所有识别到的表格
    for table_idx, table_data in enumerate(tables_result):
        cells = table_data.get('body', [])
        if cells:
            matrix = process_single_table(cells)
            if matrix:
                all_tables.append(matrix)
                print(f"已识别表格 {table_idx + 1}: {len(matrix)} 行 x {len(matrix[0])} 列")

    if not all_tables:
        return None

    # 如果只有一个表格，直接返回
    if len(all_tables) == 1:
        return all_tables[0]

    # 如果有多个表格，尝试合并它们
    print(f"\n检测到 {len(all_tables)} 个表格，正在合并...")

    # 假设所有表格的第一行都是表头，检查表头是否相同
    headers = [table[0] for table in all_tables]

    # 找出最长的表头
    max_header = max(headers, key=len)

    # 合并所有表格的数据（跳过表头，保留第一个表头）
    merged_matrix = [max_header]  # 使用第一个表的表头

    for table in all_tables:
        # 添加每个表格的数据行（跳过表头行）
        if len(table) > 1:
            merged_matrix.extend(table[1:])

    print(f"合并后: {len(merged_matrix)} 行 x {len(merged_matrix[0])} 列")
    return merged_matrix


def call_baidu_table_ocr(image_base64_str, access_token):
    """调用百度表格OCR接口。"""
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/table?access_token={access_token}"
    payload = {"image": image_base64_str}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, headers=headers, data=payload)
    return response.json()


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


def run_table_recognition_pipeline(image_data, access_token):
    """
    识别主流程：
    1. PP-Structure 辅助切表
    2. 百度 OCR 主识别
    3. 失败/无区域时回退整图识别
    """
    regions, pp_meta = extract_table_regions_with_ppstructure(image_data)
    candidate_images = regions if regions else [image_data]
    fallback_used = not bool(regions)
    combined_tables_result = []
    matrices = []

    for candidate in candidate_images:
        base64_str = base64.b64encode(candidate).decode("utf-8")
        result = call_baidu_table_ocr(base64_str, access_token)
        tables_result = result.get("tables_result", [])
        if tables_result:
            combined_tables_result.extend(tables_result)
            matrix = process_table_data(tables_result)
            if matrix:
                matrices.append(matrix)

    if not matrices and regions:
        # 区域识别均失败时，再尝试整图兜底一次
        base64_str = base64.b64encode(image_data).decode("utf-8")
        result = call_baidu_table_ocr(base64_str, access_token)
        tables_result = result.get("tables_result", [])
        if tables_result:
            combined_tables_result.extend(tables_result)
            matrix = process_table_data(tables_result)
            if matrix:
                matrices.append(matrix)
                fallback_used = True

    merged_matrix = merge_table_matrices(matrices)
    meta = {
        "source_engine": "baidu_table_ocr",
        "pp_structure": {
            **pp_meta,
            "fallback_used": fallback_used,
        },
        "candidate_count": len(candidate_images),
    }
    return merged_matrix, {"tables_result": combined_tables_result}, meta


@app.post("/api/ocr")
async def ocr_table(file: UploadFile = File(...), enhance: bool = True):
    """
    OCR识别表格图片，可选择是否使用LLM增强
    """
    # 验证文件类型
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="只支持图片文件")

    # 获取访问令牌
    access_token = get_access_token()
    if not access_token:
        raise HTTPException(status_code=500, detail="获取OCR服务令牌失败")

    # 读取图片
    try:
        image_data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    try:
        data_matrix, result, recognition_meta = run_table_recognition_pipeline(image_data, access_token)
        if data_matrix:
            # 如果启用LLM增强
            if enhance:
                try:
                    # 先调用LLM增强整个表格
                    enhanced_result = llm_enhancer.enhance_table_data(data_matrix, result)

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
