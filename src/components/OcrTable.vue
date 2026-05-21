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
          multiple
          @change="handleFileSelect"
          style="display: none"
        />

        <div v-if="imageQueue.length === 0" class="upload-placeholder">
          <svg class="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke-width="2"/>
            <polyline points="17 8 12 3 7 8" stroke-width="2"/>
            <line x1="12" y1="3" x2="12" y2="15" stroke-width="2"/>
          </svg>
          <p class="upload-text">点击或拖拽图片到此处</p>
          <p class="upload-hint">支持 JPG、PNG，可多选或批量拖拽</p>
        </div>

        <div v-else class="preview-container">
          <img :src="previewImage" alt="预览图" class="preview-image" />
          <button @click.stop="clearAllImages" class="clear-btn" title="清空全部">×</button>
        </div>

        <div v-if="isLoading" class="loading-overlay">
          <div class="spinner"></div>
          <p>{{ batchProgressText }}</p>
        </div>
      </div>

      <div v-if="imageQueue.length > 0" class="batch-toolbar">
        <span class="batch-count">已添加 {{ imageQueue.length }} 张图片</span>
        <button type="button" class="link-btn" @click="triggerFileInput">继续添加</button>
      </div>

      <div v-if="imageQueue.length > 1" class="batch-thumbnails">
        <button
          v-for="item in imageQueue"
          :key="item.id"
          type="button"
          class="thumb-item"
          :class="{ active: item.id === activeItemId, [item.status]: true }"
          @click="selectItem(item.id)"
        >
          <img :src="item.preview" :alt="item.file.name" />
          <span class="thumb-name">{{ item.file.name }}</span>
          <span class="thumb-status">{{ statusLabel(item.status) }}</span>
          <span
            class="thumb-remove"
            @click.stop="removeItem(item.id)"
            title="移除"
          >×</span>
        </button>
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
          {{ ocrButtonLabel }}
        </button>
        <button
          v-if="hasAnySuccess"
          type="button"
          class="export-btn batch-export-btn"
          @click="exportAllBatchCsv"
        >
          导出全部 CSV
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
          <button @click="exportCsv" class="export-btn" :disabled="!canExport">导出 CSV</button>
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
        <div class="split-header-actions">
          <span class="split-badge">检测到 {{ splitTables.length }} 个表格</span>
          <button @click="exportAllSplitTablesCsv" class="export-btn" :disabled="!canExport">合并导出 CSV</button>
        </div>
      </div>

      <div v-for="(table, tableIndex) in splitTables" :key="tableIndex" class="table-section">
        <div class="table-header">
          <h4>表格 {{ tableIndex + 1 }}</h4>
          <div class="table-actions">
            <button @click="exportSingleTableCsv(tableIndex)" class="export-btn" :disabled="!canExport">导出表格 {{ tableIndex + 1 }}</button>
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
import { ref, reactive, computed } from 'vue'
import {
  tableToCsv,
  mergeMultipleTablesCsv,
  mergeSplitTablesCsv,
  buildExportFilename,
  downloadCsv,
  sanitizeFilename,
  ensureTableHeaders,
  type TableExportData
} from '../utils/csvExport'

const fixTableForDisplay = (table: TableData): TableData => ensureTableHeaders(table)

interface TableData {
  headers: string[]
  rows: string[][]
}

type BatchStatus = 'pending' | 'processing' | 'success' | 'error'

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

interface EnhancementState {
  applied: boolean
  corrections: Correction[]
  tableStructure: TableStructure
  error: string
}

interface BatchItem {
  id: string
  file: File
  preview: string
  status: BatchStatus
  error?: string
  isSplit: boolean
  tableData: TableData
  splitTables: TableData[]
  enhancement: EnhancementState
}

const emptyEnhancement = (): EnhancementState => ({
  applied: false,
  corrections: [],
  tableStructure: {},
  error: ''
})

const isDragOver = ref(false)
const isLoading = ref(false)
const errorMessage = ref('')
const fileInput = ref<HTMLInputElement>()
const useLLMEnhancement = ref(true)
const imageQueue = ref<BatchItem[]>([])
const activeItemId = ref<string | null>(null)
const batchProgress = ref({ current: 0, total: 0 })

const tableData = reactive<TableData>({ headers: [], rows: [] })
const splitTables = ref<TableData[]>([])
const isSplit = ref(false)

const enhancementInfo = reactive<EnhancementState>(emptyEnhancement())

let idCounter = 0
const nextId = () => `img-${Date.now()}-${++idCounter}`

const activeItem = computed(() =>
  imageQueue.value.find(i => i.id === activeItemId.value) ?? null
)

const previewImage = computed(() => activeItem.value?.preview ?? '')

const batchProgressText = computed(() => {
  if (batchProgress.value.total > 1) {
    return `正在识别 ${batchProgress.value.current}/${batchProgress.value.total}...`
  }
  return '正在识别...'
})

const hasAnySuccess = computed(() =>
  imageQueue.value.some(i => i.status === 'success')
)

const canExport = computed(() =>
  tableData.headers.length > 0 || tableData.rows.length > 0
)

const ocrButtonLabel = computed(() => {
  const base = useLLMEnhancement.value ? '智能识别' : '开始识别'
  if (imageQueue.value.length > 1) return `批量${base}（${imageQueue.value.length} 张）`
  return base
})

const statusLabel = (status: BatchStatus) => {
  const map: Record<BatchStatus, string> = {
    pending: '待识别',
    processing: '识别中',
    success: '已完成',
    error: '失败'
  }
  return map[status]
}

const syncDisplayFromItem = (item: BatchItem | null) => {
  if (!item) {
    tableData.headers = []
    tableData.rows = []
    splitTables.value = []
    isSplit.value = false
    Object.assign(enhancementInfo, emptyEnhancement())
    return
  }
  tableData.headers = [...item.tableData.headers]
  tableData.rows = item.tableData.rows.map(r => [...r])
  splitTables.value = item.splitTables.map(t => ({
    headers: [...t.headers],
    rows: t.rows.map(r => [...r])
  }))
  isSplit.value = item.isSplit
  Object.assign(enhancementInfo, { ...item.enhancement })
}

const applyOcrResultToItem = (item: BatchItem, result: Record<string, unknown>) => {
  const data = result.data as Record<string, unknown>
  if (data.tables && Array.isArray(data.tables) && (data.tables as TableData[]).length > 0) {
    const tables = (data.tables as TableData[]).map(fixTableForDisplay)
    item.splitTables = tables
    item.isSplit = true
    item.tableData = {
      headers: [...tables[0].headers],
      rows: tables[0].rows.map(r => [...r])
    }
  } else {
    item.splitTables = []
    item.isSplit = false
    item.tableData = fixTableForDisplay({
      headers: [...(data.headers as string[])],
      rows: (data.rows as string[][]).map(r => [...r])
    })
  }
  const enh = result.enhancement as Record<string, unknown> | undefined
  if (enh) {
    item.enhancement = {
      applied: Boolean(enh.applied),
      corrections: (enh.corrections as Correction[]) || [],
      tableStructure: (enh.tableStructure as TableStructure) || {},
      error: (enh.error as string) || ''
    }
  } else {
    item.enhancement = emptyEnhancement()
  }
}

const readFilePreview = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target?.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })

const addFiles = async (files: FileList | File[]) => {
  const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
  if (!imageFiles.length) {
    errorMessage.value = '请选择图片文件（JPG、PNG 等）'
    return
  }
  errorMessage.value = ''

  for (const file of imageFiles) {
    const preview = await readFilePreview(file)
    const item: BatchItem = {
      id: nextId(),
      file,
      preview,
      status: 'pending',
      isSplit: false,
      tableData: { headers: [], rows: [] },
      splitTables: [],
      enhancement: emptyEnhancement()
    }
    imageQueue.value.push(item)
    if (!activeItemId.value) {
      activeItemId.value = item.id
      syncDisplayFromItem(item)
    }
  }
}

const triggerFileInput = () => fileInput.value?.click()

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files?.length) addFiles(target.files)
  target.value = ''
}

const handleDrop = (event: DragEvent) => {
  isDragOver.value = false
  const files = event.dataTransfer?.files
  if (files?.length) {
    addFiles(files)
  } else {
    errorMessage.value = '请上传图片文件'
  }
}

const selectItem = (id: string) => {
  activeItemId.value = id
  syncDisplayFromItem(imageQueue.value.find(i => i.id === id) ?? null)
}

const removeItem = (id: string) => {
  const idx = imageQueue.value.findIndex(i => i.id === id)
  if (idx === -1) return
  imageQueue.value.splice(idx, 1)
  if (activeItemId.value === id) {
    const next = imageQueue.value[Math.min(idx, imageQueue.value.length - 1)]
    activeItemId.value = next?.id ?? null
    syncDisplayFromItem(next ?? null)
  }
}

const clearAllImages = () => {
  imageQueue.value = []
  activeItemId.value = null
  syncDisplayFromItem(null)
  errorMessage.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

const runOcrForFile = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  const url = `http://localhost:8000/api/ocr?enhance=${useLLMEnhancement.value}`
  const response = await fetch(url, { method: 'POST', body: formData })
  return response.json()
}

const startOcr = async () => {
  if (!imageQueue.value.length) {
    errorMessage.value = '请先添加图片'
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  const targets = imageQueue.value.filter(i => i.status !== 'success')
  const toProcess = targets.length ? targets : imageQueue.value
  batchProgress.value = { current: 0, total: toProcess.length }

  let failCount = 0

  for (let i = 0; i < toProcess.length; i++) {
    const item = toProcess[i]
    batchProgress.value = { current: i + 1, total: toProcess.length }
    item.status = 'processing'
    item.error = undefined
    selectItem(item.id)

    try {
      const result = await runOcrForFile(item.file)
      if (result.success) {
        applyOcrResultToItem(item, result)
        item.status = 'success'
        syncDisplayFromItem(item)
      } else {
        item.status = 'error'
        item.error = result.error || '识别失败'
        failCount++
      }
    } catch (error) {
      console.error('OCR请求失败:', error)
      item.status = 'error'
      item.error = '连接OCR服务失败'
      failCount++
    }
  }

  isLoading.value = false
  batchProgress.value = { current: 0, total: 0 }

  if (failCount === toProcess.length) {
    errorMessage.value = '全部识别失败，请检查后端服务或图片质量'
  } else if (failCount > 0) {
    errorMessage.value = `${failCount} 张图片识别失败，可在缩略图上查看状态`
  }
}

const sourceBaseName = () => {
  const name = activeItem.value?.file.name ?? 'ocr_result'
  return sanitizeFilename(name.replace(/\.[^.]+$/, ''))
}

const exportCsv = () => {
  if (!canExport.value) return
  const meta = imageQueue.value.length > 1
    ? { headers: ['来源文件'], values: [activeItem.value?.file.name ?? ''] }
    : undefined
  downloadCsv(
    tableToCsv(tableData, meta),
    buildExportFilename(sourceBaseName())
  )
}

const exportSingleTableCsv = (tableIndex: number) => {
  const table = splitTables.value[tableIndex]
  if (!table?.headers.length && !table?.rows.length) return
  const meta = imageQueue.value.length > 1
    ? { headers: ['来源文件'], values: [activeItem.value?.file.name ?? ''] }
    : undefined
  downloadCsv(
    tableToCsv(table, meta),
    buildExportFilename(`${sourceBaseName()}_table${tableIndex + 1}`)
  )
}

const exportAllSplitTablesCsv = () => {
  if (!splitTables.value.length) return
  const meta = imageQueue.value.length > 1
    ? { headers: ['来源文件'], values: [activeItem.value?.file.name ?? ''] }
    : undefined
  downloadCsv(
    mergeSplitTablesCsv(splitTables.value, meta),
    buildExportFilename(`${sourceBaseName()}_merged`)
  )
}

const exportAllBatchCsv = () => {
  const successItems = imageQueue.value.filter(
    i => i.status === 'success' && (i.tableData.headers.length || i.tableData.rows.length || i.splitTables.length)
  )
  if (!successItems.length) return

  if (successItems.length === 1) {
    const item = successItems[0]
    const meta = { headers: ['来源文件'], values: [item.file.name] }
    if (item.isSplit && item.splitTables.length) {
      downloadCsv(
        mergeSplitTablesCsv(item.splitTables, meta),
        buildExportFilename(item.file.name.replace(/\.[^.]+$/, ''))
      )
    } else {
      downloadCsv(
        tableToCsv(item.tableData, meta),
        buildExportFilename(item.file.name.replace(/\.[^.]+$/, ''))
      )
    }
    return
  }

  const hasSplit = successItems.some(i => i.isSplit && i.splitTables.length > 1)
  const metaHeaders = hasSplit ? ['来源文件', '子表格'] : ['来源文件']
  const sections: { metaValues?: string[]; table: TableExportData }[] = []

  for (const item of successItems) {
    if (item.isSplit && item.splitTables.length) {
      for (let t = 0; t < item.splitTables.length; t++) {
        sections.push({
          metaValues: hasSplit
            ? [item.file.name, `表格${t + 1}`]
            : [item.file.name],
          table: item.splitTables[t]
        })
      }
    } else {
      sections.push({
        metaValues: [item.file.name],
        table: item.tableData
      })
    }
  }

  downloadCsv(mergeMultipleTablesCsv(sections, metaHeaders), buildExportFilename('batch_ocr'))
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

.batch-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.75rem;
  font-size: 0.9rem;
  color: #555;
}

.link-btn {
  background: none;
  border: none;
  color: #2196F3;
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0;
}

.link-btn:hover {
  text-decoration: underline;
}

.batch-thumbnails {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
  max-height: 200px;
  overflow-y: auto;
}

.thumb-item {
  position: relative;
  width: 100px;
  padding: 0.35rem;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  text-align: center;
  transition: border-color 0.2s;
}

.thumb-item:hover,
.thumb-item.active {
  border-color: #4CAF50;
}

.thumb-item.success { border-color: #81c784; }
.thumb-item.error { border-color: #e57373; }
.thumb-item.processing { border-color: #ffb74d; }

.thumb-item img {
  width: 100%;
  height: 56px;
  object-fit: cover;
  border-radius: 4px;
}

.thumb-name {
  display: block;
  font-size: 0.65rem;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 0.25rem;
}

.thumb-status {
  display: block;
  font-size: 0.6rem;
  color: #888;
}

.thumb-remove {
  position: absolute;
  top: 2px;
  right: 4px;
  color: #999;
  font-size: 14px;
  line-height: 1;
}

.thumb-remove:hover {
  color: #f44336;
}

.batch-export-btn {
  align-self: flex-start;
}

.export-btn:disabled {
  background: #bdbdbd;
  cursor: not-allowed;
}

.export-btn:disabled:hover {
  background: #bdbdbd;
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
  flex-wrap: wrap;
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

.split-header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
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
