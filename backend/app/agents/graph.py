from langgraph.graph import StateGraph, END

from app.models import YTSageState
from app.agents.ingest import ingest_transcript
from app.agents.planner import plan_concepts
from app.agents.script_writer import write_scripts
from app.agents.video_generator import generate_videos


def should_continue(state: YTSageState) -> str:
    """Check if pipeline should continue or stop due to error."""
    if state.get("status") == "error":
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    """Build the LangGraph pipeline: ingest → planner → script_writer → video_generator."""
    graph = StateGraph(YTSageState)

    graph.add_node("ingest", ingest_transcript)
    graph.add_node("planner", plan_concepts)
    graph.add_node("script_writer", write_scripts)
    graph.add_node("video_generator", generate_videos)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "planner")

    graph.add_conditional_edges(
        "planner",
        should_continue,
        {"continue": "script_writer", "end": END},
    )

    graph.add_conditional_edges(
        "script_writer",
        should_continue,
        {"continue": "video_generator", "end": END},
    )

    graph.add_edge("video_generator", END)

    return graph.compile()
