import base64
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from llm_enhancer_v2 import LLMEnhancer
from ocr_postprocess import build_table_from_cells, preprocess_image_for_ocr, repair_table_structure
from ppstructure_engine import run_ppstructure
from table_splitter import merge_split_results, split_table_by_repeated_headers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Gaokao OCR Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("BAIDU_OCR_API_KEY", "oRirY5AYCHC7giulzzLj4jFV")
SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY", "OHkKy4zC8rSKulma0XQOQ04mn1RACtfl")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-d114b6faaa5942969eaaba903080c713")
DEFAULT_OCR_ENGINE = os.getenv("OCR_ENGINE", "baidu").strip().lower()

http_session = requests.Session()
access_token_cache = {"value": None, "expires_at": 0.0}
llm_enhancer = LLMEnhancer(api_key=DEEPSEEK_API_KEY)


def get_access_token() -> Optional[str]:
    if access_token_cache["value"] and access_token_cache["expires_at"] > time.time():
        return access_token_cache["value"]

    try:
        response = http_session.post(
            "https://aip.baidubce.com/oauth/2.0/token",
            params={
                "grant_type": "client_credentials",
                "client_id": API_KEY,
                "client_secret": SECRET_KEY,
            },
            timeout=15,
        )
        payload = response.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 2592000))
        if token:
            access_token_cache["value"] = token
            access_token_cache["expires_at"] = time.time() + max(60, expires_in - 300)
        return token
    except Exception as exc:
        logger.exception("Failed to get access token: %s", exc)
        return None


def process_single_table(cells: List[Dict[str, Any]]):
    if not cells:
        return None
    return build_table_from_cells(cells)


def process_table_data(tables_result: List[Dict[str, Any]]):
    if not tables_result:
        return None

    all_tables = []
    for table in tables_result:
        matrix = process_single_table(table.get("body", []))
        if matrix:
            all_tables.append(matrix)

    if not all_tables:
        return None
    if len(all_tables) == 1:
        return all_tables[0]

    max_header = max((table[0] for table in all_tables if table), key=len)
    merged_matrix = [max_header]
    for table in all_tables:
        if len(table) > 1:
            merged_matrix.extend(table[1:])
    return merged_matrix


def build_table_response(table: List[List[str]]) -> Dict[str, Any]:
    return {
        "headers": table[0] if table else [],
        "rows": table[1:] if len(table) > 1 else [],
    }


@app.post("/api/ocr")
async def ocr_table(file: UploadFile = File(...), enhance: bool = True, engine: Optional[str] = None):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    started_at = time.perf_counter()
    try:
        image_data = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read image: {exc}")

    selected_engine = (engine or DEFAULT_OCR_ENGINE or "baidu").strip().lower()

    # Engine 1: PP-Structure (local) — best effort; fallback to baidu if unavailable.
    if selected_engine in {"ppstructure", "pp-structure", "paddle", "paddleocr"}:
        table_matrix, pp_raw, pp_diag = run_ppstructure(image_data)
        if table_matrix:
            data_matrix = table_matrix
            ocr_raw_result: Dict[str, Any] = {"ppstructure": pp_raw, "engine": "ppstructure"}
            preprocess_info = {"applied": False, "reason": "ppstructure_handles_preprocess"}
            engine_diag = {
                "engine": "ppstructure",
                "ppstructure": {
                    "model_loaded": pp_diag.model_loaded,
                    "tables_found": pp_diag.tables_found,
                    "blocks_found": pp_diag.blocks_found,
                    "timing_ms": pp_diag.timing_ms,
                    "error": pp_diag.error,
                },
            }
        else:
            logger.warning("PP-Structure unavailable or no table found, fallback to Baidu. reason=%s", pp_diag.error)
            selected_engine = "baidu"
            engine_diag = {
                "engine": "ppstructure_fallback_to_baidu",
                "ppstructure": {
                    "model_loaded": pp_diag.model_loaded,
                    "tables_found": pp_diag.tables_found,
                    "blocks_found": pp_diag.blocks_found,
                    "timing_ms": pp_diag.timing_ms,
                    "error": pp_diag.error,
                },
            }
    else:
        engine_diag = {"engine": "baidu"}

    # Engine 2: Baidu table OCR (existing behavior)
    if selected_engine == "baidu":
        access_token = get_access_token()
        if not access_token:
            raise HTTPException(status_code=500, detail="Failed to get OCR access token")

        processed_image, preprocess_info = preprocess_image_for_ocr(image_data)
        try:
            response = http_session.post(
                f"https://aip.baidubce.com/rest/2.0/ocr/v1/table?access_token={access_token}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"image": base64.b64encode(processed_image).decode("utf-8")},
                timeout=45,
            )
            ocr_raw_result = response.json()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"OCR request failed: {exc}")

        if "tables_result" not in ocr_raw_result:
            return {
                "success": False,
                "error": "OCR recognition failed",
                "detail": ocr_raw_result.get("error_msg", "unknown_error"),
                "enhancement": {
                    "applied": False,
                    "corrections": [],
                    "table_structure": {},
                    "split_info": {"was_split": False, "table_count": 0},
                    "error": None,
                    "diagnostics": {
                        "preprocess": preprocess_info,
                        "timing_ms": {"total": int((time.perf_counter() - started_at) * 1000)},
                        **engine_diag,
                    },
                },
            }

        data_matrix = process_table_data(ocr_raw_result["tables_result"])
        if not data_matrix:
            return {"success": False, "error": "No valid table content extracted"}
    else:
        # Selected engine was PP-Structure and produced a matrix above.
        pass

    rule_result = repair_table_structure(data_matrix)
    working_table = rule_result["table"]
    final_result = {
        "enhanced_table": working_table,
        "corrections": rule_result.get("corrections", []),
        "table_structure": {
            "headers": working_table[0] if working_table else [],
            "data_types": [],
            "estimated_columns": len(working_table[0]) if working_table else 0,
        },
        "split_info": {"was_split": False, "table_count": 1},
        "diagnostics": {
            "numeric_columns": rule_result.get("numeric_columns", []),
            "suspicious_rows": rule_result.get("suspicious_rows", []),
            "llm_used": False,
        },
    }

    if enhance:
        try:
            final_result = llm_enhancer.enhance_table_data(working_table, ocr_raw_result)
        except Exception as exc:
            logger.exception("LLM enhancement failed: %s", exc)
            final_result["error"] = f"llm_enhance_failed: {exc}"

    enhanced_table = final_result.get("enhanced_table", working_table)
    split_tables = split_table_by_repeated_headers(enhanced_table)
    if len(split_tables) > 1:
        final_result = merge_split_results(
            [
                {
                    "enhanced_table": split_table,
                    "corrections": final_result.get("corrections", []),
                    "table_structure": {
                        "headers": split_table[0] if split_table else [],
                        "data_types": [],
                        "estimated_columns": len(split_table[0]) if split_table else 0,
                    },
                }
                for split_table in split_tables
            ]
        )
        enhanced_table = final_result.get("enhanced_table", enhanced_table)

    enhancement_payload = {
        "applied": bool(final_result.get("diagnostics", {}).get("llm_used")),
        "corrections": final_result.get("corrections", []),
        "table_structure": final_result.get("table_structure", {}),
        "split_info": final_result.get("split_info", {"was_split": False, "table_count": 1}),
        "error": final_result.get("error"),
        "diagnostics": {
            **final_result.get("diagnostics", {}),
            "preprocess": preprocess_info,
            "timing_ms": {"total": int((time.perf_counter() - started_at) * 1000)},
            **engine_diag,
        },
    }

    if enhancement_payload["split_info"].get("was_split") and enhancement_payload["split_info"].get("table_count", 0) > 1:
        split_tables = split_table_by_repeated_headers(enhanced_table)
        return {
            "success": True,
            "data": {
                "tables": [build_table_response(table) for table in split_tables],
                "is_split": True,
                "table_count": len(split_tables),
            },
            "enhancement": enhancement_payload,
        }

    return {
        "success": True,
        "data": {
            **build_table_response(enhanced_table),
            "original_headers": data_matrix[0] if data_matrix else [],
            "original_rows": data_matrix[1:] if len(data_matrix) > 1 else [],
        },
        "enhancement": enhancement_payload,
    }


@app.post("/api/synthesize")
async def synthesize_table(text: str):
    if not text or len(text.strip()) < 10:
        return {"success": False, "error": "Input text is too short"}

    try:
        synthesis_result = llm_enhancer.synthesize_table_from_text(text)
        synthesized_table = synthesis_result.get("synthesized_table", [])
        confidence = synthesis_result.get("confidence", 0.0)
        if synthesized_table:
            return {
                "success": True,
                "data": build_table_response(synthesized_table),
                "synthesis": {
                    "confidence": confidence,
                    "extracted_info": synthesis_result.get("extracted_info", {}),
                    "error": synthesis_result.get("error"),
                },
            }
        return {
            "success": False,
            "error": "Failed to synthesize table from text",
            "detail": synthesis_result.get("error", "unknown_error"),
        }
    except Exception as exc:
        return {"success": False, "error": f"Synthesis failed: {exc}"}


@app.get("/")
async def root():
    return {"message": "Gaokao OCR service API"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
