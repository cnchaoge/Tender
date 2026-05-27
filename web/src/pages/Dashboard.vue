<template>
  <div class="dashboard-page">

    <!-- ── Stats Row ── -->
    <div class="stats-row">
      <div class="stat-item">
        <div class="stat-num">{{ stats.document_count ?? 0 }}</div>
        <div class="stat-lbl">文档</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-num">{{ stats.chunk_count ?? 0 }}</div>
        <div class="stat-lbl">切片</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-num">{{ stats.user_count ?? 0 }}</div>
        <div class="stat-lbl">用户</div>
      </div>
    </div>

    <!-- ── 功能导航 ── -->
    <div class="section-header">
      <div class="section-title">功能导航</div>
    </div>
    <div class="quick-grid">
      <router-link to="/bid" class="quick-card qc-blue">
        <div class="qc-icon">📋</div>
        <div class="qc-body">
          <div class="qc-title">标书生成</div>
          <div class="qc-desc">AI 自动编写专业投标文件</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>

      <router-link to="/kb" class="quick-card qc-green">
        <div class="qc-icon">📄</div>
        <div class="qc-body">
          <div class="qc-title">知识库</div>
          <div class="qc-desc">上传和管理企业文档</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>

      <router-link to="/kb" class="quick-card qc-orange">
        <div class="qc-icon">💬</div>
        <div class="qc-body">
          <div class="qc-title">RAG 问答</div>
          <div class="qc-desc">基于文档内容的智能问答检索</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>
    </div>

    <!-- ── 核心功能卡片 ── -->
    <div class="section-header">
      <div class="section-title">核心功能</div>
    </div>
    <div class="features-grid">
      <div class="feature-card" v-for="f in features" :key="f.title">
        <div class="fc-icon">{{ f.icon }}</div>
        <div class="fc-title">{{ f.title }}</div>
        <div class="fc-desc">{{ f.desc }}</div>
        <router-link :to="f.path" class="fc-link">
          进入 <span>→</span>
        </router-link>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import api from "../api"

const stats = ref({ document_count: 0, chunk_count: 0, user_count: 0 })

const features = [
  {
    icon: "📂",
    title: "招标文件解析",
    desc: "智能解析招标公告，提取关键信息，自动识别技术要求与评分标准",
    path: "/bid-analyze"
  },
  {
    icon: "📋",
    title: "标书智能生成",
    desc: "基于产品资料与招标要求，AI 一键生成专业投标文件",
    path: "/bid"
  },
  {
    icon: "🧠",
    title: "企业 RAG 知识库",
    desc: "私有化部署向量知识库，支持文档管理与智能问答检索",
    path: "/kb"
  },
  {
    icon: "🕒",
    title: "历史版本管理",
    desc: "标书历史版本完整保留，随时回溯对比，一键下载历史版本",
    path: "/bid"
  }
]

onMounted(async () => {
  try {
    const resp = await api.get("/api/admin/stats")
    stats.value = resp.data
  } catch {}
})
</script>

<style scoped>
.dashboard-page {
  padding: 32px 36px 64px;
  max-width: 1024px;
}

/* ── Stats Row ── */
.stats-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 20px 40px;
  margin-bottom: 32px;
}
.stat-item { flex: 1; text-align: center; }
.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-ink);
  letter-spacing: -0.6px;
  line-height: 1.2;
}
.stat-lbl {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-top: 4px;
  font-weight: 500;
}
.stat-divider {
  width: 1px;
  height: 36px;
  background: var(--color-hairline);
}

/* ── Section Header ── */
.section-header {
  margin-bottom: 14px;
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.3px;
}

/* ── Quick Grid ── */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 32px;
}

.quick-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border-radius: var(--radius-lg);
  text-decoration: none;
  transition: all 0.15s;
  border: 1px solid var(--color-hairline);
  background: var(--color-surface-1);
}
.quick-card:hover {
  border-color: var(--color-hairline-strong);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}

.qc-icon { font-size: 24px; flex-shrink: 0; }
.qc-body { flex: 1; }
.qc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
  margin-bottom: 3px;
}
.qc-desc {
  font-size: 12px;
  color: var(--color-ink-subtle);
  line-height: 1.4;
}
.qc-arrow {
  font-size: 16px;
  color: var(--color-ink-tertiary);
  flex-shrink: 0;
  transition: transform 0.15s;
}
.quick-card:hover .qc-arrow {
  transform: translateX(3px);
  color: var(--color-ink-subtle);
}

/* ── Features Grid ── */
.features-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.feature-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.15s;
}
.feature-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.1);
  transform: translateY(-2px);
}

.fc-icon { font-size: 28px; margin-bottom: 4px; }
.fc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.2px;
}
.fc-desc {
  font-size: 12px;
  color: var(--color-ink-subtle);
  line-height: 1.5;
  flex: 1;
}
.fc-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
  text-decoration: none;
  margin-top: 4px;
  transition: gap 0.15s;
}
.fc-link:hover { gap: 8px; }
.fc-link span { font-size: 14px; }

/* ── Responsive ── */
@media (max-width: 1024px) {
  .features-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    padding: 20px 16px 48px;
  }
  .stats-row {
    padding: 16px 24px;
  }
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .features-grid {
    grid-template-columns: 1fr;
  }
}
</style>
