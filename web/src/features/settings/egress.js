// 与 server/domain/jobs/runtime.py 的出境说明保持同一句。
export const CLOUD_EGRESS_NOTE =
  "egress=cloud：使用云端模型时，该次作业的提示词和所需正文会离开本机，发往该服务商。不会发送整个 data 目录。"

const LLM_EGRESS = {
  ollama: "local",
  bge: "local",
  m3e: "local",
  deepseek: "cloud",
  dashscope: "cloud",
  openai: "cloud",
  minimax: "cloud",
  mock: "dev",
}

const EMBED_EGRESS = {
  ollama: "local",
  bge: "local",
  m3e: "local",
  dashscope: "cloud",
  deepseek: "cloud",
  openai: "cloud",
  minimax: "cloud",
  mock: "dev",
}

export function egressOf(kind, provider) {
  const table = kind === "embed" ? EMBED_EGRESS : LLM_EGRESS
  const key = String(provider || "").trim().toLowerCase()
  if (table[key]) return table[key]
  return "cloud"
}

export function jobEgressNote(runtime) {
  if (!runtime || runtime.egress !== "cloud") return ""
  return runtime.note || CLOUD_EGRESS_NOTE
}
