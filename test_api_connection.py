#!/usr/bin/env python3
"""
测试DeepSeek API连接
"""
import requests
import json

API_KEY = "sk-d114b6faaa5942969eaaba903080c713"
BASE_URL = "https://api.deepseek.com"

def test_api_connection():
    """测试API连接"""
    print("=" * 50)
    print("测试DeepSeek API连接")
    print("=" * 50)

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # 简单的测试请求
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个测试助手"
            },
            {
                "role": "user",
                "content": "请回复'连接成功'"
            }
        ],
        "max_tokens": 50,
        "temperature": 0.1
    }

    print(f"\n正在请求URL: {url}")
    print(f"使用API密钥: {API_KEY[:10]}...{API_KEY[-10:]}")

    try:
        print("\n发送请求...")
        response = requests.post(url, headers=headers, json=payload, timeout=10)

        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")

        if response.status_code == 200:
            result = response.json()
            print("\n[SUCCESS] API connection successful!")
            print(f"Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            print(f"\n[FAILED] API call failed!")
            print(f"Response: {response.text}")

    except requests.exceptions.Timeout:
        print("\n[TIMEOUT] Request timed out - possible network issue")
    except requests.exceptions.ConnectionError as e:
        print(f"\n[CONNECTION ERROR] Connection failed: {e}")
    except Exception as e:
        print(f"\n[ERROR] An error occurred: {e}")

if __name__ == "__main__":
    test_api_connection()
