from langgraph.graph import StateGraph

from .state import WorkflowState
from . import nodes


def build_graph() -> StateGraph:
    graph = StateGraph(WorkflowState)

    graph.add_node("load_context", nodes.load_context)
    graph.add_node("retrieve_preference", nodes.retrieve_preference)
    graph.add_node("generate_variants", nodes.generate_variants)
    graph.add_node("select_best", nodes.select_best)
    graph.add_node("synthesize_audio", nodes.synthesize_audio)
    graph.add_node("collect_feedback", nodes.collect_feedback)
    graph.add_node("update_preference", nodes.update_preference)
    graph.add_node("complete", nodes.complete)

    graph.set_entry_point("load_context")

    graph.add_edge("load_context", "retrieve_preference")
    graph.add_conditional_edges(
        "retrieve_preference",
        lambda state: "generate_variants",
    )
    graph.add_edge("generate_variants", "select_best")
    graph.add_edge("select_best", "synthesize_audio")
    graph.add_edge("synthesize_audio", "collect_feedback")
    graph.add_edge("collect_feedback", "update_preference")
    graph.add_edge("update_preference", "complete")

    graph.set_finish_point("complete")

    return graph.compile()
