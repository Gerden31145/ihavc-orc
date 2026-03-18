from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import base64
import requests
import uvicorn

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


def process_table_data(tables_result):
    """处理百度OCR返回的表格数据"""
    if not tables_result:
        return None

    cells = tables_result[0].get('body', [])

    # 找出最大行和最大列
    max_row = max([cell['row_end'] for cell in cells]) + 1
    max_col = max([cell['col_end'] for cell in cells]) + 1

    # 初始化空白矩阵
    matrix = [["" for _ in range(max_col)] for _ in range(max_row)]

    # 填充数据
    for cell in cells:
        r = cell['row_start']
        c = cell['col_start']
        text = cell['words']
        matrix[r][c] = text

    return matrix


@app.post("/api/ocr")
async def ocr_table(file: UploadFile = File(...)):
    """
    OCR识别表格图片
    """
    # 验证文件类型
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="只支持图片文件")

    # 获取访问令牌
    access_token = get_access_token()
    if not access_token:
        raise HTTPException(status_code=500, detail="获取OCR服务令牌失败")

    # 读取图片并转换为base64
    try:
        image_data = await file.read()
        base64_str = base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    # 调用百度OCR API
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/table?access_token={access_token}"
    payload = {'image': base64_str}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    try:
        response = requests.post(url, headers=headers, data=payload)
        result = response.json()

        if "tables_result" in result:
            # 处理表格数据
            data_matrix = process_table_data(result["tables_result"])

            if data_matrix:
                return {
                    "success": True,
                    "data": {
                        "headers": data_matrix[0] if data_matrix else [],
                        "rows": data_matrix[1:] if len(data_matrix) > 1 else []
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "未能提取到有效表格内容"
                }
        else:
            return {
                "success": False,
                "error": "OCR识别失败",
                "detail": result.get("error_msg", "未知错误")
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR服务调用失败: {str(e)}")


@app.get("/")
async def root():
    return {"message": "高考分数线OCR服务API"}


if __name__ == '__main__':
    print("启动OCR服务...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
