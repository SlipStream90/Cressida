import os
from pathlib import Path

import numpy as np

FAISS_INDEX_DIR = Path("echo/faiss_index")


class VectorService:
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    def _index_path(self, user_id: str) -> Path:
        return FAISS_INDEX_DIR / f"{user_id}.index"

    def index_exists(self, user_id: str) -> bool:
        return self._index_path(user_id).exists()

    def search_similar(self, user_id: str, query_vector: list[float], top_k: int = 5) -> list[int]:
        import faiss
        path = self._index_path(user_id)
        if not path.exists():
            return []
        index = faiss.read_index(str(path))
        query = np.array([query_vector], dtype=np.float32)
        distances, indices = index.search(query, top_k)
        return indices[0].tolist()

    def add_vectors(self, user_id: str, vectors: list[list[float]]) -> None:
        import faiss
        path = self._index_path(user_id)
        vec_array = np.array(vectors, dtype=np.float32)
        if path.exists():
            index = faiss.read_index(str(path))
            index.add(vec_array)
        else:
            index = faiss.IndexFlatL2(self.dimension)
            index.add(vec_array)
        faiss.write_index(index, str(path))
