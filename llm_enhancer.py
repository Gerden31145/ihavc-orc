import requests
import json
import re
import logging
from typing import List, Dict, Any, Optional

def try_fix_json(json_str: str) -> str:
    """尝试修复常见的JSON格式错误"""
    try:
        # 尝试直接解析
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass

    # 常见修复策略
    fixed = json_str

    # 1. 修复缺少逗号的问题：在 } 后跟 " 之间加逗号
    fixed = re.sub(r'}\s*"', '}, "', fixed)
    fixed = re.sub(r']\s*"', '], "', fixed)

    # 2. 修复缺少逗号的问题：在 " 后跟 { 之间加逗号
    fixed = re.sub(r'"\s*{', '", {', fixed)
    fixed = re.sub(r'"\s*\[', '", [', fixed)

    # 3. 移除尾随逗号：在 } 或 ] 前的逗号
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)

    # 4. 修复缺少逗号的问题：在数字或字符串后跟 " 之间加逗号
    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
    fixed = re.sub(r':\s*\[\s*\]', ': []', fixed)
    fixed = re.sub(r':\s*\{\s*\}', ': {}', fixed)

    return fixed

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMEnhancer:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def call_llm(self, prompt: str, max_tokens: int = 8000) -> Optional[str]:
        """调用DeepSeek LLM API"""
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的表格数据处理助手，擅长纠正OCR识别错误、完善表格结构、标准化数据格式。请严格按照JSON格式返回结果。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1
        }

        try:
            logger.info(f"正在调用LLM API: {url}")
            logger.info(f"请求payload大小: {len(json.dumps(payload))} 字符")
            # 增加超时时间到120秒，因为大表格处理需要更长时间
            response = requests.post(url, headers=self.headers, json=payload, timeout=120)

            logger.info(f"LLM API响应状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                logger.info(f"API响应结构: {list(result.keys())}")
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    logger.info(f"LLM API调用成功，返回内容长度: {len(content)} 字符")
                    logger.info(f"返回内容预览: {content[:200]}...")
                    return content
                else:
                    logger.error(f"API响应格式异常，没有choices字段: {result}")
                    return None
            else:
                error_msg = f"LLM API调用失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                # 返回错误信息而不是None，以便调用者可以看到具体错误
                return None
        except requests.exceptions.Timeout:
            error_msg = "LLM API调用超时"
            logger.error(error_msg)
            return None
        except requests.exceptions.ConnectionError as e:
            error_msg = f"LLM API连接失败: {e}"
            logger.error(error_msg)
            return None
        except Exception as e:
            error_msg = f"LLM调用异常: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None
    
    def enhance_table_data(self, table_data: List[List[str]], original_ocr_result: Dict) -> Dict[str, Any]:
        """使用LLM增强表格数据"""
        
        # 准备表格数据用于LLM处理
        table_text = self._format_table_for_llm(table_data)
        ocr_context = self._extract_ocr_context(original_ocr_result)
        
        prompt = f"""请分析以下OCR识别的表格数据，并进行智能增强。

原始OCR识别结果（包含位置信息）：
{ocr_context}

提取的表格数据：
{table_text}

请执行以下任务：
1. 纠正识别错误的文字（特别是数字、专业术语）
2. 完善表格结构，填充可能的缺失单元格
3. 标准化数据格式（如统一日期、数字格式）
4. 识别表头和数据行的逻辑关系

【重要】请直接返回纯JSON格式的结果，严格遵守以下要求：
- 不要使用markdown代码块（不要用```json或```）
- 不要添加任何文字说明、解释或注释
- 直接以{{开始，以}}结束
- 确保JSON格式完全正确，可以正常解析

返回格式：
{{
    "enhanced_table": [
        ["学校名称", "录取分数线", "年份"],
        ["北京大学", "680", "2023"],
        ["清华大学", "685", "2023"]
    ],
    "corrections": [
        {{"original": "北大", "corrected": "北京大学", "reason": "规范学校名称"}},
        {{"original": "68O", "corrected": "680", "reason": "纠正数字识别错误"}}
    ],
    "table_structure": {{
        "headers": ["学校名称", "录取分数线", "年份"],
        "data_types": ["string", "integer", "year"],
        "estimated_columns": 3
    }}
}}
"""
        
        llm_response = self.call_llm(prompt)
        if not llm_response:
            error_detail = "LLM API调用失败，请检查网络连接和API密钥"
            logger.error(f"LLM增强失败: {error_detail}")
            return {
                "enhanced_table": table_data,
                "corrections": [],
                "table_structure": {
                    "headers": table_data[0] if table_data else [],
                    "data_types": [],
                    "estimated_columns": len(table_data[0]) if table_data else 0
                },
                "error": error_detail
            }

        # 检查响应是否被截断
        if not llm_response.strip().endswith('}'):
            error_detail = f"LLM响应被截断（完整响应需要更多tokens），当前长度: {len(llm_response)}"
            logger.error(f"LLM增强失败: {error_detail}")
            logger.error(f"响应结尾: ...{llm_response[-200:]}")
            return {
                "enhanced_table": table_data,
                "corrections": [],
                "table_structure": {
                    "headers": table_data[0] if table_data else [],
                    "data_types": [],
                    "estimated_columns": len(table_data[0]) if table_data else 0
                },
                "error": error_detail
            }

        # 解析LLM响应
        try:
            logger.info("开始解析LLM响应...")

            # 保存原始响应用于调试
            with open('llm_response_raw.txt', 'w', encoding='utf-8') as f:
                f.write(llm_response)
            logger.info("原始响应已保存到 llm_response_raw.txt")

            # 移除markdown代码块标记
            cleaned_response = llm_response
            # 移除 ```json 和 ``` 标记
            cleaned_response = re.sub(r'```json\s*', '', cleaned_response)
            cleaned_response = re.sub(r'```\s*', '', cleaned_response)
            cleaned_response = cleaned_response.strip()

            logger.info(f"清理后的响应长度: {len(cleaned_response)} 字符")
            logger.info(f"响应开头: {cleaned_response[:200]}...")

            # 尝试提取JSON部分（找到第一个 { 和最后一个 }）
            json_match = re.search(r'\{[\s\S]*\}', cleaned_response)
            if json_match:
                json_str = json_match.group()
                logger.info(f"提取的JSON长度: {len(json_str)} 字符")

                # 保存提取的JSON用于调试
                with open('llm_response_extracted.json', 'w', encoding='utf-8') as f:
                    f.write(json_str)
                logger.info("提取的JSON已保存到 llm_response_extracted.json")

                # 先尝试直接解析
                try:
                    enhanced_result = json.loads(json_str)
                    logger.info("JSON解析成功（直接解析）")
                    return enhanced_result
                except json.JSONDecodeError as e:
                    logger.warning(f"直接解析失败: {e}，尝试修复JSON...")

                    # 尝试修复JSON
                    fixed_json = try_fix_json(json_str)

                    # 保存修复后的JSON用于调试
                    with open('llm_response_fixed.json', 'w', encoding='utf-8') as f:
                        f.write(fixed_json)
                    logger.info("修复后的JSON已保存到 llm_response_fixed.json")

                    try:
                        enhanced_result = json.loads(fixed_json)
                        logger.info("JSON解析成功（修复后）")
                        return enhanced_result
                    except json.JSONDecodeError as e2:
                        logger.error(f"修复后仍然解析失败: {e2}")
                        raise e2
            else:
                # 如果无法解析为JSON，返回原始数据
                logger.error("无法在响应中找到有效的JSON结构")
                print("无法解析LLM响应为JSON")
                return {
                    "enhanced_table": table_data,
                    "corrections": [],
                    "table_structure": {
                        "headers": table_data[0] if table_data else [],
                        "data_types": [],
                        "estimated_columns": len(table_data[0]) if table_data else 0
                    },
                    "error": "LLM响应格式错误"
                }
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            logger.error(f"错误的JSON片段: {cleaned_response[:500] if 'cleaned_response' in locals() else llm_response[:500]}")
            print(f"JSON解析错误: {e}")
            return {
                "enhanced_table": table_data,
                "corrections": [],
                "table_structure": {
                    "headers": table_data[0] if table_data else [],
                    "data_types": [],
                    "estimated_columns": len(table_data[0]) if table_data else 0
                },
                "error": f"JSON解析失败: {e}"
            }
    
    def synthesize_table_from_text(self, text_content: str) -> Dict[str, Any]:
        """从非结构化文本中合成表格"""
        
        prompt = f"""
请从以下文本中提取表格数据并合成结构化的表格：

文本内容：
{text_content}

请分析文本中的表格信息，包括：
1. 识别表头和列名
2. 提取数据行
3. 推断数据类型和格式
4. 构建完整的二维表格结构

返回JSON格式：
{{
    "synthesized_table": [[表头], [行1], [行2], ...],
    "confidence": 置信度(0-1),
    "extracted_info": {{
        "headers": ["识别出的表头"],
        "row_count": 行数,
        "column_count": 列数,
        "data_types": ["每列的数据类型"]
    }}
}}
"""
        
        llm_response = self.call_llm(prompt)
        if not llm_response:
            return {
                "synthesized_table": [],
                "confidence": 0.0,
                "error": "LLM调用失败"
            }
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    "synthesized_table": [],
                    "confidence": 0.0,
                    "error": "无法解析响应"
                }
        except json.JSONDecodeError as e:
            return {
                "synthesized_table": [],
                "confidence": 0.0,
                "error": f"JSON解析失败: {e}"
            }
    
    def _format_table_for_llm(self, table_data: List[List[str]]) -> str:
        """格式化表格数据用于LLM处理"""
        if not table_data:
            return "空表格"
        
        # 创建表格的文本表示
        lines = []
        for i, row in enumerate(table_data):
            row_str = " | ".join(str(cell) if cell else "[空]" for cell in row)
            lines.append(f"行{i}: {row_str}")
        
        return "\n".join(lines)
    
    def _extract_ocr_context(self, ocr_result: Dict) -> str:
        """提取OCR结果的上下文信息"""
        context_parts = []
        
        if "tables_result" in ocr_result:
            tables = ocr_result["tables_result"]
            for i, table in enumerate(tables):
                context_parts.append(f"表格{i+1}:")
                if "body" in table:
                    for cell in table["body"]:
                        context_parts.append(
                            f"  位置({cell.get('row_start', '?')},{cell.get('col_start', '?')})-({cell.get('row_end', '?')},{cell.get('col_end', '?')}): {cell.get('words', '')}"
                        )
        
        return "\n".join(context_parts) if context_parts else "无详细位置信息"


def test_llm_enhancer():
    """测试LLM增强器"""
    # 使用提供的API密钥
    enhancer = LLMEnhancer(api_key="sk-d114b6faaa5942969eaaba903080c713")
    
    # 测试数据
    test_table = [
        ["学校名称", "分数线", "年份"],
        ["北京大学", "680", "2023"],
        ["清华大学", "685", ""],
        ["复旦大学", "675", "2023"]
    ]
    
    test_ocr_result = {
        "tables_result": [
            {
                "body": [
                    {"words": "学校名称", "row_start": 0, "col_start": 0, "row_end": 0, "col_end": 0},
                    {"words": "分数线", "row_start": 0, "col_start": 1, "row_end": 0, "col_end": 1},
                    {"words": "年份", "row_start": 0, "col_start": 2, "row_end": 0, "col_end": 2},
                    {"words": "北京大学", "row_start": 1, "col_start": 0, "row_end": 1, "col_end": 0},
                    {"words": "680", "row_start": 1, "col_start": 1, "row_end": 1, "col_end": 1},
                    {"words": "2023", "row_start": 1, "col_start": 2, "row_end": 1, "col_end": 2}
                ]
            }
        ]
    }
    
    result = enhancer.enhance_table_data(test_table, test_ocr_result)
    print("增强结果:", json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    test_llm_enhancer()