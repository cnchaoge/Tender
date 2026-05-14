import axios from "axios"

const isDev = import.meta.env.DEV

const api = axios.create({
  baseURL: isDev ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000"),
  timeout: 60000
})

api.interceptors.response.use(
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

const auth = {
  login: (username, password) => api.post("/api/auth/login", { username, password }),
  logout: () => api.post("/api/auth/logout"),
  me: () => api.get("/api/auth/me"),
}

const kb = {
  list: () => api.get("/api/kb/documents"),
  upload: (formData) => api.post("/api/kb/documents", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  }),
  delete: (id) => api.delete(`/api/kb/documents/${id}`),
  getChunks: (id) => api.get(`/api/kb/documents/${id}/chunks`),
}

const rag = {
  query: (question, top_k, stream) => api.post("/api/rag/query", { question, top_k, stream }),
  chat: (messages) => api.post("/api/rag/chat", { messages }),
}

const bid = {
  parse: (filePath) => api.post("/api/bid/parse", { file_path: filePath }),
  generate: (parseResult, materials) => api.post("/api/bid/generate", {
    parse_result: parseResult,
    materials
  }),
  generateStream: (parseResult, materials) => api.post("/api/bid/generate/stream", {
    parse_result: parseResult,
    materials
  }, { timeout: 300000 }),
  download: (filename) => {
    const base = isDev ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000")
    return `${base}/api/bid/download/${filename}`
  },
  matchCheck: (parseResult, materials) =>
    api.post("/api/bid/match_check", { parse_result: parseResult, materials }),
  analyzeOld: (docId) => api.post(`/api/bid/analyze-old/${docId}`),
  analyzeOldSections: (docId) => api.get(`/api/bid/analyze-old/${docId}/sections`),
  violationCheck: (payload) => api.post("/api/bid/violation_check", payload),
  getDisqualifyRules: () => api.get("/api/bid/disqualify_rules"),
  getViolationCases: (category) => api.get("/api/bid/violation_cases", { params: { category } }),
  plagiarismCheck: (bidContent, excludeDocIds) =>
    api.post("/api/bid/plagiarism_check", { bid_content: bidContent, exclude_doc_ids: excludeDocIds }),
}

const admin = {
  listUsers: () => api.get("/api/admin/users"),
  createUser: (data) => api.post("/api/admin/users", data),
  updateUser: (id, data) => api.put(`/api/admin/users/${id}`, data),
  deleteUser: (id) => api.delete(`/api/admin/users/${id}`),
  getStats: () => api.get("/api/admin/stats"),
  getConfig: () => api.get("/api/admin/config"),
  updateConfig: (data) => api.put("/api/admin/config", data),
}

export { api }
export default { api, auth, kb, rag, bid, admin }