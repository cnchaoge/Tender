<template>
<div class="section-label">招标文件</div>

<!-- Upload Zone -->
<div class="upload-zone" @click="triggerUpload" v-if="!bidFile">
  <div class="upload-icon">
    <el-icon><component :is="Upload" /></el-icon>
  </div>
  <div class="upload-text">点击上传招标文件</div>
  <div class="upload-hint">支持 PDF / DOCX 格式</div>
</div>
<input
  ref="fileInputRef"
  type="file"
  accept=".pdf,.docx"
  style="display: none"
  @change="onFileSelected"
/>

<!-- File Loaded -->
<div class="file-card" v-if="bidFile">
  <div class="file-card-inner">
    <div class="file-icon">
      <el-icon><component :is="Document" /></el-icon>
    </div>
    <div class="file-meta">
      <div class="file-name">{{ bidFile.name }}</div>
      <div class="file-status" v-if="parseResult">已解析 · {{ Math.round(parseResult.parse_meta?.confidence * 100) }}% 可信度</div>
      <div class="file-status uploading" v-else>解析中...</div>
    </div>
    <div class="file-actions">
      <el-button size="small" @click="triggerUpload">重新上传</el-button>
    </div>
  </div>
</div>
</template>

<script setup>
import { ref } from "vue"
import { Document, Upload } from "@element-plus/icons-vue"

defineProps({
  bidFile: { type: Object, default: null },
  parseResult: { type: Object, default: null },
})
const emit = defineEmits(["file-selected"])
const fileInputRef = ref(null)

function triggerUpload() {
  fileInputRef.value?.click()
}

function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (file) emit("file-selected", file)
  e.target.value = ""
}
</script>

