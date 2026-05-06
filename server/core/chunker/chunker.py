"""
ClawOS X - 文本切片策略
按字符数切，支持重叠
"""
from typing import List


def chunk_by_chars(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按字符数切分文本"""
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap  # 重叠

    return chunks


def chunk_by_paragraphs(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按段落切分，尽量保持语义完整"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_chunk = ""
    current_size = 0

    for para in paragraphs:
        para_len = len(para)
        if current_size + para_len + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # 保留最后一个段落作为重叠
            overlap_text = paragraphs[paragraphs.index(para) - 1] if paragraphs.index(para) > 0 else ""
            current_chunk = overlap_text + "\n\n" + para if overlap_text else para
            current_size = len(current_chunk)
        else:
            current_chunk += ("\n\n" if current_chunk else "") + para
            current_size += para_len + 2

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def chunk_text(text: str, strategy: str = "chars", chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """统一切片入口"""
    if strategy == "paragraphs":
        return chunk_by_paragraphs(text, chunk_size, overlap)
    return chunk_by_chars(text, chunk_size, overlap)
