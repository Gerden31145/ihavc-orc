# 🚀 快速开始

## 5分钟快速上手高考分数线OCR工具

### 第一步：安装依赖

**1. Python依赖（首次运行）**
```bash
pip install fastapi uvicorn python-multipart requests
```

**2. 前端依赖（首次运行）**
```bash
npm install
```

### 第二步：启动服务

**方式一：一键启动（推荐）**
```bash
# Windows
双击 start.bat

# Mac/Linux
chmod +x start.sh && ./start.sh
```

**方式二：手动启动**
```bash
# 终端1：启动后端
python ocr_api.py

# 终端2：启动前端
npm run dev
```

### 第三步：开始使用

1. **打开浏览器**
   ```
   http://localhost:5173
   ```

2. **上传图片**
   - 点击上传区域
   - 选择表格图片

3. **开始识别**
   - 点击"开始识别"按钮
   - 等待3-10秒

4. **导出结果**
   - 点击"导出CSV"
   - 在下载文件夹找到文件

## ✅ 测试

使用 `test-images` 目录中的示例图片进行测试，或上传您自己的表格图片。

## 🎯 完成！

现在您已经成功运行了OCR工具。查看 `USAGE.md` 了解更多使用技巧。

---

**遇到问题？** 查看 `USAGE.md` 中的常见问题部分。
