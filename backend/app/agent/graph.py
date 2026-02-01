from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.nodes import plan_node, browse_node, score_links_node, guardrail_node, extract_node, summarize_node


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("browse", browse_node)
    graph.add_node("score_links", score_links_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("extract", extract_node)
    graph.add_node("summarize", summarize_node)
    
    graph.set_entry_point("plan")
    graph.add_edge("plan", "browse")
    graph.add_edge("browse", "score_links")
    graph.add_edge("score_links", "guardrail")
    graph.add_edge("guardrail", "extract")
    graph.add_edge("extract", "summarize")
    graph.add_edge("summarize", END)
    
    return graph.compile()
