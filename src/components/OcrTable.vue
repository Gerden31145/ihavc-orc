<template>
  <div class="ocr-container">
    <div class="upload-section">
      <div
        class="upload-area"
        :class="{ 'drag-over': isDragOver, 'loading': isLoading }"
        @drop.prevent="handleDrop"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @click="triggerFileInput"
      >
        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          @change="handleFileSelect"
          style="display: none"
        />

        <div v-if="!previewImage" class="upload-placeholder">
          <svg class="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke-width="2"/>
            <polyline points="17 8 12 3 7 8" stroke-width="2"/>
            <line x1="12" y1="3" x2="12" y2="15" stroke-width="2"/>
          </svg>
          <p class="upload-text">点击或拖拽图片到此处</p>
          <p class="upload-hint">支持 JPG、PNG 格式</p>
        </div>

        <div v-else class="preview-container">
          <img :src="previewImage" alt="预览图" class="preview-image" />
          <button @click.stop="clearImage" class="clear-btn">×</button>
        </div>

        <div v-if="isLoading" class="loading-overlay">
          <div class="spinner"></div>
          <p>正在识别...</p>
        </div>
      </div>

      <div v-if="previewImage && !isLoading" class="ocr-controls">
        <div class="llm-toggle">
          <label class="toggle-label">
            <input type="checkbox" v-model="useLLMEnhancement" />
            <span class="toggle-slider"></span>
            <span class="toggle-text">启用LLM智能增强</span>
          </label>
          <span class="toggle-hint">使用AI纠正识别错误，完善表格结构</span>
        </div>
        
        <button
          @click="startOcr"
          class="ocr-btn"
          :disabled="isLoading"
        >
          {{ useLLMEnhancement ? '智能识别' : '开始识别' }}
        </button>
      </div>
    </div>

    <div v-if="errorMessage" class="error-message">
      {{ errorMessage }}
    </div>

    <!-- 增强信息显示 -->
    <div v-if="enhancementInfo.applied" class="enhancement-section">
      <div class="enhancement-header">
        <h3>🔍 AI智能增强结果</h3>
        <span class="enhancement-badge">AI优化</span>
      </div>
      
      <div v-if="enhancementInfo.corrections.length > 0" class="corrections-list">
        <h4>文字纠正 ({{ enhancementInfo.corrections.length }} 处)</h4>
        <div class="correction-item" v-for="(correction, index) in enhancementInfo.corrections" :key="index">
          <span class="original">{{ correction.original }}</span>
          <span class="arrow">→</span>
          <span class="corrected">{{ correction.corrected }}</span>
          <span class="reason">{{ correction.reason }}</span>
        </div>
      </div>
      
      <div v-if="enhancementInfo.tableStructure && Object.keys(enhancementInfo.tableStructure).length > 0" class="structure-info">
        <h4>表格结构分析</h4>
        <div class="structure-details">
          <span>表头: {{ enhancementInfo.tableStructure.headers ? enhancementInfo.tableStructure.headers.join(', ') : '未识别' }}</span>
          <span>列数: {{ enhancementInfo.tableStructure.estimated_columns ?? '未知' }}</span>
          <span>数据类型: {{ enhancementInfo.tableStructure.data_types ? enhancementInfo.tableStructure.data_types.join(', ') : '未分析' }}</span>
        </div>
      </div>
      
      <div v-if="enhancementInfo.error" class="enhancement-error">
        <span class="error-text">⚠️ 增强过程遇到问题: {{ enhancementInfo.error }}</span>
      </div>
    </div>

    <!-- 单个表格或未拆分的情况 -->
    <div v-if="!isSplit && tableData.headers.length > 0" class="table-section">
      <div class="table-header">
        <h3>{{ enhancementInfo.applied ? '智能识别结果' : '识别结果' }}</h3>
        <div class="table-actions">
          <button @click="exportCsv" class="export-btn">导出 CSV</button>
        </div>
      </div>

      <div class="table-wrapper">
        <table class="result-table">
          <thead>
            <tr>
              <th v-for="(header, index) in tableData.headers" :key="index">
                {{ header }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in tableData.rows" :key="rowIndex">
              <td v-for="(cell, cellIndex) in row" :key="cellIndex">
                {{ cell }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="table-info">
        <span>共 {{ tableData.rows.length }} 行数据</span>
        <span v-if="enhancementInfo.applied" class="enhancement-indicator">✓ AI增强已应用</span>
      </div>
    </div>

    <!-- 多个拆分表格的情况 -->
    <div v-if="isSplit && splitTables.length > 0" class="tables-section">
      <div class="split-info-header">
        <h3>{{ enhancementInfo.applied ? '智能识别结果' : '识别结果' }}</h3>
        <span class="split-badge">检测到 {{ splitTables.length }} 个表格</span>
      </div>

      <div v-for="(table, tableIndex) in splitTables" :key="tableIndex" class="table-section">
        <div class="table-header">
          <h4>表格 {{ tableIndex + 1 }}</h4>
          <div class="table-actions">
            <button @click="exportSingleTableCsv(tableIndex)" class="export-btn">导出表格 {{ tableIndex + 1 }}</button>
          </div>
        </div>

        <div class="table-wrapper">
          <table class="result-table">
            <thead>
              <tr>
                <th v-for="(header, index) in table.headers" :key="index">
                  {{ header }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in table.rows" :key="rowIndex">
                <td v-for="(cell, cellIndex) in row" :key="cellIndex">
                  {{ cell }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="table-info">
          <span>共 {{ table.rows.length }} 行数据</span>
          <span v-if="enhancementInfo.applied" class="enhancement-indicator">✓ AI增强已应用</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'

interface TableData {
  headers: string[]
  rows: string[][]
}

interface SplitTable {
  headers: string[]
  rows: string[][]
}

const isDragOver = ref(false)
const isLoading = ref(false)
const previewImage = ref('')
const errorMessage = ref('')
const fileInput = ref<HTMLInputElement>()
const selectedFile = ref<File | null>(null)
const useLLMEnhancement = ref(true)

const tableData = reactive<TableData>({
  headers: [],
  rows: []
})

const splitTables = ref<SplitTable[]>([])
const isSplit = ref(false)

interface Correction {
  original: string
  corrected: string
  reason: string
}

interface TableStructure {
  headers?: string[]
  data_types?: string[]
  estimated_columns?: number
}

const enhancementInfo = reactive({
  applied: false,
  corrections: [] as Correction[],
  tableStructure: {} as TableStructure,
  error: ''
})

// 触发文件选择
const triggerFileInput = () => {
  fileInput.value?.click()
}

// 处理文件选择
const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    processFile(file)
  }
}

// 处理拖拽上传
const handleDrop = (event: DragEvent) => {
  isDragOver.value = false
  const file = event.dataTransfer?.files[0]
  if (file && file.type.startsWith('image/')) {
    processFile(file)
  } else {
    errorMessage.value = '请上传图片文件'
  }
}

// 处理文件
const processFile = (file: File) => {
  selectedFile.value = file
  errorMessage.value = ''

  // 创建预览
  const reader = new FileReader()
  reader.onload = (e) => {
    previewImage.value = e.target?.result as string
  }
  reader.readAsDataURL(file)

  // 清空之前的结果
  tableData.headers = []
  tableData.rows = []
}

// 清除图片
const clearImage = () => {
  previewImage.value = ''
  selectedFile.value = null
  tableData.headers = []
  tableData.rows = []
  splitTables.value = []
  isSplit.value = false
  errorMessage.value = ''

  // 重置增强信息
  enhancementInfo.applied = false
  enhancementInfo.corrections = []
  enhancementInfo.tableStructure = {}
  enhancementInfo.error = ''
}

// 开始OCR识别
const startOcr = async () => {
  if (!selectedFile.value) {
    errorMessage.value = '请先选择图片'
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  
  // 重置增强信息
  enhancementInfo.applied = false
  enhancementInfo.corrections = []
  enhancementInfo.tableStructure = {}
  enhancementInfo.error = ''

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    // 添加LLM增强参数
    const url = `http://localhost:8000/api/ocr?enhance=${useLLMEnhancement.value}`
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData
    })

    const result = await response.json()

    if (result.success) {
      // 检查是否有多个表格
      if (result.data.tables && result.data.tables.length > 0) {
        // 多个拆分表格
        splitTables.value = result.data.tables
        isSplit.value = true
        // 使用第一个表格作为默认显示（兼容旧逻辑）
        tableData.headers = result.data.tables[0].headers
        tableData.rows = result.data.tables[0].rows
      } else {
        // 单个表格
        splitTables.value = []
        isSplit.value = false
        tableData.headers = result.data.headers
        tableData.rows = result.data.rows
      }

      // 保存增强信息
      if (result.enhancement) {
        enhancementInfo.applied = result.enhancement.applied
        enhancementInfo.corrections = result.enhancement.corrections || []
        enhancementInfo.tableStructure = result.enhancement.tableStructure || {}
        enhancementInfo.error = result.enhancement.error || ''
      }
    } else {
      errorMessage.value = result.error || '识别失败，请重试'
    }
  } catch (error) {
    console.error('OCR请求失败:', error)
    errorMessage.value = '连接OCR服务失败，请确保后端服务已启动'
  } finally {
    isLoading.value = false
  }
}

// 导出CSV
const exportCsv = () => {
  if (!tableData.headers || tableData.headers.length === 0) return

  const csvContent = [
    tableData.headers.join(','),
    ...tableData.rows.map(row => row ? row.join(',') : '')
  ].join('\n')

  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'ocr_result.csv'
  link.click()
}

// 导出单个表格CSV
const exportSingleTableCsv = (tableIndex: number) => {
  if (!splitTables.value[tableIndex]) return

  const table = splitTables.value[tableIndex]
  const csvContent = [
    table.headers.join(','),
    ...table.rows.map(row => row ? row.join(',') : '')
  ].join('\n')

  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `ocr_result_table_${tableIndex + 1}.csv`
  link.click()
}
</script>

<style scoped>
.ocr-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.upload-section {
  margin-bottom: 2rem;
}

.upload-area {
  border: 2px dashed #ddd;
  border-radius: 8px;
  padding: 3rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  background: #fafafa;
}

.upload-area:hover,
.upload-area.drag-over {
  border-color: #4CAF50;
  background: #f0f8f0;
}

.upload-area.loading {
  pointer-events: none;
}

.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.upload-icon {
  width: 64px;
  height: 64px;
  color: #999;
}

.upload-text {
  font-size: 1.1rem;
  color: #333;
  margin: 0;
}

.upload-hint {
  font-size: 0.9rem;
  color: #999;
  margin: 0;
}

.preview-container {
  position: relative;
  display: inline-block;
}

.preview-image {
  max-width: 100%;
  max-height: 400px;
  border-radius: 4px;
}

.clear-btn {
  position: absolute;
  top: -10px;
  right: -10px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  background: #ff4444;
  color: white;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #4CAF50;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.ocr-btn {
  margin-top: 1rem;
  padding: 0.75rem 2rem;
  background: #4CAF50;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.3s;
}

.ocr-btn:hover:not(:disabled) {
  background: #45a049;
}

.ocr-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.error-message {
  background: #ffebee;
  color: #c62828;
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.table-section {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  overflow: hidden;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #eee;
}

.table-header h3 {
  margin: 0;
  color: #333;
}

.table-actions {
  display: flex;
  gap: 0.5rem;
}

.export-btn {
  padding: 0.5rem 1rem;
  background: #2196F3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.3s;
}

.export-btn:hover {
  background: #0b7dda;
}

.table-wrapper {
  overflow-x: auto;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
}

.result-table th,
.result-table td {
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.result-table th {
  background: #f5f5f5;
  font-weight: 600;
  color: #333;
}

.result-table tbody tr:hover {
  background: #f9f9f9;
}

.table-info {
  padding: 0.75rem 1.5rem;
  background: #f5f5f5;
  color: #666;
  font-size: 0.9rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.enhancement-indicator {
  color: #4CAF50;
  font-weight: 600;
}

/* LLM增强控制样式 */
.ocr-controls {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.llm-toggle {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 500;
}

.toggle-label input[type="checkbox"] {
  display: none;
}

.toggle-slider {
  width: 50px;
  height: 24px;
  background: #ccc;
  border-radius: 24px;
  position: relative;
  transition: background 0.3s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: transform 0.3s;
}

.toggle-label input[type="checkbox"]:checked + .toggle-slider {
  background: #4CAF50;
}

.toggle-label input[type="checkbox"]:checked + .toggle-slider::before {
  transform: translateX(26px);
}

.toggle-text {
  color: #333;
}

.toggle-hint {
  font-size: 0.85rem;
  color: #666;
  margin-left: 60px;
}

/* 增强信息显示样式 */
.enhancement-section {
  background: linear-gradient(135deg, #e8f5e8, #f0f8f0);
  border: 1px solid #4CAF50;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.enhancement-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.enhancement-header h3 {
  margin: 0;
  color: #2e7d32;
}

.enhancement-badge {
  background: #4CAF50;
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
}

.corrections-list h4,
.structure-info h4 {
  margin: 1rem 0 0.5rem 0;
  color: #2e7d32;
  font-size: 1rem;
}

.correction-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: white;
  border-radius: 4px;
  margin-bottom: 0.25rem;
  border-left: 3px solid #4CAF50;
}

.original {
  text-decoration: line-through;
  color: #f44336;
  font-weight: 500;
}

.arrow {
  color: #666;
}

.corrected {
  color: #4CAF50;
  font-weight: 600;
}

.reason {
  color: #666;
  font-size: 0.85rem;
  margin-left: auto;
}

.structure-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.structure-details span {
  background: white;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.9rem;
}

.enhancement-error {
  background: #ffebee;
  border: 1px solid #f44336;
  border-radius: 4px;
  padding: 0.75rem;
  margin-top: 1rem;
}

.error-text {
  color: #c62828;
  font-size: 0.9rem;
}

/* 多表格显示样式 */
.tables-section {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.split-info-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: linear-gradient(135deg, #e3f2fd, #f3e5f5);
  border: 1px solid #9c27b0;
  border-radius: 8px 8px 0 0;
}

.split-info-header h3 {
  margin: 0;
  color: #7b1fa2;
}

.split-badge {
  background: #9c27b0;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 600;
}

.tables-section .table-section {
  margin-top: 0;
}

.tables-section .table-header h4 {
  margin: 0;
  color: #333;
  font-size: 1.1rem;
}
</style>
