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

      <button
        v-if="previewImage && !isLoading"
        @click="startOcr"
        class="ocr-btn"
        :disabled="isLoading"
      >
        开始识别
      </button>
    </div>

    <div v-if="errorMessage" class="error-message">
      {{ errorMessage }}
    </div>

    <div v-if="tableData.headers.length > 0" class="table-section">
      <div class="table-header">
        <h3>识别结果</h3>
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

const isDragOver = ref(false)
const isLoading = ref(false)
const previewImage = ref('')
const errorMessage = ref('')
const fileInput = ref<HTMLInputElement>()
const selectedFile = ref<File | null>(null)

const tableData = reactive<TableData>({
  headers: [],
  rows: []
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
  errorMessage.value = ''
}

// 开始OCR识别
const startOcr = async () => {
  if (!selectedFile.value) {
    errorMessage.value = '请先选择图片'
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const response = await fetch('http://localhost:8000/api/ocr', {
      method: 'POST',
      body: formData
    })

    const result = await response.json()

    if (result.success) {
      tableData.headers = result.data.headers
      tableData.rows = result.data.rows
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
  if (tableData.headers.length === 0) return

  const csvContent = [
    tableData.headers.join(','),
    ...tableData.rows.map(row => row.join(','))
  ].join('\n')

  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'ocr_result.csv'
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
}
</style>
