<template>
  <div class="price-analyze">
    <!-- Page Header -->
    <div class="page-header">
      <div class="header-eyebrow">投标报价</div>
      <h1 class="header-title">报价分析计算器</h1>
      <p class="header-desc">根据招标文件的评分公式，输入成本价后自动计算最优投标报价。</p>
    </div>

    <div class="page-body">
      <!-- Left: Main Content -->
      <div class="main-content">
        <!-- Card: Formula -->
        <div class="card">
          <div class="card-header">
            <h3>价格评分公式</h3>
            <div class="card-actions">
              <el-button size="small" @click="showTemplateDialog = true">选择模板</el-button>
              <el-button size="small" text @click="formulaEditable = !formulaEditable">
                {{ formulaEditable ? '完成编辑' : '编辑公式' }}
              </el-button>
            </div>
          </div>
          <div class="card-body">
            <el-descriptions :column="2" border size="small" v-if="!formulaEditable">
              <el-descriptions-item label="评标方法">
                <el-tag :type="methodTagType" size="small">{{ methodLabel }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="价格分权重">{{ formula.weight }} 分</el-descriptions-item>
              <el-descriptions-item label="公式描述" :span="2">{{ formula.description || '未识别到价格公式' }}</el-descriptions-item>
            </el-descriptions>

            <el-form v-else label-position="top" size="small">
              <el-form-item label="评标方法">
                <el-select v-model="formula.method" style="width:100%">
                  <el-option value="lowest" label="最低价法 — 价格分 = (最低价/投标报价)×权重" />
                  <el-option value="average" label="均价法 — 价格分 = (平均价/投标报价)×权重" />
                  <el-option value="formula" label="公式法 — 自定义公式" />
                </el-select>
              </el-form-item>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="价格分权重">
                    <el-input-number v-model="formula.weight" :min="5" :max="60" style="width:100%" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="基准价类型">
                    <el-select v-model="formula.params.base_price_type" style="width:100%">
                      <el-option value="lowest" label="最低有效报价" />
                      <el-option value="average" label="有效报价平均值" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="公式表达式">
                <el-input v-model="formula.params.formula_text" placeholder="如：(最低报价/投标报价)*30" />
              </el-form-item>
            </el-form>
          </div>
        </div>

        <!-- Card: Cost & Calculate -->
        <div class="card">
          <div class="card-header">
            <h3>成本与计算</h3>
          </div>
          <div class="card-body">
            <el-row :gutter="16" align="middle">
              <el-col :span="8">
                <el-form label-position="top" size="small">
                  <el-form-item label="成本价（元）">
                    <el-input-number
                      v-model="costPrice"
                      :min="1"
                      :step="1000"
                      style="width:100%"
                      placeholder="输入成本价"
                    />
                  </el-form-item>
                </el-form>
              </el-col>
              <el-col :span="6">
                <el-form label-position="top" size="small">
                  <el-form-item label="假设对手数量">
                    <el-input-number v-model="competitorCount" :min="2" :max="20" style="width:100%" />
                  </el-form-item>
                </el-form>
              </el-col>
              <el-col :span="6" style="display:flex;align-items:flex-end;padding-bottom:8px;">
                <el-button type="primary" size="large" :loading="calculating" @click="handleCalculate" style="width:100%">
                  {{ calculating ? '计算中...' : '开始计算' }}
                </el-button>
              </el-col>
              <el-col :span="4" style="display:flex;align-items:flex-end;padding-bottom:8px;">
                <el-button v-if="result" size="large" @click="handleSaveAnalysis">保存结果</el-button>
              </el-col>
            </el-row>
          </div>
        </div>

        <!-- Card: Results -->
        <div v-if="result" class="card">
          <div class="card-header">
            <h3>报价策略对比</h3>
            <el-tag type="success" size="small" v-if="result.suggested_price">
              建议报价：¥{{ formatMoney(result.suggested_price) }}
            </el-tag>
          </div>
          <div class="card-body">
            <!-- Explanation -->
            <el-alert :title="result.explanation" type="success" :closable="false" show-icon style="margin-bottom:16px" />

            <!-- Strategy Table -->
            <el-table :data="result.strategies" border stripe highlight-current-row max-height="400">
              <el-table-column label="策略" prop="name" width="100" />
              <el-table-column label="报价（元）" width="160">
                <template #default="{ row }">
                  <span :class="{ 'suggested-price': row.is_suggested }">¥ {{ formatMoney(row.price) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="得分" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.is_suggested ? 'success' : 'info'" effect="plain">
                    {{ row.score }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="利润（元）" width="140">
                <template #default="{ row }">
                  <span :style="{ color: row.profit >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }">
                    {{ row.profit >= 0 ? '+' : '' }}¥ {{ formatMoney(row.profit) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="利润率" width="90">
                <template #default="{ row }">
                  {{ row.profit_margin }}%
                </template>
              </el-table-column>
              <el-table-column label="排名" width="70" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.rank === 1 ? 'danger' : 'info'" size="small" round>{{ row.rank }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="推荐" width="80" align="center">
                <template #default="{ row }">
                  <el-icon v-if="row.is_suggested" color="var(--color-success)" size="18"><Check /></el-icon>
                </template>
              </el-table-column>
            </el-table>

            <!-- Insert to bid -->
            <div style="margin-top:16px;text-align:right">
              <el-button type="primary" @click="handleInsertToBid">
                <el-icon><Plus /></el-icon>
                插入到标书商务标
              </el-button>
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <el-empty v-if="!result && !calculating" :image-size="120" style="margin-top:40px">
          <template #description>
            <p>输入成本价并点击"开始计算"查看报价策略</p>
          </template>
        </el-empty>
      </div>

      <!-- Right: History -->
      <div class="side-panel">
        <div class="card">
          <div class="card-header">
            <h3>历史记录</h3>
            <el-button size="small" text @click="loadHistory">刷新</el-button>
          </div>
          <div class="card-body">
            <div v-if="historyLoading" style="text-align:center;padding:20px">
              <el-icon class="is-loading" size="20"><Loading /></el-icon>
            </div>
            <div v-else-if="historyRecords.length === 0" style="text-align:center;padding:20px;color:var(--color-ink-tertiary);font-size:13px">
              暂无记录
            </div>
            <div v-else class="history-list">
              <div
                v-for="r in historyRecords"
                :key="r.id"
                class="history-item"
                :class="{ active: activeHistoryId === r.id }"
                @click="loadHistoryDetail(r.id)"
              >
                <div class="history-name">{{ r.project_name || '未知项目' }}</div>
                <div class="history-meta">
                  成本 ¥{{ formatMoney(r.cost_price) }}
                  <el-tag size="small" type="success" v-if="r.suggested_price">
                    建议 ¥{{ formatMoney(r.suggested_price) }}
                  </el-tag>
                </div>
                <div class="history-date">{{ r.created_at }}</div>
                <el-button
                  size="small"
                  text
                  type="danger"
                  class="history-delete"
                  @click.stop="handleDeleteHistory(r.id)"
                >
                  删除
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Template Dialog -->
    <el-dialog v-model="showTemplateDialog" title="选择公式模板" width="520px">
      <div class="template-list">
        <div
          v-for="t in templates"
          :key="t.name"
          class="template-item"
          @click="selectTemplate(t)"
        >
          <div class="template-name">{{ t.name }}</div>
          <div class="template-desc">{{ t.description }}</div>
          <div class="template-meta">
            <el-tag size="small">{{ methodLabels[t.method] || t.method }}</el-tag>
            <span>权重：{{ t.weight }} 分</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showTemplateDialog = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { Check, Plus, Loading } from "@element-plus/icons-vue"
import { bid, price } from "../api"

const router = useRouter()

// ── State ────────────────────────────────────────────────────────────────
const formula = reactive({
  method: "lowest",
  weight: 30,
  description: "请先解析招标文件，或手动选择公式模板",
  params: {
    base_price_type: "lowest",
    formula_text: "(最低报价/投标报价)*30",
  },
})

const formulaEditable = ref(false)
const costPrice = ref(0)
const competitorCount = ref(5)
const calculating = ref(false)
const result = ref(null)
const showTemplateDialog = ref(false)
const templates = ref([])

// History
const historyRecords = ref([])
const historyLoading = ref(false)
const activeHistoryId = ref(null)

const methodLabels = {
  lowest: "最低价法",
  average: "均价法",
  formula: "公式法",
}

const methodTagType = computed(() => {
  return { lowest: "primary", average: "warning", formula: "success" }[formula.method] || "info"
})

const methodLabel = computed(() => methodLabels[formula.method] || formula.method)

function formatMoney(val) {
  if (val == null) return "0.00"
  return Number(val).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── Load templates ──────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const resp = await price.formulaTemplates()
    templates.value = resp.data.templates || []
  } catch (e) {
    // ignore
  }
  loadHistory()
})

// ── Parse from bid parse result (called from BidGenerate page) ──────────
async function loadFromParseResult(scoring, rawText) {
  try {
    const resp = await price.parseFormula(scoring, rawText)
    if (resp.data?.formula) {
      Object.assign(formula, resp.data.formula)
    }
  } catch (e) {
    ElMessage.warning("公式自动识别失败，请手动选择模板或编辑")
  }
}

// ── Template select ─────────────────────────────────────────────────────
function selectTemplate(t) {
  Object.assign(formula, {
    method: t.method,
    weight: t.weight,
    description: t.description,
    params: { ...t.params },
  })
  showTemplateDialog.value = false
  formulaEditable.value = false
  ElMessage.success(`已选择模板：${t.name}`)
}

// ── Calculate ────────────────────────────────────────────────────────────
async function handleCalculate() {
  if (!costPrice.value || costPrice.value <= 0) {
    ElMessage.warning("请输入成本价")
    return
  }

  calculating.value = true
  try {
    const resp = await price.calculate(
      JSON.stringify(formula),
      costPrice.value,
      competitorCount.value
    )
    result.value = resp.data
  } catch (e) {
    ElMessage.error("计算失败：" + (e.response?.data?.detail || e.message))
  } finally {
    calculating.value = false
  }
}

// ── Save ─────────────────────────────────────────────────────────────────
async function handleSaveAnalysis() {
  if (!result.value) return
  try {
    await price.save({
      project_name: "",
      formula_json: JSON.stringify(formula),
      cost_price: costPrice.value,
      suggested_price: result.value.suggested_price,
      calculated_results: JSON.stringify(result.value),
      strategy_scores: JSON.stringify(result.value.strategies),
    })
    ElMessage.success("保存成功")
    loadHistory()
  } catch (e) {
    ElMessage.error("保存失败")
  }
}

// ── History ──────────────────────────────────────────────────────────────
async function loadHistory() {
  historyLoading.value = true
  try {
    const resp = await price.history(20)
    historyRecords.value = resp.data?.records || []
  } catch (e) {
    // ignore
  } finally {
    historyLoading.value = false
  }
}

async function loadHistoryDetail(id) {
  activeHistoryId.value = id
  try {
    const resp = await price.historyDetail(id)
    const data = resp.data
    if (data.formula_json) Object.assign(formula, data.formula_json)
    costPrice.value = data.cost_price || 0
    if (data.calculated_results) result.value = data.calculated_results
  } catch (e) {
    ElMessage.error("加载失败")
  }
}

async function handleDeleteHistory(id) {
  try {
    await ElMessageBox.confirm("确定删除此记录？", "确认", { type: "warning" })
    await price.deleteHistory(id)
    ElMessage.success("已删除")
    if (activeHistoryId.value === id) activeHistoryId.value = null
    loadHistory()
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败")
  }
}

// ── Insert to bid ────────────────────────────────────────────────────────
function handleInsertToBid() {
  if (!result.value || !result.value.suggested_price) return
  // Store price data for bid page to pick up
  sessionStorage.setItem("bid_price_data", JSON.stringify({
    suggested_price: result.value.suggested_price,
    strategies: result.value.strategies,
    formula: formula,
  }))
  ElMessage.success("报价数据已保存，请在标书生成页面插入商务标章节")
  router.push("/bid")
}

// Expose for use from other pages
defineExpose({ loadFromParseResult })
</script>

<style scoped>
.price-analyze {
  padding: 24px 32px;
  max-width: 1280px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}
.header-eyebrow {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--color-ink-tertiary);
  margin-bottom: 4px;
}
.header-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 4px;
}
.header-desc {
  font-size: 13px;
  color: var(--color-ink-subtle);
  margin: 0;
}

.page-body {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 20px;
  align-items: start;
}

.main-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.side-panel {
  position: sticky;
  top: 24px;
}

.card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-hairline);
}
.card-header h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--color-ink);
}
.card-actions {
  display: flex;
  gap: 8px;
}
.card-body {
  padding: 16px;
}

.suggested-price {
  font-weight: 600;
  color: var(--color-primary);
}

/* Template list */
.template-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.template-item {
  padding: 12px;
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.12s;
}
.template-item:hover {
  border-color: var(--color-primary);
  background: rgba(94, 105, 209, 0.06);
}
.template-name {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
}
.template-desc {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-bottom: 6px;
}
.template-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--color-ink-tertiary);
}

/* History */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.history-item {
  position: relative;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.12s;
}
.history-item:hover,
.history-item.active {
  border-color: var(--color-primary);
  background: rgba(94, 105, 209, 0.04);
}
.history-name {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 2px;
}
.history-meta {
  font-size: 11px;
  color: var(--color-ink-subtle);
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.history-date {
  font-size: 10px;
  color: var(--color-ink-tertiary);
  margin-top: 2px;
}
.history-delete {
  position: absolute;
  top: 4px;
  right: 4px;
  opacity: 0;
  transition: opacity 0.12s;
}
.history-item:hover .history-delete {
  opacity: 1;
}
</style>
