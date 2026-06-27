import pytest
from unittest.mock import patch, MagicMock


class TestWorkflowState:
    def test_workflow_state_typeddict(self):
        from app.workflow.state import WorkflowState
        state: WorkflowState = {
            "segment_id": "seg1",
            "segment_text": "Hello",
            "user_id": "u1",
            "session_id": "s1",
            "style_scores": {"suspense": 0.5, "dialogue": 0.5},
            "variants": [],
            "selected_variant": None,
            "audio_url": None,
            "feedback_collected": False,
            "preference_updated": False,
        }
        assert state["segment_id"] == "seg1"
        assert state["segment_text"] == "Hello"
        assert state["feedback_collected"] is False


class TestWorkflowNodes:
    def test_node_functions_exist(self):
        from app.workflow.nodes import (
            load_context, retrieve_preference, generate_variants,
            select_best, synthesize_audio, collect_feedback,
            update_preference, complete
        )
        assert callable(load_context)
        assert callable(retrieve_preference)
        assert callable(generate_variants)
        assert callable(select_best)
        assert callable(synthesize_audio)
        assert callable(collect_feedback)
        assert callable(update_preference)
        assert callable(complete)


class TestWorkflowCheckpointer:
    def test_with_checkpointer_imports(self):
        from app.workflow.checkpointer import with_checkpointer
        assert callable(with_checkpointer)

    @patch("app.workflow.checkpointer.os.environ.get")
    def test_with_checkpointer_redis_available(self, mock_get):
        from app.workflow.checkpointer import with_checkpointer

        mock_get.return_value = "redis://localhost:6379"
        with patch("app.workflow.checkpointer.RedisSaver") as MockSaver:
            mock_saver = MagicMock()
            MockSaver.from_conn_string.return_value = mock_saver
            mock_graph = MagicMock()
            mock_graph.compile.return_value = "compiled"

            result = with_checkpointer(mock_graph)
            assert result == "compiled"

    @patch("app.workflow.checkpointer.os.environ.get")
    def test_with_checkpointer_no_redis(self, mock_get):
        from app.workflow.checkpointer import with_checkpointer

        mock_get.return_value = None
        mock_graph = MagicMock()
        mock_graph.compile.return_value = "compiled_noop"

        result = with_checkpointer(mock_graph)
        assert result == "compiled_noop"


class TestWorkflowGraph:
    def test_graph_module_imports(self):
        from app.workflow.graph import create_workflow, compiled_graph
        assert callable(create_workflow)
        assert compiled_graph is not None
