# 🛠 开发指南

## 项目架构

### 整体架构

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Vue 3     │────────▶│  FastAPI    │────────▶│ 百度OCR API │
│   Frontend  │         │   Backend   │         │   Service   │
└─────────────┘         └─────────────┘         └─────────────│
     :5173                   :8000                    :https
```

### 数据流

1. 用户上传图片 → 前端预览
2. 前端发送图片 → FastAPI后端
3. 后端调用 → 百度OCR API
4. OCR返回结果 → 后端处理
5. 后端返回数据 → 前端展示

## 前端开发

### 目录结构

```
src/
├── components/
│   └── OcrTable.vue         # OCR主要组件
├── App.vue                  # 应用根组件
├── main.ts                  # 应用入口
└── style.css                # 全局样式
```

### 核心组件：OcrTable.vue

**状态管理：**
```typescript
// 图片相关
isDragOver        // 拖拽状态
isLoading         // 加载状态
previewImage      // 图片预览URL
selectedFile      // 选中的文件对象

// 数据相关
tableData         // 识别结果
errorMessage      // 错误信息
```

**主要方法：**
- `processFile()` - 处理上传的文件
- `startOcr()` - 调用OCR识别
- `exportCsv()` - 导出CSV文件

### 样式约定

- **BEM命名规范** - 块、元素、修饰符
- **响应式设计** - 移动端优先
- **渐变主题** - 紫色渐变背景

### 添加新功能

**1. 添加新的API接口：**
```typescript
// 在OcrTable.vue中
const newApiCall = async () => {
  const response = await fetch('http://localhost:8000/api/new-endpoint', {
    method: 'POST',
    body: formData
  })
  return await response.json()
}
```

**2. 添加新的状态：**
```typescript
const newState = ref('')
```

**3. 添加新的UI元素：**
```vue
<div class="new-element">{{ newState }}</div>
```

## 后端开发

### 项目结构

```
ocr_api.py                 # FastAPI主应用
├── app                    # FastAPI实例
├── get_access_token()     # 获取百度API令牌
├── process_table_data()   # 处理OCR返回数据
└── /api/ocr               # OCR识别接口
```

### 核心函数

**1. get_access_token()**
```python
def get_access_token():
    """获取百度API访问令牌"""
    # 实现OAuth2.0认证
```

**2. process_table_data()**
```python
def process_table_data(tables_result):
    """处理百度OCR返回的表格数据"""
    # 将OCR结果转换为矩阵格式
```

**3. /api/ocr 接口**
```python
@app.post("/api/ocr")
async def ocr_table(file: UploadFile = File(...)):
    """接收图片文件，返回识别结果"""
```

### 添加新的API端点

```python
@app.post("/api/new-endpoint")
async def new_endpoint(data: SomeModel):
    """新的API端点"""
    return {"success": True, "data": data}
```

### 数据模型

**请求模型：**
```python
from pydantic import BaseModel

class OcrRequest(BaseModel):
    image: str  # base64编码的图片
```

**响应模型：**
```python
class OcrResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
```

## 开发工作流

### 本地开发

1. **启动开发服务器**
   ```bash
   # 后端
   python ocr_api.py

   # 前端
   npm run dev
   ```

2. **代码修改**
   - 前端修改会自动热重载
   - 后端修改需要重启服务器

3. **测试功能**
   - 访问 http://localhost:5173
   - 上传测试图片

### 调试技巧

**前端调试：**
```typescript
// 在组件中添加console.log
console.log('调试信息:', data)

// 使用Vue Devtools
// 浏览器扩展安装Vue Devtools
```

**后端调试：**
```python
# 添加日志
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("调试信息")
```

### 代码规范

**前端：**
- 使用TypeScript类型注解
- 组件使用Composition API
- Props需要定义类型

**后端：**
- 使用类型注解
- 异步函数使用async/await
- 错误处理要完整

## 测试

### 前端测试

```bash
# 单元测试（待实现）
npm run test

# E2E测试（待实现）
npm run test:e2e
```

### 后端测试

```bash
# 手动测试
curl -X POST "http://localhost:8000/api/ocr" \
  -F "file=@test-image.jpg"
```

## 部署

### 前端部署

```bash
# 构建
npm run build

# 部署dist目录到静态服务器
```

### 后端部署

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python ocr_api.py

# 或使用gunicorn（生产环境）
gunicorn ocr_api:app -w 4 -k uvicorn.workers.UvicornWorker
```

## 常见开发任务

### 修改API端口

**后端：**
```python
# ocr_api.py
uvicorn.run(app, host="0.0.0.0", port=3000)  # 改为3000
```

**前端：**
```typescript
// OcrTable.vue
const response = await fetch('http://localhost:3000/api/ocr', {
```

### 更换OCR服务

1. 在`ocr_api.py`中修改OCR调用逻辑
2. 保持返回格式不变
3. 测试识别结果

### 添加新的导出格式

```typescript
// 在OcrTable.vue中添加
const exportExcel = () => {
  // 实现Excel导出逻辑
}
```

## 性能优化

### 前端优化

- 图片压缩后再上传
- 使用Web Worker处理大文件
- 添加请求缓存

### 后端优化

- 添加异步处理队列
- 实现结果缓存
- 限流保护

## 安全考虑

1. **API密钥保护**
   - 使用环境变量
   - 不提交到git

2. **文件验证**
   - 验证文件类型
   - 限制文件大小

3. **CORS配置**
   - 生产环境限制来源
   - 不使用通配符

## 贡献指南

1. Fork项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

---

**Happy Coding! 🚀**
