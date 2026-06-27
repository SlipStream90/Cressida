import pytest
from unittest.mock import patch, MagicMock
import os


@pytest.fixture
def faiss_dir(tmp_path):
    return str(tmp_path / "faiss")


class TestVectorService:
    def test_module_imports(self):
        from app.services.vector_service import VectorService
        assert VectorService

    def test_index_exists_returns_false_for_missing(self):
        from app.services.vector_service import VectorService
        svc = VectorService(dimension=768)
        result = svc.index_exists("nonexistent_user")
        assert result is False

    def test_search_similar_returns_empty_for_missing_index(self):
        from app.services.vector_service import VectorService
        svc = VectorService(dimension=768)
        result = svc.search_similar("no_index_user", [0.1] * 768, top_k=5)
        assert result == []

    def test_default_dimension(self):
        from app.services.vector_service import VectorService
        svc = VectorService()
        assert svc.dimension == 768

    def test_cold_start_returns_empty(self):
        from app.services.vector_service import VectorService
        svc = VectorService(dimension=768)
        result = svc.search_similar("new_user_cold", [0.1] * 768)
        assert result == []

    def test_add_vectors_creates_new_index(self, faiss_dir):
        with patch("app.services.vector_service.settings.faiss_index_dir", faiss_dir):
            from app.services.vector_service import VectorService
            svc = VectorService(dimension=8)
            svc.add_vectors("test_user_add", [[0.1] * 8, [0.2] * 8])
            assert svc.index_exists("test_user_add")

    def test_search_similar_returns_indices(self, faiss_dir):
        with patch("app.services.vector_service.settings.faiss_index_dir", faiss_dir):
            from app.services.vector_service import VectorService
            svc = VectorService(dimension=8)
            svc.add_vectors("test_user_search", [[0.1] * 8, [0.2] * 8])
            results = svc.search_similar("test_user_search", [0.1] * 8, top_k=1)
            assert len(results) == 1

    def test_add_vectors_appends_to_existing(self, faiss_dir):
        with patch("app.services.vector_service.settings.faiss_index_dir", faiss_dir):
            from app.services.vector_service import VectorService
            svc = VectorService(dimension=8)
            svc.add_vectors("test_user_append", [[0.1] * 8])
            svc.add_vectors("test_user_append", [[0.2] * 8, [0.3] * 8])
            results = svc.search_similar("test_user_append", [0.1] * 8, top_k=1)
            assert len(results) == 1

    def test_persistence_survives_reload(self, faiss_dir):
        with patch("app.services.vector_service.settings.faiss_index_dir", faiss_dir):
            from app.services.vector_service import VectorService
            svc1 = VectorService(dimension=8)
            svc1.add_vectors("persist_user", [[0.1] * 8, [0.2] * 8])
            svc2 = VectorService(dimension=8)
            assert svc2.index_exists("persist_user")
            results = svc2.search_similar("persist_user", [0.1] * 8, top_k=1)
            assert len(results) == 1
