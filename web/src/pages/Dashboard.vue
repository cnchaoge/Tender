<template>
  <div class="dashboard-page">

    <!-- Hero Banner -->
    <div class="hero-banner">
      <div class="hero-left">
        <div class="hero-brand">
          <span class="brand-icon">⚡</span>
          <span class="brand-name">ClawOS X</span>
        </div>
        <h1 class="hero-title">制造业投标标书<br>AI 一键生成</h1>
        <p class="hero-desc">上传产品资料 · 选择模板 · 生成专业投标文件</p>
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

    <!-- Stats Row -->
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

    <!-- Quick Actions -->
    <div class="section-title">快速开始</div>
    <div class="quick-grid">
      <router-link to="/kb" class="quick-card qc-blue">
        <div class="qc-icon">📄</div>
        <div class="qc-body">
          <div class="qc-title">上传文档</div>
          <div class="qc-desc">构建知识库，支持 PDF/Word/Excel</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>

      <router-link to="/chat" class="quick-card qc-green">
        <div class="qc-icon">💬</div>
        <div class="qc-body">
          <div class="qc-title">RAG 问答</div>
          <div class="qc-desc">基于文档内容的智能问答检索</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>

      <router-link to="/bid" class="quick-card qc-orange">
        <div class="qc-icon">📋</div>
        <div class="qc-body">
          <div class="qc-title">生成标书</div>
          <div class="qc-desc">AI 自动编写专业投标文件</div>
        </div>
        <div class="qc-arrow">→</div>
      </router-link>
    </div>

    <!-- Trust Badges -->
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
  max-width: 960px;
}

/* ── Hero Banner ── */
.hero-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: var(--color-primary);
  border-radius: var(--radius-xl);
  padding: 36px 40px;
  margin-bottom: 24px;
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
  color: rgba(255,255,255,0.7);
}

.security-badge {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  white-space: nowrap;
}
.sb-icon { font-size: 22px; }
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
  margin-bottom: 32px;
}
.stat-item {
  flex: 1;
  text-align: center;
}
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

/* ── Section Title ── */
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.2px;
  margin-bottom: 14px;
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
@media (max-width: 768px) {
  .dashboard-page {
    padding: 20px 16px 48px;
  }
  .hero-banner {
    flex-direction: column;
    align-items: flex-start;
    padding: 24px;
  }
  .hero-title { font-size: 22px; }
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .stats-row {
    padding: 16px 24px;
  }
}
</style>
