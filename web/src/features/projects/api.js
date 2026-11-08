import api from "../../api"

export function listProjects() {
  return api.get("/api/projects")
}

export function createProject(body = {}) {
  return api.post("/api/projects", body)
}

export function getProject(id) {
  return api.get(`/api/projects/${id}`)
}

export function updateProject(id, body) {
  return api.put(`/api/projects/${id}`, body)
}

export function uploadTender(id, formData) {
  return api.post(`/api/projects/${id}/tender`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300000,
  })
}

export function setProjectMaterials(id, documentIds) {
  return api.put(`/api/projects/${id}/materials`, { document_ids: documentIds })
}

export function saveProjectSnapshot(id, body) {
  return api.put(`/api/projects/${id}/snapshot`, body)
}

export function queryProjectId(query) {
  const raw = query?.project_id
  const value = Array.isArray(raw) ? raw[0] : raw
  const id = Number(value)
  return Number.isFinite(id) && id > 0 ? id : null
}
