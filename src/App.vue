<script setup lang="ts">
import OcrTable from './components/OcrTable.vue'
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>🎓 高考分数线 OCR 提取工具</h1>
      <p>上传表格图片，自动识别并导出数据</p>
    </header>

    <main class="app-main">
      <OcrTable />
    </main>

    <footer class="app-footer">
      <p>基于百度OCR API | Vue 3 + FastAPI</p>
    </footer>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.app-header {
  text-align: center;
  padding: 3rem 1rem 2rem;
  color: white;
}

.app-header h1 {
  margin: 0 0 0.5rem 0;
  font-size: 2.5rem;
  font-weight: 700;
}

.app-header p {
  margin: 0;
  font-size: 1.1rem;
  opacity: 0.9;
}

.app-main {
  flex: 1;
  background: white;
  border-radius: 2rem 2rem 0 0;
  padding: 2rem 0;
}

.app-footer {
  text-align: center;
  padding: 1.5rem;
  color: white;
  opacity: 0.8;
  font-size: 0.9rem;
}

.app-footer p {
  margin: 0;
}
</style>

