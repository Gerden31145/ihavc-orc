import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

from ocr_postprocess import compact_ocr_context, repair_table_structure, summarize_row_issues

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def try_fix_json(json_str: str) -> str:
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass

    fixed = json_str
    fixed = re.sub(r"}\s*\"", '}, "', fixed)
    fixed = re.sub(r"]\s*\"", '], "', fixed)
    fixed = re.sub(r'"\s*{', '", {', fixed)
    fixed = re.sub(r'"\s*\[', '", [', fixed)
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
    return fixed


class LLMEnhancer:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def call_llm(self, prompt: str, max_tokens: int = 2500) -> Optional[str]:
        if not self.api_key:
            return None

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You repair OCR table rows. Return JSON only. "
                        "Keep row and column counts unchanged."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=45,
            )
            if response.status_code != 200:
                logger.error("LLM call failed: %s %s", response.status_code, response.text)
                return None

            result = response.json()
            choices = result.get("choices") or []
            if not choices:
                return None
            return choices[0]["message"]["content"]
        except requests.RequestException as exc:
            logger.error("LLM request failed: %s", exc)
            return None

    def enhance_table_data(self, table_data: List[List[str]], original_ocr_result: Dict[str, Any]) -> Dict[str, Any]:
        repaired = repair_table_structure(table_data)
        working_table = repaired["table"]
        corrections = list(repaired["corrections"])
        suspicious_rows = repaired["suspicious_rows"]

        result = {
            "enhanced_table": working_table,
            "corrections": corrections,
            "table_structure": self._build_table_structure(working_table),
            "diagnostics": {
                "numeric_columns": repaired["numeric_columns"],
                "suspicious_rows": suspicious_rows,
                "llm_used": False,
            },
        }

        if not working_table:
            result["error"] = "empty_table"
            return result

        if not suspicious_rows:
            result["diagnostics"]["llm_skipped_reason"] = "no_suspicious_rows"
            return result

        llm_response = self.call_llm(
            self._build_row_repair_prompt(working_table, suspicious_rows, original_ocr_result)
        )
        if not llm_response:
            result["error"] = "llm_call_failed"
            return result

        parsed = self._parse_llm_response(llm_response)
        if not parsed:
            result["error"] = "llm_response_invalid"
            return result

        applied_rows = 0
        for patch in parsed.get("row_patches", []):
            row_index = patch.get("row_index")
            values = patch.get("values")
            reason = patch.get("reason", "llm_row_repair")
            confidence = float(patch.get("confidence", 0.0))

            if not isinstance(row_index, int) or row_index <= 0 or row_index >= len(working_table):
                continue
            if row_index not in suspicious_rows or not isinstance(values, list):
                continue
            if len(values) != len(working_table[0]) or confidence < 0.6:
                continue

            normalized_values = ["" if value is None else str(value).strip() for value in values]
            original_row = working_table[row_index][:]
            if normalized_values == original_row:
                continue

            working_table[row_index] = normalized_values
            corrections.append(
                {
                    "original": " | ".join(original_row),
                    "corrected": " | ".join(normalized_values),
                    "reason": reason,
                }
            )
            applied_rows += 1

        result["enhanced_table"] = working_table
        result["corrections"] = corrections
        result["table_structure"] = self._build_table_structure(working_table)
        result["diagnostics"]["llm_used"] = applied_rows > 0
        result["diagnostics"]["llm_applied_rows"] = applied_rows
        if applied_rows == 0:
            result["diagnostics"]["llm_skipped_reason"] = "no_high_confidence_patch"
        return result

    def synthesize_table_from_text(self, text_content: str) -> Dict[str, Any]:
        prompt = (
            "Extract a structured table from the text below and return JSON only.\n"
            f"Text:\n{text_content}\n"
            'Return {"synthesized_table":[["header"]],"confidence":0.0,"extracted_info":{}}'
        )
        llm_response = self.call_llm(prompt, max_tokens=1800)
        if not llm_response:
            return {"synthesized_table": [], "confidence": 0.0, "error": "llm_call_failed"}

        parsed = self._parse_llm_response(llm_response, allow_generic=True)
        if not parsed:
            return {"synthesized_table": [], "confidence": 0.0, "error": "llm_response_invalid"}
        return parsed

    def _build_row_repair_prompt(
        self,
        table_data: List[List[str]],
        suspicious_rows: List[int],
        original_ocr_result: Dict[str, Any],
    ) -> str:
        headers = json.dumps(table_data[0], ensure_ascii=False)
        issues = summarize_row_issues(table_data, suspicious_rows)
        issue_lines = [
            f"row {item['row_index']}: {json.dumps(item['row'], ensure_ascii=False)}; issues={item['issues']}"
            for item in issues
        ]
        focused_context = compact_ocr_context(original_ocr_result, suspicious_rows)
        return (
            "Repair only the suspicious OCR rows below.\n"
            "Keep the number of columns unchanged.\n"
            "Only fill values when the OCR context makes them plausible.\n"
            "If uncertain, keep the original text.\n\n"
            f"Headers: {headers}\n"
            f"Suspicious rows:\n{os.linesep.join(issue_lines)}\n\n"
            f"OCR cell context:\n{focused_context}\n\n"
            'Return JSON: {"row_patches":[{"row_index":1,"values":["..."],"reason":"...","confidence":0.0}]}'
        )

    def _parse_llm_response(self, response_text: str, allow_generic: bool = False) -> Optional[Dict[str, Any]]:
        cleaned = re.sub(r"```json\s*|```", "", response_text).strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None

        candidate = match.group(0)
        for possible_json in (candidate, try_fix_json(candidate)):
            try:
                parsed = json.loads(possible_json)
                if os.getenv("DEBUG_LLM_DUMP") == "1":
                    with open("llm_response_raw.txt", "w", encoding="utf-8") as handle:
                        handle.write(response_text)
                if allow_generic or "row_patches" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _build_table_structure(self, table_data: List[List[str]]) -> Dict[str, Any]:
        headers = table_data[0] if table_data else []
        data_types = []
        for column_index, _ in enumerate(headers):
            data_types.append("number" if self._column_looks_numeric(table_data, column_index) else "string")
        return {
            "headers": headers,
            "data_types": data_types,
            "estimated_columns": len(headers),
        }

    def _column_looks_numeric(self, table_data: List[List[str]], column_index: int) -> bool:
        values = []
        for row in table_data[1:]:
            if column_index < len(row) and row[column_index]:
                values.append(row[column_index])
        if not values:
            return False
        numeric_like = sum(1 for value in values if re.fullmatch(r"[\d.\-\n ]+", value))
        return numeric_like / len(values) >= 0.6
