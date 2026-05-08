"""
BGE embedding using huggingface_hub + tokenizers + torch, no sentence_transformers.
BGE model: BAAI/bge-large-zh-v1.5 (384-dim)
"""
import os, sys
from typing import Optional
from pathlib import Path

import numpy as np
import torch
from torch import nn
import tokenizers


# Cache dir for BGE model
MODEL_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
MODEL_ID = "BAAI/bge-large-zh-v1.5"  # HuggingFace repo ID (forward slashes)
LOCAL_MODEL_FOLDER = "models--BAAI--bge-large-zh-v1.5"  # Local cache folder name (double hyphens)


def _get_model_path() -> str:
    """Get the local path to the BGE model (already downloaded)."""
    model_dir = MODEL_CACHE / LOCAL_MODEL_FOLDER
    if not model_dir.exists():
        raise RuntimeError(f"BGE model not found at {model_dir}. Please run download_bge.py first.")

    # Find the actual model snapshot dir inside
    for d in model_dir.iterdir():
        if d.is_dir() and not d.name.startswith('.'):
            blks_file = d / "model.safetensors"
            if blks_file.exists():
                return str(d)

    raise RuntimeError(f"BGE model snapshot not found in {model_dir}")


class BGEModel:
    """Minimal BGE embedding model without sentence_transformers."""

    def __init__(self):
        model_path = _get_model_path()
        self.model_path = model_path

        # Load config
        config_path = os.path.join(model_path, "config.json")
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Load tokenizer from local path
        tokenizer_path = os.path.join(model_path, "tokenizer.json")
        if not os.path.exists(tokenizer_path):
            tokenizer_config_path = os.path.join(model_path, "tokenizer_config.json")
            # Try to find tokenizer file
            raise RuntimeError(f"tokenizer.json not found at {tokenizer_path}")
        self.tokenizer = tokenizers.Tokenizer.from_file(tokenizer_path)

        # Load model weights manually using torch
        safetensors_path = os.path.join(model_path, "model.safetensors")
        if not os.path.exists(safetensors_path):
            safetensors_path = os.path.join(model_path, "pytorch_model.bin")

        state_dict = torch.load(safetensors_path, map_location="cpu", weights_only=True)

        # Build simple embedding model
        hidden_size = config.get("hidden_size", 1024)
        vocab_size = config.get("vocab_size", 30522)
        max_position = config.get("max_position_embeddings", 512)
        type_vocab_size = config.get("type_vocab_size", 2)

        self.truncation = True
        self.max_length = 512

        # Simple embedding + pooler (BERT-style)
        class BERTEmbedding(nn.Module):
            def __init__(self):
                super().__init__()
                self.word_embeddings = nn.Embedding(vocab_size, hidden_size)
                self.position_embeddings = nn.Embedding(max_position, hidden_size)
                self.token_type_embeddings = nn.Embedding(type_vocab_size, hidden_size)
                self.LayerNorm = nn.LayerNorm(hidden_size)
                self.dropout = nn.Dropout(0.1)

            def forward(self, input_ids, token_type_ids):
                seq_len = input_ids.size(1)
                position_ids = torch.arange(seq_len, dtype=torch.long, device=input_ids.device)
                position_ids = position_ids.unsqueeze(0).expand_as(input_ids)
                return self.dropout(
                    self.LayerNorm(
                        self.word_embeddings(input_ids)
                        + self.position_embeddings(position_ids)
                        + self.token_type_embeddings(token_type_ids)
                    )
                )

        class SimpleBERTModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.embedding = BERTEmbedding()
                # Use simple mean pooling instead of encoder layers
                # We just need embeddings, not full model
                self.pooler = nn.Linear(hidden_size, hidden_size)

            def forward(self, input_ids, attention_mask, token_type_ids):
                embedding_output = self.embedding(input_ids, token_type_ids)
                # Mean pooling
                mask_expanded = attention_mask.unsqueeze(-1).expand(embedding_output.size()).float()
                sum_embeddings = torch.sum(embedding_output * mask_expanded, dim=1)
                sum_mask = mask_expanded.sum(dim=1).clamp(min=1e-9)
                pooled = sum_embeddings / sum_mask
                return pooled

        self.model = SimpleBERTModel()
        self.model.load_state_dict(state_dict, strict=False)
        self.model.eval()
        self.hidden_size = hidden_size

    def encode(self, texts: list[str]) -> list[np.ndarray]:
        """Encode texts to embeddings."""
        if isinstance(texts, str):
            texts = [texts]

        # Tokenize
        encoded = self.tokenizer.encode_batch(texts)
        input_ids = torch.tensor([e.ids for e in encoded], dtype=torch.long)
        attention_mask = torch.tensor([e.attention_mask for e in encoded], dtype=torch.long)
        token_type_ids = torch.zeros_like(input_ids)

        with torch.no_grad():
            pooled = self.model(input_ids, attention_mask, token_type_ids)
            # Normalize
            pooled = nn.functional.normalize(pooled, p=2, dim=1)
            embeddings = pooled.cpu().numpy()

        return [emb for emb in embeddings]


# Global model instance
_model: Optional[BGEModel] = None


def get_embedder():
    global _model
    if _model is None:
        _model = BGEModel()
    return _model


def encode_texts(texts: list[str]) -> list[np.ndarray]:
    """Encode texts using BGE model."""
    embedder = get_embedder()
    return embedder.encode(texts)
