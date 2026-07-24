from src.graph.agent import agentic_ai
from src.graph.edges import after_transform


def test_graph_compiles_without_env():
 assert agentic_ai is not None
 node_names = set(agentic_ai.get_graph().nodes)
 # Graph has: ingest_node, plan_node, execute_node, response_node, handle_error, finalize,
 # plus backwards-compat alias transform_text
 assert "handle_error" in node_names
 assert "finalize" in node_names


def test_error_edge_routes_to_handler():
 assert after_transform({"error": "boom"}) == "handle_error"
 assert after_transform({"error": None}) == "finalize"


def test_transform_node_surfaces_missing_key_as_error(no_keys):
 """With no key, the node returns an actionable error — it never raises."""
 from src.graph.nodes import transform_text

 out = transform_text({"input_text": "hi", "instruction": "upper"})
 assert out.get("error") is not None
 assert "AGENT_" in (out.get("error") or "")
