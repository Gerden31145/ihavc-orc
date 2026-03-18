# 🎓 高考分数线 OCR 提取工具

> 将图片中的表格数据自动转换为结构化数据，基于 Vue 3 + FastAPI + 百度OCR

[![Vue 3](https://img.shields.io/badge/Vue-3-42b883)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688)](https://fastapi.tiangolo.com/)

## ✨ 功能特性

- ✅ 图片上传（支持拖拽）
- ✅ OCR 表格识别
- ✅ 实时预览
- ✅ 结果展示
- ✅ CSV 导出

## 🚀 快速开始

### 环境要求

- Python >= 3.8
- Node.js >= 16.0

### 安装依赖

```bash
# 前端依赖
npm install

# 后端依赖
pip install -r requirements.txt
```

### 启动服务

```bash
# 一键启动（Windows）
start.bat

# 或手动启动
python ocr_api.py        # 终端1
npm run dev             # 终端2
```

### 访问应用

打开浏览器：**http://localhost:5173**

## 📖 详细文档

- [完整项目文档](PROJECT_README.md) - 项目介绍和API文档
- [快速开始指南](QUICKSTART.md) - 5分钟上手教程
- [使用指南](USAGE.md) - 详细使用说明和常见问题

## 📸 使用方法

1. 上传表格图片
2. 点击"开始识别"
3. 查看识别结果
4. 导出CSV文件

## 🛠 技术栈

**前端：** Vue 3 + TypeScript + Vite
**后端：** FastAPI + 百度OCR API

## 📄 License

MIT
