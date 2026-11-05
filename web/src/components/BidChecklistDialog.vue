<template>
  <el-dialog
    v-model="visible"
    title="投标材料检查清单"
    width="680px"
    :close-on-click-modal="false"
    @open="loadChecklist"
    @closed="emit('close')"
  >
    <!-- Summary -->
    <div v-if="summary" class="checklist-summary">
      <div class="summary-item" :class="{ ready: summary.ready === summary.total }">
        <span class="summary-num">{{ summary.ready }}/{{ summary.total }}</span>
        <span class="summary-label">已完成</span>
      </div>
      <div class="summary-bar">
        <div class="summary-bar-fill" :style="{ width: (summary.total ? (summary.ready / summary.total * 100) : 0) + '%' }" />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" style="text-align:center;padding:40px">
      <el-icon class="is-loading" size="24"><Loading /></el-icon>
      <p style="margin-top:12px;color:var(--color-ink-tertiary)">正在生成检查清单...</p>
    </div>

    <!-- Items -->
    <div v-else class="checklist-body">
      <div v-for="cat in categories" :key="cat.name" class="checklist-category" v-if="cat.items.length">
        <div class="cat-header">
          <span class="cat-name">{{ cat.name }}</span>
          <span class="cat-count">{{ cat.items.filter(i => i.status === '已准备').length }}/{{ cat.items.length }}</span>
        </div>
        <div
          v-for="item in cat.items"
          :key="item.id"
          class="checklist-item"
          :class="{ 'is-prepared': item.status === '已准备', 'is-na': item.status === '不适用' }"
        >
          <div class="item-left">
            <el-tag
              size="small"
              :type="statusType(item.status)"
              :hit="item.status === '待准备'"
              style="cursor:pointer;min-width:56px;text-align:center"
              @click="cycleStatus(item)"
            >
              {{ item.status }}
            </el-tag>
          </div>
          <div class="item-center">
            <span class="item-text">{{ item.item }}</span>
            <span v-if="item.remark" class="item-remark">{{ item.remark }}</span>
          </div>
          <div class="item-right">
            <el-button v-if="item.source === 'manual'" size="small" text type="danger" @click="handleDelete(item.id)">
              删除
            </el-button>
          </div>
        </div>
      </div>

      <!-- Empty -->
      <el-empty v-if="!categories.length || categories.every(c => !c.items.length)" :image-size="80">
        <template #description>暂无检查项</template>
      </el-empty>

      <!-- Add custom item -->
      <div class="add-item-row">
        <el-select v-model="newItemCategory" size="small" style="width:120px">
          <el-option v-for="c in categoryNames" :key="c" :value="c" :label="c" />
        </el-select>
        <el-input v-model="newItemText" size="small" placeholder="添加自定义检查项..." style="flex:1" @keyup.enter="handleAddItem" />
        <el-button size="small" type="primary" @click="handleAddItem" :disabled="!newItemText.trim()">添加</el-button>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="handleExport">导出 PDF 打印</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from "vue"
import { ElMessage } from "element-plus"
import { Loading } from "@element-plus/icons-vue"
import { checklist } from "../api"

const props = defineProps({
  modelValue: Boolean,
  bidVersionId: Number,
  bidContent: String,
  parseResult: Object,
})

const emit = defineEmits(["update:modelValue", "close"])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
})

const loading = ref(false)
const items = ref([])
const summary = ref(null)
const categoryNames = ref(["盖章页", "签字页", "资质证书", "财务证明", "业绩证明", "其他"])
const newItemCategory = ref("其他")
const newItemText = ref("")

// Group items by category
const categories = computed(() => {
  const grouped = {}
  for (const name of categoryNames.value) {
    grouped[name] = { name, items: [] }
  }
  for (const item of items.value) {
    const cat = item.category || "其他"
    if (!grouped[cat]) grouped[cat] = { name: cat, items: [] }
    grouped[cat].items.push(item)
  }
  return Object.values(grouped)
})

function statusType(status) {
  return { "已准备": "success", "不适用": "info", "待准备": "warning" }[status] || "info"
}

async function loadChecklist() {
  if (!props.bidVersionId) return
  loading.value = true
  try {
    // Generate first
    await checklist.generate(props.bidVersionId, props.bidContent || "", props.parseResult || {})
    // Fetch items
    const resp = await checklist.get(props.bidVersionId)
    items.value = resp.data?.items || []
    // Fetch export data for summary
    try {
      const exp = await checklist.exportData(props.bidVersionId)
      summary.value = exp.data?.summary || null
    } catch (e) {
      summary.value = null
    }
  } catch (e) {
    ElMessage.error("加载检查清单失败")
  } finally {
    loading.value = false
  }
}

async function cycleStatus(item) {
  const order = ["待准备", "已准备", "不适用"]
  const idx = order.indexOf(item.status)
  const nextStatus = order[(idx + 1) % order.length]
  item.status = nextStatus
  try {
    await checklist.updateItem(item.id, { status: nextStatus })
    // Refresh summary
    try {
      const exp = await checklist.exportData(props.bidVersionId)
      summary.value = exp.data?.summary || null
    } catch (e) { /* ignore */ }
  } catch (e) {
    ElMessage.error("更新失败")
  }
}

async function handleAddItem() {
  const text = newItemText.value.trim()
  if (!text) return
  try {
    const resp = await checklist.addItem({
      bid_version_id: props.bidVersionId,
      category: newItemCategory.value,
      item: text,
    })
    items.value.push({
      id: resp.data?.id,
      bid_version_id: props.bidVersionId,
      category: newItemCategory.value,
      item: text,
      status: "待准备",
      remark: "",
      source: "manual",
    })
    newItemText.value = ""
    ElMessage.success("已添加")
  } catch (e) {
    ElMessage.error("添加失败")
  }
}

async function handleDelete(itemId) {
  try {
    await checklist.deleteItem(itemId)
    items.value = items.value.filter(i => i.id !== itemId)
    ElMessage.success("已删除")
  } catch (e) {
    ElMessage.error("删除失败")
  }
}

async function handleExport() {
  try {
    const resp = await checklist.exportData(props.bidVersionId)
    const data = resp.data
    if (!data || !data.categories) {
      ElMessage.warning("清单为空")
      return
    }
    // Build print HTML
    let html = `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { font-family: "宋体", serif; padding: 40px; color: #333; }
  h1 { text-align: center; font-size: 18px; margin-bottom: 4px; }
  .subtitle { text-align: center; font-size: 12px; color: #999; margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; }
  th { background: #f0f0f0; font-weight: 600; }
  .cat-cell { font-weight: 600; background: #fafafa; width: 80px; }
  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
  .s-ready { background: #e6f7e6; color: #389e0d; }
  .s-pending { background: #fff7e6; color: #d48806; }
  .s-na { background: #f5f5f5; color: #999; }
  .summary { text-align: center; font-size: 12px; color: #666; margin-top: 16px; }
  @media print { body { padding: 20px; } }
</style></head><body>
<h1>投标材料检查清单</h1>
<p class="subtitle">${new Date().toLocaleDateString("zh-CN")}</p>
<table>
<tr><th style="width:80px">分类</th><th>检查项</th><th style="width:80px">状态</th><th>备注</th></tr>`
    for (const [cat, catItems] of Object.entries(data.categories)) {
      catItems.forEach((ci, idx) => {
        const statusClass = ci.status === '已准备' ? 's-ready' : ci.status === '不适用' ? 's-na' : 's-pending'
        html += `<tr>${idx === 0 ? `<td class="cat-cell" rowspan="${catItems.length}">${cat}</td>` : ''}<td>${ci.item}</td><td><span class="status-badge ${statusClass}">${ci.status}</span></td><td>${ci.remark || ''}</td></tr>`
      })
    }
    html += `</table>
<p class="summary">已完成 ${data.summary.ready}/${data.summary.total} 项${data.summary.pending ? '，尚有 ' + data.summary.pending + ' 项待准备' : ''}</p>
</body></html>`

    const win = window.open("", "_blank")
    win.document.write(html)
    win.document.close()
    win.focus()
    setTimeout(() => { win.print() }, 500)
  } catch (e) {
    ElMessage.error("导出失败")
  }
}
</script>

<style scoped>
.checklist-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}
.summary-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-danger);
}
.summary-item.ready .summary-num {
  color: var(--color-success);
}
.summary-label {
  font-size: 11px;
  color: var(--color-ink-tertiary);
}
.summary-bar {
  flex: 1;
  height: 8px;
  background: var(--color-surface-2);
  border-radius: 4px;
  overflow: hidden;
}
.summary-bar-fill {
  height: 100%;
  background: var(--color-success);
  border-radius: 4px;
  transition: width 0.3s;
}
.checklist-body {
  max-height: 480px;
  overflow-y: auto;
}
.checklist-category {
  margin-bottom: 12px;
}
.cat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--color-hairline);
  margin-bottom: 4px;
}
.cat-name {
  font-size: 13px;
  font-weight: 600;
}
.cat-count {
  font-size: 11px;
  color: var(--color-ink-tertiary);
}
.checklist-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 8px;
  border-radius: var(--radius-md);
  transition: background 0.1s;
}
.checklist-item:hover {
  background: var(--color-surface-2);
}
.checklist-item.is-prepared {
  opacity: 0.7;
}
.checklist-item.is-na {
  opacity: 0.5;
}
.item-left {
  flex-shrink: 0;
  padding-top: 1px;
}
.item-center {
  flex: 1;
  min-width: 0;
}
.item-text {
  font-size: 13px;
  line-height: 1.5;
}
.item-remark {
  display: block;
  font-size: 11px;
  color: var(--color-ink-tertiary);
  margin-top: 2px;
}
.item-right {
  flex-shrink: 0;
}
.add-item-row {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-hairline);
}
</style>
