#!/usr/bin/env python3
"""
测试LLM集成功能的脚本
"""

import requests
import json

def test_llm_enhancer_direct():
    """直接测试LLM增强器"""
    print("=== 测试LLM增强器 ===")
    
    try:
        from llm_enhancer import LLMEnhancer
        
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
        
        print("原始表格数据:")
        for row in test_table:
            print(" | ".join(str(cell) if cell else "[空]" for cell in row))
        
        print("\n调用LLM进行增强...")
        result = enhancer.enhance_table_data(test_table, test_ocr_result)
        
        print("\n增强结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        return True
        
    except Exception as e:
        print(f"LLM增强器测试失败: {e}")
        return False

def test_api_endpoints():
    """测试API端点"""
    print("\n=== 测试API端点 ===")
    
    base_url = "http://localhost:8000"
    
    # 测试根端点
    try:
        response = requests.get(f"{base_url}/")
        print(f"根端点响应: {response.json()}")
    except Exception as e:
        print(f"根端点测试失败: {e}")
        return False
    
    # 测试表格合成端点
    try:
        test_text = """
        以下是2023年部分高校的录取分数线：
        北京大学：理科680分，文科675分
        清华大学：理科685分，文科680分  
        复旦大学：理科675分，文科670分
        上海交通大学：理科678分，文科673分
        """
        
        response = requests.post(
            f"{base_url}/api/synthesize",
            json={"text": test_text}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("表格合成结果:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"表格合成失败: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"表格合成测试失败: {e}")
        return False
    
    return True

def main():
    """主测试函数"""
    print("开始测试LLM集成功能...")
    
    # 测试LLM增强器
    llm_test_passed = test_llm_enhancer_direct()
    
    # 测试API端点（需要先启动服务）
    print("\n注意：API端点测试需要先启动OCR服务 (python ocr_api.py)")
    print("是否要启动服务并测试？(y/n)")
    
    choice = input().strip().lower()
    if choice == 'y':
        api_test_passed = test_api_endpoints()
    else:
        api_test_passed = False
        print("跳过API端点测试")
    
    print("\n=== 测试总结 ===")
    print(f"LLM增强器测试: {'通过' if llm_test_passed else '失败'}")
    print(f"API端点测试: {'通过' if api_test_passed else '跳过/失败'}")
    
    if llm_test_passed:
        print("\n✅ LLM集成功能已成功实现！")
        print("\n使用说明:")
        print("1. 启动OCR服务: python ocr_api.py")
        print("2. 访问前端界面进行测试")
        print("3. 在前端界面中启用'LLM智能增强'开关")
        print("4. 上传表格图片进行智能识别")
    else:
        print("\n❌ LLM集成功能测试失败，请检查配置")

if __name__ == "__main__":
    main()