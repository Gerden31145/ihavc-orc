# 🎓 高考分数线 OCR 提取工具

> 一个基于 Vue 3 + FastAPI + 百度OCR 的表格图片识别提取工具，将图片中的表格数据自动转换为结构化数据。

[![Vue 3](https://img.shields.io/badge/Vue-3-42b883)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## ✨ 功能特性

- ✅ **图片上传** - 支持点击选择和拖拽上传
- ✅ **OCR识别** - 基于百度OCR的高精度表格识别
- ✅ **实时预览** - 上传后立即预览图片
- ✅ **结果展示** - 清晰的表格展示识别结果
- ✅ **CSV导出** - 一键导出识别数据
- ✅ **响应式设计** - 美观的渐变UI设计

## 🛠 技术栈

### 前端
- **Vue 3** - 渐进式JavaScript框架
- **TypeScript** - 类型安全的JavaScript超集
- **Vite** - 新一代前端构建工具

### 后端
- **FastAPI** - 现代化的Python Web框架
- **百度OCR API** - 强大的表格识别能力
- **Uvicorn** - ASGI服务器

## 🚀 快速开始

> 💡 **提示：** 首次使用请查看 [QUICKSTART.md](QUICKSTART.md) 获取详细的5分钟上手指南

### 环境要求

- **Python** >= 3.8
- **Node.js** >= 16.0
- **npm** >= 7.0

### 1. 克隆项目

```bash
git clone <repository-url>
cd ocr-project
```

### 2. 安装依赖

**前端依赖：**
```bash
npm install
```

**后端依赖：**
```bash
pip install -r requirements.txt
```

### 3. 启动服务

**一键启动（推荐）：**
```bash
# Windows
start.bat

# Mac/Linux
chmod +x start.sh && ./start.sh
```

**手动启动：**
```bash
# 终端1：启动后端服务
python ocr_api.py

# 终端2：启动前端服务
npm run dev
```

### 4. 访问应用

打开浏览器访问：**http://localhost:5173**

## 📖 使用方法

1. **上传图片** - 点击上传区域或拖拽图片文件
2. **预览图片** - 确认上传的图片是否正确
3. **开始识别** - 点击"开始识别"按钮，等待OCR处理
4. **查看结果** - 在表格中查看识别的数据
5. **导出数据** - 点击"导出CSV"保存到本地

## 📁 项目结构

```
ocr-project/
├── src/
│   ├── components/
│   │   └── OcrTable.vue         # OCR主组件
│   ├── App.vue                  # 应用主组件
│   ├── main.ts                  # 应用入口
│   └── style.css                # 全局样式
├── public/                      # 静态资源
├── test-images/                 # 测试图片目录
├── ocr_api.py                   # FastAPI后端服务
├── ocr_server.py                # 原始OCR脚本
├── requirements.txt             # Python依赖
├── package.json                 # 前端依赖配置
├── README.md                    # 项目说明
├── QUICKSTART.md                # 快速开始指南
└── USAGE.md                     # 详细使用指南
```

## 🔌 API接口

### POST /api/ocr

识别表格图片

**请求参数：**
- `file`: 图片文件（multipart/form-data）

**响应示例：**
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

**错误响应：**
```json
{
  "success": false,
  "error": "识别失败"
}
```

## ⚙️ 配置说明

### 修改OCR API密钥

编辑 `ocr_api.py` 文件：

```python
API_KEY = "your-api-key"
SECRET_KEY = "your-secret-key"
```

### 修改端口

**后端端口（默认8000）：**
```python
# ocr_api.py 最后一行
uvicorn.run(app, host="0.0.0.0", port=8000)
```

**前端端口（默认5173）：**
```typescript
// vite.config.ts
export default defineConfig({
  server: {
    port: 3000  // 修改为其他端口
  }
})
```

## 📸 图片要求

- **格式**: JPG、PNG
- **分辨率**: 建议 1024x768 以上
- **内容**: 清晰的表格结构
- **光线**: 充足且均匀
- **角度**: 尽量平整，避免倾斜

## 🗺 路线图

### ✅ Phase 1（已完成）
- [x] 图片上传
- [x] OCR识别
- [x] 结果展示
- [x] CSV导出

### 🚧 Phase 2（计划中）
- [ ] 表格可编辑
- [ ] 数据校验
- [ ] Excel导出
- [ ] 批量上传

### 🎯 Phase 3（未来）
- [ ] 原图对照
- [ ] 历史记录
- [ ] 用户认证
- [ ] 数据可视化

## ❓ 常见问题

<details>
<summary><b>Q: 提示"连接OCR服务失败"怎么办？</b></A>

**A:** 请确保后端服务已启动：
1. 检查是否有运行 `python ocr_api.py` 的终端
2. 确认端口8000未被占用
3. 查看后端终端是否有错误信息
</details>

<details>
<summary><b>Q: 识别结果不准确怎么办？</b></A>

**A:** 尝试以下方法：
1. 使用更高分辨率的图片
2. 确保图片光线充足、表格清晰
3. 避免图片倾斜或扭曲
4. 使用图片编辑工具预处理
</details>

<details>
<summary><b>Q: 支持哪些图片格式？</b></A>

**A:** 目前支持 JPG 和 PNG 格式。其他格式需要先转换。
</details>

## 📄 许可证

[MIT License](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 提交 Issue
- 发送邮件
- 加入讨论组

---

**⭐ 如果这个项目对您有帮助，请给个 Star！**
