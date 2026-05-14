"""
ClawOS X - 标书查重模块
基于向量相似度检测标书之间的内容重复率
"""
import json
from typing import Optional
from server.db.sqlite import get_db
from server.db.chromadb import query_chunks
from server.core.embedder.embedder import get_embedder


class PlagiarismChecker:
    """
    标书查重器：检测新生成的标书与历史标书的相似程度。
    用于识别：重复使用历史标书、直接抄袭、段落后高度重复等问题。
    """

    def __init__(self):
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def check(self, bid_content: str, exclude_doc_ids: list[int] = None,
              top_k_per_section: int = 3, section_threshold: float = 0.85) -> dict:
        """
        对一段标书正文进行查重检测

        Args:
            bid_content: 待检测的标书正文（Markdown 格式）
            exclude_doc_ids: 排除的文档ID（如当前正在生成中的标书）
            top_k_per_section: 每个章节片段取多少个最相似结果
            section_threshold: 章节相似度阈值，超过则标记为高风险

        Returns:
            {
                "passed": bool,                    # 是否通过查重（false=有严重重复）
                "overall_score": float,            # 整体相似度 0-100
                "total_sections": int,             # 检测的章节总数
                "high_risk_sections": int,         # 高风险章节数
                "sections": [
                    {
                        "section_name": str,
                        "section_index": int,
                        "section_text": str,       # 章节原文（前200字）
                        "similarity_score": float,  # 相似度 0-100
                        "risk_level": str,          # high/mid/low
                        "matched_bids": [
                            {
                                "doc_id": int,
                                "filename": str,
                                "chunk_text": str,   # 最相似的段落
                                "similarity": float, # 与该历史标书的相似度
                            }
                        ]
                    }
                ],
                "summary": {
                    "total_chunks": int,           # 检测的切片总数
                    "repetitive_chunks": int,       # 重复切片数（相似度>85%）
                    "avg_similarity": float,        # 平均相似度
                    "max_similarity": float,        # 最高相似度
                }
            }
        """
        # 1. 把标书正文按章节拆分
        sections = self._split_sections(bid_content)

        if not sections:
            return {
                "passed": True,
                "overall_score": 0.0,
                "total_sections": 0,
                "high_risk_sections": 0,
                "sections": [],
                "summary": {"total_chunks": 0, "repetitive_chunks": 0,
                            "avg_similarity": 0.0, "max_similarity": 0.0}
            }

        # 2. 过滤掉 exclude_doc_ids 对应的 chunks（避免"自己和自己比"）
        all_similarity_data = []
        section_results = []

        for idx, (sec_name, sec_text) in enumerate(sections):
            if not sec_text.strip():
                continue

            # 取章节切片的前500字做检索（截断避免超长）
            query_text = sec_text[:800]

            # 从 ChromaDB 检索（排除指定 doc_ids）
            chunks = query_chunks(query_text, top_k=top_k_per_section * 3)

            # 按 doc_id 过滤
            if exclude_doc_ids:
                chunks = [c for c in chunks if c["metadata"].get("doc_id") not in exclude_doc_ids]

            # 按 doc_id 聚类，取每个 doc 的最高相似度
            doc_scores: dict[int, dict] = {}
            for chunk in chunks:
                doc_id = chunk["metadata"].get("doc_id")
                if not doc_id:
                    continue
                score = 1 - chunk.get("distance", 1.0)
                if doc_id not in doc_scores or score > doc_scores[doc_id]["score"]:
                    doc_scores[doc_id] = {
                        "score": score,
                        "chunk_text": chunk["text"],
                        "doc_id": doc_id,
                    }

            matched_bids = []
            for doc_id, data in sorted(doc_scores.items(), key=lambda x: x[1]["score"], reverse=True):
                if data["score"] < 0.5:  # 低于50%相似度不显示
                    continue
                # 查文档名
                matched_bids.append({
                    "doc_id": doc_id,
                    "filename": self._get_filename(doc_id),
                    "chunk_text": data["chunk_text"][:300],
                    "similarity": round(data["score"] * 100, 1),
                })

            similarity_score = 0.0
            if matched_bids:
                similarity_score = matched_bids[0]["similarity"]

            if similarity_score >= section_threshold * 100:
                risk_level = "high"
            elif similarity_score >= 70:
                risk_level = "mid"
            else:
                risk_level = "low"

            section_results.append({
                "section_name": sec_name or f"第{idx + 1}节",
                "section_index": idx,
                "section_text": sec_text[:200],
                "similarity_score": round(similarity_score, 1),
                "risk_level": risk_level,
                "matched_bids": matched_bids[:3],
            })

            all_similarity_data.append(similarity_score)

        # 3. 计算整体相似度
        total = len(all_similarity_data)
        high_risk = sum(1 for s in section_results if s["risk_level"] == "high")

        overall_score = round(sum(all_similarity_data) / total, 1) if total else 0.0
        max_similarity = round(max(all_similarity_data), 1) if all_similarity_data else 0.0

        return {
            "passed": high_risk == 0,
            "overall_score": overall_score,
            "total_sections": total,
            "high_risk_sections": high_risk,
            "sections": section_results,
            "summary": {
                "total_chunks": sum(1 for s in section_results if s["matched_bids"]),
                "repetitive_chunks": sum(1 for s in section_results if s["similarity_score"] >= 85),
                "avg_similarity": overall_score,
                "max_similarity": max_similarity,
            }
        }

    def check_batch(self, bid_contents: list[str],
                    doc_ids: list[int]) -> list[dict]:
        """
        批量查重：一次性检测多份标书（两两对比）

        Returns:
            [
                {"doc_id_a": int, "doc_id_b": int, "similarity": float}
            ]
        """
        if len(bid_contents) < 2:
            return []

        results = []
        n = len(bid_contents)
        for i in range(n):
            for j in range(i + 1, n):
                content_a = bid_contents[i][:2000]
                content_b = bid_contents[j][:2000]

                # 简单：用 embedder 比对两段文本的相似度
                try:
                    vec_a = self.embedder.embed([content_a])[0]
                    vec_b = self.embedder.embed([content_b])[0]
                    similarity = self._cosine_similarity(vec_a, vec_b)
                    results.append({
                        "doc_id_a": doc_ids[i],
                        "doc_id_b": doc_ids[j],
                        "similarity": round(similarity * 100, 1),
                    })
                except Exception:
                    continue

        return results

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """按 Markdown 标题拆分标书为章节列表"""
        import re
        lines = text.split("\n")
        sections = []
        current_title = ""
        current_content = []

        for line in lines:
            m = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
            if m:
                if current_content:
                    sections.append((current_title, "\n".join(current_content)))
                current_title = m.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        if current_content:
            sections.append((current_title, "\n".join(current_content)))

        if not sections:
            # 没有标题，按段落拆分（每500字一片）
            chunks = self._chunk_text(text, 500)
            sections = [(f"片段{i + 1}", c) for i, c in enumerate(chunks)]

        return sections

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        """按字符数拆分文本"""
        paragraphs = text.split("\n")
        chunks = []
        current = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) > chunk_size and current:
                chunks.append("\n".join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para) + 1

        if current:
            chunks.append("\n".join(current))

        return chunks if chunks else [text]

    def _get_filename(self, doc_id: int) -> str:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        conn.close()
        return row["filename"] if row else f"doc_{doc_id}"

    @staticmethod
    def _cosine_similarity(vec_a: list, vec_b: list) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# 单例
_checker = None


def get_plagiarism_checker() -> PlagiarismChecker:
    global _checker
    if _checker is None:
        _checker = PlagiarismChecker()
    return _checker