import axios from "axios"

// Same-origin `/api`. Dev Vite proxies `/api` to the backend. A production
// build is served by that same process, so a page opened with a LAN address
// still talks to the host that served the page.
export function apiBase() {
  return ""
}

const http = axios.create({
  baseURL: apiBase(),
  timeout: 60000
})

export function redirectToLogin() {
  localStorage.removeItem("token")
  localStorage.removeItem("user")
  if (window.location.pathname !== "/login") {
    window.location.href = "/login"
  }
}

http.interceptors.request.use(config => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  resp => resp,
  err => {
    const url = err.config?.url || ""
    // Wrong password is also 401; stay on the login form so the error can show.
    if (err.response?.status === 401 && !url.includes("/api/auth/login")) {
      redirectToLogin()
    }
    if (err.response?.status === 403 && err.response?.data?.detail === "必须先修改密码") {
      try {
        const stored = JSON.parse(localStorage.getItem("user") || "null")
        if (stored) {
          stored.must_change_password = true
          localStorage.setItem("user", JSON.stringify(stored))
        }
      } catch {
        // Ignore a corrupt local user cache; the redirect still applies.
      }
      if (window.location.pathname !== "/change-password") {
        window.location.href = "/change-password"
      }
    }
    return Promise.reject(err)
  }
)

// fetch() (SSE streams) does not use the axios interceptors above.
export async function authFetch(url, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = localStorage.getItem("token") || ""
  if (token) {
    headers.set("Authorization", `Bearer ${token}`)
  }
  const resp = await fetch(url, { ...options, headers })
  if (resp.status === 401) {
    redirectToLogin()
    const error = new Error("未登录")
    error.status = 401
    throw error
  }
  return resp
}

export async function downloadWithAuth(path, filename) {
  const resp = await authFetch(`${apiBase()}${path}`)
  if (!resp.ok) {
    let detail = ""
    try {
      const data = await resp.json()
      detail = data.detail || ""
    } catch {
      detail = ""
    }
    const error = new Error(detail || `下载失败 (${resp.status})`)
    error.status = resp.status
    throw error
  }
  const blob = await resp.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = objectUrl
  a.download = filename || "download"
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

// ── 认证 ─────────────────────────────────────────────────────────────────────
const auth = {
  login: (username, password) => http.post("/api/auth/login", { username, password }),
  logout: () => http.post("/api/auth/logout"),
  me: () => http.get("/api/auth/me"),
  changePassword: (oldPassword, newPassword) =>
    http.post("/api/auth/change-password", {
      old_password: oldPassword,
      new_password: newPassword,
    }),
}

// ── 知识库 ────────────────────────────────────────────────────────────────────
const kb = {
  list: () => http.get("/api/kb/documents"),
  upload: (formData) => http.post("/api/kb/documents", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000,
  }),
  status: (id) => http.get(`/api/kb/documents/${id}/status`),
  folder: (folderPath) => http.get("/api/kb/folder", { params: { folder_path: folderPath } }),
  delete: (id) => http.delete(`/api/kb/documents/${id}`),
  getChunks: (id) => http.get(`/api/kb/documents/${id}/chunks`),
}

// ── RAG 问答 ──────────────────────────────────────────────────────────────────
const rag = {
  query: (question, top_k, stream) => http.post("/api/rag/query", { question, top_k, stream }),
}

// ── 标书生成 ──────────────────────────────────────────────────────────────────
const bid = {
  parse: (filePath) => http.post("/api/bid/parse", { file_path: filePath }),
  // 标书正文只走 SSE。页面此前用 authFetch 手写这一请求，axios 版 generate / generateStream
  // 没有调用方，而且 axios 会把整段事件流缓冲完，带不上章节和策略。
  openGenerateStream: (payload) => authFetch(`${apiBase()}/api/bid/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  download: (filename) => downloadWithAuth(
    `/api/bid/download/${encodeURIComponent(filename)}`,
    filename
  ),
  matchCheck: (parseResult, materials) =>
    http.post("/api/bid/match_check", { parse_result: parseResult, materials }),
  recommendPreview: (docId, payload) =>
    http.post(`/api/bid/recommend/${docId}/preview`, payload || {}),
  analyzeOld: (docId) => http.post(`/api/bid/analyze-old/${docId}`),
  analyzeOldSections: (docId) => http.get(`/api/bid/analyze-old/${docId}/sections`),
  violationCheck: (payload) => http.post("/api/bid/violation_check", payload),
  getDisqualifyRules: () => http.get("/api/bid/disqualify_rules"),
  getViolationCases: (category) => http.get("/api/bid/violation_cases", { params: { category } }),
  plagiarismCheck: (bidContent, excludeDocIds) =>
    http.post("/api/bid/plagiarism_check", { bid_content: bidContent, exclude_doc_ids: excludeDocIds }),
}

// ── 报价分析 ──────────────────────────────────────────────────────────────────
const price = {
  parseFormula: (scoring, rawText) => http.post("/api/price/parse-formula", { scoring, raw_text: rawText }),
  calculate: (formulaJson, costPrice, competitorCount) =>
    http.post("/api/price/calculate", { formula_json: formulaJson, cost_price: costPrice, competitor_count: competitorCount }),
  save: (data) => http.post("/api/price/save", data),
  history: (limit) => http.get("/api/price/history", { params: { limit } }),
  historyDetail: (id) => http.get(`/api/price/history/${id}`),
  deleteHistory: (id) => http.delete(`/api/price/history/${id}`),
  formulaTemplates: () => http.get("/api/price/formula-templates"),
}

// ── 检查清单 ──────────────────────────────────────────────────────────────────
const checklist = {
  generate: (bidVersionId, bidContent, parseResult, projectId) =>
    http.post("/api/checklist/generate", {
      bid_version_id: bidVersionId,
      bid_content: bidContent,
      parse_result: parseResult,
      project_id: projectId || null,
    }),
  get: (bidVersionId) => http.get(`/api/checklist/${bidVersionId}`),
  updateItem: (itemId, data) => http.put(`/api/checklist/item/${itemId}`, data),
  addItem: (data) => http.post("/api/checklist/item", data),
  deleteItem: (itemId) => http.delete(`/api/checklist/item/${itemId}`),
  exportData: (bidVersionId) => http.get(`/api/checklist/export/${bidVersionId}`),
  categories: () => http.get("/api/checklist/categories"),
}

// ── 管理后台 ──────────────────────────────────────────────────────────────────
const admin = {
  listUsers: () => http.get("/api/admin/users"),
  createUser: (data) => http.post("/api/admin/users", data),
  updateUser: (id, data) => http.put(`/api/admin/users/${id}`, data),
  deleteUser: (id) => http.delete(`/api/admin/users/${id}`),
  getStats: () => http.get("/api/admin/stats"),
  getConfig: () => http.get("/api/admin/config"),
  updateConfig: (data) => http.put("/api/admin/config", data),
  saveModel: (data) => http.post("/api/admin/model/config", data),
  saveEmbed: (data) => http.post("/api/admin/embed/config", data),
}

// 统一导出：default = axios 实例（兼容 import api from），named exports 也有完整对象
const api = http

export default api  // 必须是 axios 实例本身，不能是包含 api 的对象
export { http, api, auth, kb, rag, bid, admin, price, checklist }