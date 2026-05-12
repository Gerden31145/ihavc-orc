# CLAUDE.md

## 项目概述

高考分数线表格 OCR 提取工具。Vue 3 + Vite 前端，Python FastAPI 后端。

## 启动方式

### 后端（Python FastAPI）
```bash
python ocr_api.py
# 运行在 http://localhost:8000
```

### 前端（Vue 3 + Vite）
```bash
npm run dev
# 运行在 http://localhost:5173
```

两个服务都需要启动，分别在后台运行即可。

## 关键文件

- `ocr_api.py` — 后端 OCR API 服务
- `src/` — 前端 Vue 源码
- `llm_enhancer.py` — DeepSeek LLM 表格增强
- `table_splitter.py` — 多表格拆分逻辑
- `requirements.txt` — Python 依赖
- `package.json` — 前端依赖

## Git 规范

- commit message 不要加 Claude 水印（不要加 `Co-Authored-By` 行）
