<template>
<!-- 标书模板选择 -->
    <div class="section-label">
      标书模板
      <span class="section-label-hint" v-if="selectedTemplate">已选：{{ selectedTemplate.name }}</span>
    </div>
    <div class="template-card">
      <div class="template-list">
        <div
          v-for="tpl in templates"
          :key="tpl.id"
          class="template-item"
          :class="{ active: selectedTemplateId === tpl.id }"
          @click="emit('select', tpl)"
        >
          <div class="template-radio">
            <span class="radio-dot" :class="{ checked: selectedTemplateId === tpl.id }"></span>
          </div>
          <div class="template-body">
            <div class="template-name">{{ tpl.name }}</div>
            <div class="template-desc">{{ tpl.description }}</div>
            <div class="template-meta">
              <span>{{ tpl.chapters?.length || 0 }} 章</span>
              <span v-if="tpl.industry"> · {{ tpl.industry }}</span>
              <span class="template-strategy">策略：{{ tpl.default_strategy }}</span>
            </div>
          </div>
          <el-button
            v-if="selectedTemplateId === tpl.id"
            size="small"
            text
            type="primary"
            @click.stop="showTemplatePreview = true"
          >
            预览
          </el-button>
        </div>
      </div>
      <div class="template-none" @click="emit('clear')">
        <span class="radio-dot" :class="{ checked: !selectedTemplateId }"></span>
        <span>不使用模板（AI 自动规划章节）</span>
      </div>
    </div>

    <!-- 模板章节预览弹窗 -->
    <el-dialog
      v-model="showTemplatePreview"
      title="章节预览"
      width="500px"
      class="template-preview-dialog bid-page"
    >
      <div v-if="selectedTemplate" class="preview-chapters">
        <div
          v-for="(ch, idx) in selectedTemplate.chapters"
          :key="idx"
          class="preview-chapter-item"
        >
          <div class="preview-chapter-num">{{ idx + 1 }}</div>
          <div class="preview-chapter-body">
            <div class="preview-chapter-name">{{ ch.name }}</div>
            <div class="preview-chapter-desc">{{ ch.description }}</div>
            <div v-if="ch.key_points" class="preview-chapter-points">{{ ch.key_points }}</div>
          </div>
        </div>
      </div>
    </el-dialog>

<!-- 规划阶段弹窗 -->
<el-dialog
  :model-value="planDialogVisible"
  @update:model-value="emit('update:planDialogVisible', $event)"
  title="确认标书结构"
  width="560px"
  :close-on-click-modal="false"
  class="plan-dialog bid-page"
>
  <div class="plan-intro">请确认以下章节结构，生成过程中将按此结构编写各章节内容：</div>
  <div class="plan-chapters">
    <div
      v-for="(ch, idx) in planningChapters"
      :key="idx"
      class="plan-chapter-item"
    >
      <div class="plan-chapter-num">{{ idx + 1 }}</div>
      <div class="plan-chapter-body">
        <div class="plan-chapter-name">{{ ch.name }}</div>
        <div class="plan-chapter-desc">{{ ch.description }}</div>
      </div>
    </div>
  </div>
  <template #footer>
    <el-button @click="emit('update:planDialogVisible', false)">取消</el-button>
    <el-button type="primary" @click="emit('confirm')">确认并生成正文</el-button>
  </template>
</el-dialog>
</template>

<script setup>
import { ref } from "vue"

defineProps({
  templates: { type: Array, default: () => [] },
  selectedTemplateId: { type: [Number, String], default: null },
  selectedTemplate: { type: Object, default: null },
  planDialogVisible: { type: Boolean, default: false },
  planningChapters: { type: Array, default: () => [] },
})
const emit = defineEmits(["select", "clear", "update:planDialogVisible", "confirm"])
const showTemplatePreview = ref(false)
</script>

