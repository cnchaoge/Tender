<template>
<!-- 历史版本 -->
<div class="section-label" style="margin-top: 28px">历史版本</div>
<div class="versions-card">
  <div v-if="loadingVersions" class="versions-loading">
    <span class="versions-spinner"></span> 加载中...</div>
  <div v-else-if="versionList.length === 0" class="versions-empty">
    暂无历史版本
  </div>
  <div v-else class="version-list">
    <div
      v-for="v in versionList"
      :key="v.id"
      class="version-item"
      :class="{ expanded: expandedVersionId === v.id }"
    >
      <div class="version-header" @click="emit('toggle', v.id)">
        <div class="version-info">
          <span class="version-date">{{ formatDate(v.generated_at) }}</span>
          <span class="version-name">{{ v.project_name || '未命名项目' }}</span>
        </div>
        <el-icon class="version-arrow" :class="{ open: expandedVersionId === v.id }"><component :is="ArrowRight" /></el-icon>
      </div>
      <div v-if="expandedVersionId === v.id" class="version-body">
        <div class="version-content" v-html="renderMarkdown(versionContents[v.id] || '')"></div>
        <div class="version-actions">
          <el-button size="small" @click="emit('regenerate', v.id)">
            基于此版本重新生成
          </el-button>
          <el-button size="small" @click="emit('open-compare', v.id)">
            对比
          </el-button>
          <button v-if="v.file_path" type="button" class="version-download" @click="emit('download', getFilename(v.file_path))">
            <el-icon><component :is="Download" /></el-icon>
            下载
          </button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- 对比弹窗 -->
<el-dialog class="bid-page" :model-value="compareDialogVisible" title="版本对比" width="800px" :close-on-click-modal="true" @update:model-value="emit('update:compareDialogVisible', $event)">
  <div class="compare-controls">
    <el-select :model-value="compareFromId" placeholder="选择版本A" size="small" style="width: 200px" @update:model-value="emit('update:compareFromId', $event)">
      <el-option v-for="v in versionList" :key="v.id" :label="`v${v.id} - ${v.project_name || '未命名'}`" :value="v.id" />
    </el-select>
    <span style="padding: 0 8px; color: var(--color-ink-subtle)">vs</span>
    <el-select :model-value="compareToId" placeholder="选择版本B" size="small" style="width: 200px" @update:model-value="emit('update:compareToId', $event)">
      <el-option v-for="v in versionList" :key="v.id" :label="`v${v.id} - ${v.project_name || '未命名'}`" :value="v.id" />
    </el-select>
    <el-button size="small" type="primary" :loading="comparing" @click="emit('compare')" style="margin-left: 8px">对比</el-button>
  </div>
  <pre v-if="compareDiff" class="compare-diff">{{ compareDiff }}</pre>
  <div v-else class="compare-empty">选择两个版本后点击对比</div>
</el-dialog>
</template>

<script setup>
import { ArrowRight, Download } from "@element-plus/icons-vue"
import { marked } from "marked"

defineProps({
  versionList: { type: Array, default: () => [] },
  loadingVersions: { type: Boolean, default: false },
  expandedVersionId: { type: [Number, String], default: null },
  versionContents: { type: Object, default: () => ({}) },
  compareDialogVisible: { type: Boolean, default: false },
  compareFromId: { type: [Number, String], default: null },
  compareToId: { type: [Number, String], default: null },
  compareDiff: { type: String, default: "" },
  comparing: { type: Boolean, default: false },
})
const emit = defineEmits([
  "toggle",
  "regenerate",
  "open-compare",
  "compare",
  "download",
  "update:compareDialogVisible",
  "update:compareFromId",
  "update:compareToId",
])

function formatDate(ts) {
  if (!ts) return ""
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`
}

function getFilename(path) {
  return path ? path.split("/").pop() : ""
}

function renderMarkdown(text) {
  return marked.parse(text || "")
}
</script>

