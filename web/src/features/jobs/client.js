import { apiBase, authFetch } from "../../api/index.js"

export function createJob(body) {
  return authFetch(`${apiBase()}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(readJson)
}

export function getJob(jobId) {
  return authFetch(`${apiBase()}/api/jobs/${jobId}`).then(readJson)
}

export function listJobs(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value))
  })
  const suffix = query.toString() ? `?${query}` : ""
  return authFetch(`${apiBase()}/api/jobs${suffix}`).then(readJson)
}

export function readJobLog(jobId) {
  return authFetch(`${apiBase()}/api/jobs/${jobId}/log`).then(readJson)
}

export function cancelJob(jobId) {
  return authFetch(`${apiBase()}/api/jobs/${jobId}/cancel`, { method: "POST" }).then(readJson)
}

export function cancelJobKeepalive(jobId) {
  const token = localStorage.getItem("token") || ""
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  return fetch(`${apiBase()}/api/jobs/${jobId}/cancel`, {
    method: "POST",
    headers,
    keepalive: true,
  }).catch(() => {})
}

export async function readJobEvents(jobId, { after = 0, cancelOnDisconnect = false, onEvent, signal } = {}) {
  const url = `${apiBase()}/api/jobs/${jobId}/events?after=${after}&cancel_on_disconnect=${cancelOnDisconnect ? "true" : "false"}`
  const resp = await authFetch(url, { signal })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail || `请求失败 ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      const raw = line.slice(6).trim()
      if (!raw) continue
      try {
        const data = JSON.parse(raw)
        if (onEvent) onEvent(data)
      } catch {
        // 半行或心跳忽略
      }
    }
  }
}

export async function waitForJob(jobId, onEvent) {
  await readJobEvents(jobId, { cancelOnDisconnect: false, onEvent })
  const job = await getJob(jobId)
  if (job.status !== "succeeded") {
    const error = new Error(job.message || "作业没有完成")
    error.job = job
    throw error
  }
  return job.result || {}
}

async function readJson(resp) {
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    const error = new Error(data.detail || `请求失败 ${resp.status}`)
    error.status = resp.status
    throw error
  }
  return data
}
