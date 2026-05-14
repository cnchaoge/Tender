import axios from "axios"

const isDev = import.meta.env.DEV

// axios 实例：dev 模式走相对路径（由 Vite proxy 转发），生产模式用完整 URL
const http = axios.create({
  baseURL: isDev ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000"),
  timeout: 60000
})

http.interceptors.response.use(
  resp => resp,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
      window.location.href = "/login"
    }
    return Promise.reject(err)
  }
)

// ── 认证 ─────────────────────────────────────────────────────────────────────
const auth = {
  login: (username, password) => http.post("/api/auth/login", { username, password }),
  logout: () => http.post("/api/auth/logout"),
  me: () => http.get("/api/auth/me"),
}

// ── 知识库 ────────────────────────────────────────────────────────────────────
const kb = {
  list: () => http.get("/api/kb/documents"),
  upload: (formData) => http.post("/api/kb/documents", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  }),
  delete: (id) => http.delete(`/api/kb/documents/${id}`),
  getChunks: (id) => http.get(`/api/kb/documents/${id}/chunks`),
}

// ── RAG 问答 ──────────────────────────────────────────────────────────────────
const rag = {
  query: (question, top_k, stream) => http.post("/api/rag/query", { question, top_k, stream }),
  chat: (messages) => http.post("/api/rag/chat", { messages }),
}

// ── 标书生成 ──────────────────────────────────────────────────────────────────
const bid = {
  parse: (filePath) => http.post("/api/bid/parse", { file_path: filePath }),
  generate: (parseResult, materials) => http.post("/api/bid/generate", {
    parse_result: parseResult,
    materials
  }),
  generateStream: (parseResult, materials) => http.post("/api/bid/generate/stream", {
    parse_result: parseResult,
    materials
  }, { timeout: 300000 }),
  download: (filename) => {
    const base = isDev ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000")
    return `${base}/api/bid/download/${filename}`
  },
  matchCheck: (parseResult, materials) =>
    http.post("/api/bid/match_check", { parse_result: parseResult, materials }),
  analyzeOld: (docId) => http.post(`/api/bid/analyze-old/${docId}`),
  analyzeOldSections: (docId) => http.get(`/api/bid/analyze-old/${docId}/sections`),
  violationCheck: (payload) => http.post("/api/bid/violation_check", payload),
  getDisqualifyRules: () => http.get("/api/bid/disqualify_rules"),
  getViolationCases: (category) => http.get("/api/bid/violation_cases", { params: { category } }),
  plagiarismCheck: (bidContent, excludeDocIds) =>
    http.post("/api/bid/plagiarism_check", { bid_content: bidContent, exclude_doc_ids: excludeDocIds }),
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
export { http, api, auth, kb, rag, bid, admin }