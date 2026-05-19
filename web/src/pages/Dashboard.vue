<template>
  <div class="dashboard-page">

    <!-- ── Hero Banner ── -->
    <div class="hero-banner">
      <div class="hero-left">
        <div class="hero-brand">
          <span class="brand-icon">⚡</span>
          <span class="brand-name">Tender</span>
        </div>
        <h1 class="hero-title">制造业投标标书<br>AI 一键生成</h1>
        <p class="hero-desc">上传产品资料 · 选择模板 · 生成专业投标文件</p>
        <div class="hero-actions">
          <router-link to="/bid" class="btn-primary">
            开始使用
            <span class="btn-arrow">→</span>
          </router-link>
          <router-link to="/chat" class="btn-ghost">
            了解更多
          </router-link>
        </div>
      </div>
      <div class="hero-right">
        <div class="security-badge">
          <div class="sb-icon">🔒</div>
          <div class="sb-text">
            <div class="sb-title">数据本地存储</div>
            <div class="sb-sub">文件不离开工厂，符合数据安全要求</div>
          </div>
        </div>
      </div>
    </div>

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

    <!-- ── 核心功能卡片 ── -->
    <div class="section-header">
      <div class="section-title">核心功能</div>
      <div class="section-sub">一站式投标标书 AI 解决方案</div>
    </div>
    <div class="features-grid">
      <div class="feature-card" v-for="f in features" :key="f.title">
        <div class="fc-icon">{{ f.icon }}</div>
        <div class="fc-title">{{ f.title }}</div>
        <div class="fc-desc">{{ f.desc }}</div>
        <router-link :to="f.path" class="fc-link">
          立即使用 <span>→</span>
        </router-link>
      </div>
    </div>

    <!-- ── 产品优势 ── -->
    <div class="section-header">
      <div class="section-title">产品优势</div>
    </div>
    <div class="advantages-row">
      <div class="adv-item" v-for="a in advantages" :key="a.title">
        <div class="adv-icon">{{ a.icon }}</div>
        <div class="adv-text">
          <div class="adv-title">{{ a.title }}</div>
          <div class="adv-desc">{{ a.desc }}</div>
        </div>
      </div>
    </div>

    <!-- ── 快捷入口 ── -->
    <div class="section-header">
      <div class="section-title">快捷入口</div>
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
          <div class="qc-desc">构建企业文档知识库，支持 PDF/Word/Excel</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>

      <router-link to="/chat" class="quick-card qc-orange">
        <div class="qc-icon">💬</div>
        <div class="qc-body">
          <div class="qc-title">RAG 问答</div>
          <div class="qc-desc">基于文档内容的智能问答检索</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>
    </div>

    <!-- ── Trust Badges ── -->
    <div class="trust-row">
      <div class="trust-item">✓ 数据本地存储</div>
      <div class="trust-item">✓ 开箱即用</div>
      <div class="trust-item">✓ 行业垂直定制</div>
      <div class="trust-item">✓ 持续迭代更新</div>
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
    desc: "基于产品资料与招标要求，AI 一键生成专业投标文件，省时省力",
    path: "/bid"
  },
  {
    icon: "🧠",
    title: "企业 RAG 知识库",
    desc: "私有化部署向量知识库，支持 PDF/Word/Excel 多格式文档检索",
    path: "/kb"
  },
  {
    icon: "🕒",
    title: "历史版本管理",
    desc: "标书历史版本完整保留，随时回溯对比，一键下载历史版本",
    path: "/bid"
  }
]

const advantages = [
  {
    icon: "🔒",
    title: "本地部署安全",
    desc: "数据不出工厂，满足企业数据安全合规要求"
  },
  {
    icon: "⚡",
    title: "AI 提升效率",
    desc: "标书编写效率提升 10 倍，减少重复劳动"
  },
  {
    icon: "🎯",
    title: "操作简单",
    desc: "上传资料 → 选择模板 → 生成标书，三步完成"
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

/* ── Hero Banner ── */
.hero-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
  border-radius: var(--radius-xl);
  padding: 40px 44px;
  margin-bottom: 24px;
  box-shadow: 0 8px 32px rgba(59, 130, 246, 0.25);
}

.hero-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.brand-icon { font-size: 20px; }
.brand-name {
  font-size: 16px;
  font-weight: 600;
  color: rgba(255,255,255,0.9);
  letter-spacing: -0.3px;
}

.hero-title {
  font-size: 30px;
  font-weight: 700;
  color: #fff;
  line-height: 1.2;
  letter-spacing: -0.8px;
  margin-bottom: 10px;
}

.hero-desc {
  font-size: 14px;
  color: rgba(255,255,255,0.75);
  margin-bottom: 24px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  color: #3B82F6;
  font-size: 14px;
  font-weight: 600;
  padding: 10px 20px;
  border-radius: var(--radius-md);
  text-decoration: none;
  transition: all 0.15s;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}
.btn-primary:hover {
  background: #F0F9FF;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.btn-arrow {
  font-size: 16px;
  transition: transform 0.15s;
}
.btn-primary:hover .btn-arrow {
  transform: translateX(3px);
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  color: rgba(255,255,255,0.85);
  font-size: 14px;
  font-weight: 500;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  text-decoration: none;
  border: 1px solid rgba(255,255,255,0.3);
  transition: all 0.15s;
}
.btn-ghost:hover {
  background: rgba(255,255,255,0.12);
  color: #fff;
}

.security-badge {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  white-space: nowrap;
}
.sb-icon { font-size: 24px; }
.sb-title {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
}
.sb-sub {
  font-size: 11px;
  color: rgba(255,255,255,0.7);
  margin-top: 2px;
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
  margin-bottom: 36px;
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
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.section-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.3px;
}
.section-sub {
  font-size: 13px;
  color: var(--color-ink-subtle);
}

/* ── Core Features Grid ── */
.features-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 36px;
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

/* ── Advantages Row ── */
.advantages-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 36px;
}

.adv-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 18px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
}
.adv-icon { font-size: 22px; flex-shrink: 0; margin-top: 2px; }
.adv-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ink);
  margin-bottom: 4px;
}
.adv-desc {
  font-size: 12px;
  color: var(--color-ink-subtle);
  line-height: 1.5;
}

/* ── Quick Grid ── */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 24px;
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

/* ── Trust Row ── */
.trust-row {
  display: flex;
  gap: 24px;
  justify-content: center;
  flex-wrap: wrap;
}
.trust-item {
  font-size: 13px;
  color: var(--color-ink-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .features-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .advantages-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    padding: 20px 16px 48px;
  }
  .hero-banner {
    flex-direction: column;
    align-items: flex-start;
    padding: 28px 24px;
  }
  .hero-title { font-size: 24px; }
  .hero-actions { flex-wrap: wrap; }
  .features-grid {
    grid-template-columns: 1fr;
  }
  .advantages-row {
    grid-template-columns: 1fr;
  }
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .stats-row {
    padding: 16px 24px;
  }
  .security-badge {
    display: none;
  }
}
</style>