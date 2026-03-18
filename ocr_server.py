import requests
import base64
import os
import pandas as pd

# 你的百度云 API 信息
API_KEY = "oRirY5AYCHC7giulzzLj4jFV"
SECRET_KEY = "OHkKy4zC8rSKulma0XQOQ04mn1RACtfl"


def get_access_token():
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
    res = requests.post(url, params=params).json()
    return res.get("access_token")


def process_table_data(tables_result):
    """
    核心修改：将百度返回的 JSON 文字块按照行列坐标填入表格
    """
    if not tables_result:
        return None

    # 百度可能返回多个表格，我们取第一个
    cells = tables_result[0].get('body', [])

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


def upload_and_convert(image_path):
    access_token = get_access_token()
    if not access_token:
        print("Token 获取失败")
        return

    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/table?access_token=" + access_token

    try:
        with open(image_path, 'rb') as f:
            base64_str = base64.b64encode(f.read()).decode('utf-8')
    except FileNotFoundError:
        print("错误：找不到图片文件。")
        return

    payload = {'image': base64_str}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    print(f"正在识别: {image_path} ...")
    response = requests.post(url, headers=headers, data=payload)
    result = response.json()

    # 逻辑改动：如果有识别结果，即使没有 excel_url 也手动生成
    if "tables_result" in result:
        print("识别成功，正在处理数据...")
        data_matrix = process_table_data(result["tables_result"])

        if data_matrix:
            # 使用 pandas 保存
            df = pd.DataFrame(data_matrix)
            output_file = "output_table_manual.xlsx"
            df.to_excel(output_file, index=False, header=False)
            print(f"表格已成功生成并保存至: {os.path.abspath(output_file)}")
        else:
            print("未能提取到有效单元格内容。")
    else:
        print("接口调用失败或未发现表格。返回信息：", result)


if __name__ == '__main__':
    my_image = "59d2391d1a1440a6b2e11e5b3ed6f028.jpg"
    upload_and_convert(my_image)