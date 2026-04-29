# 使用指南

## 📸 准备测试图片

在项目根目录创建 `test-images` 文件夹，将需要识别的表格图片放入其中。

建议图片要求：
- 分辨率：至少 1024x768
- 格式：JPG 或 PNG
- 内容：清晰的表格结构
- 文字：尽量清晰，避免模糊

## 🚀 快速启动

### 方法一：使用启动脚本（推荐）

双击 `start.bat` 文件，将自动启动前后端服务。

### 方法二：手动启动

**启动后端：**
```bash
python ocr_api.py
```

**启动前端（新终端）：**
```bash
npm run dev
```

## 💡 使用流程

1. **打开应用**
   - 浏览器访问 `http://localhost:5173`

2. **上传图片**
   - 点击上传区域选择图片
   - 或直接拖拽图片到上传区域

3. **开始识别**
   - 点击"开始识别"按钮
   - 等待识别完成（约3-10秒）

4. **查看结果**
   - 识别结果将以表格形式展示
   - 可以直接在页面中查看

5. **导出数据**
   - 点击"导出 CSV"按钮
   - 数据将保存到本地下载文件夹

## ⚠️ 常见问题

### 1. 连接失败
**问题：** 提示"连接OCR服务失败"
**解决：** 确保后端服务已启动（检查是否有 http://localhost:8000 的终端窗口）

### 2. 识别结果不准确
**问题：** 识别的文字或表格结构有误
**解决：**
- 尝试使用更清晰的图片
- 确保图片光线充足
- 避免图片倾斜或扭曲

### 3. 接口调用失败
**问题：** 提示"获取OCR服务令牌失败"
**解决：** 检查百度OCR API密钥是否有效，或在 `ocr_api.py` 中更新密钥

## 🔧 配置说明

### 修改端口

**后端端口（默认8000）：**
编辑 `ocr_api.py` 文件最后一行：
```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # 修改 8000 为其他端口
```

**前端端口（默认5173）：**
编辑 `vite.config.ts` 文件，添加：
```typescript
server: {
  port: 3000  // 修改为其他端口
}
```

### 更换OCR服务

当前使用百度OCR API，如需更换：

1. 编辑 `ocr_api.py`
2. 修改 `API_KEY` 和 `SECRET_KEY`
3. 或替换整个OCR调用逻辑

## 🧩 使用 PP-Structure（PaddleOCR）优化结构化提取（可选）

当图片里同时包含标题/多块内容、表格线不完整、或需要更稳定的版面结构化时，建议试试 `PP-Structure`。

### 启用方式

- **方式一：请求参数**：调用 `/api/ocr` 时加 `engine=ppstructure`
- **方式二：环境变量**：设置 `OCR_ENGINE=ppstructure` 作为默认引擎

如果本机没有安装 PaddleOCR / PaddlePaddle，服务会**自动回退到百度 OCR**，并在返回的 `enhancement.diagnostics` 里给出回退原因。

### 依赖安装（Windows）

1. 先按 PaddlePaddle 官方文档安装 `paddlepaddle`（CPU 或 GPU 版本）
2. 再安装：

```bash
pip install paddleocr lxml
```

### 输出差异

PP-Structure 会在 `enhancement.diagnostics` 中附加：

- `engine`: `ppstructure` / `ppstructure_fallback_to_baidu`
- `ppstructure`: `tables_found` / `blocks_found` / `timing_ms` / `error`

## 📊 数据格式

识别结果返回JSON格式：
```json
{
  "success": true,
  "data": {
    "headers": ["年份", "省份", "科类", "批次", "分数"],
    "rows": [
      ["2023", "河南", "理科", "一本", "514"],
      ["2023", "河南", "文科", "一本", "547"]
    ]
  }
}
```

## 🎯 下一步

- [ ] 尝试不同类型的表格图片
- [ ] 批量处理多个图片
- [ ] 导出数据进行数据分析
- [ ] 根据需求自定义识别规则

## 📞 技术支持

如遇到问题，请检查：
1. Python 版本 >= 3.8
2. Node.js 版本 >= 16.0
3. 网络连接正常
4. API 密钥有效
