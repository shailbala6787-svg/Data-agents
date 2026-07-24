from pathlib import Path

p = Path("src/graph/nodes.py")
text = p.read_text(encoding="utf-8")

# Match the exact text in nodes.py (ASCII-safe)
needle = "def handle_error(state: AgentState) -> AgentState:\n return {\"status\": \"failed\", \"error\": state.get(\"error\", \"Unknown error.\")}"
appendage = "\n\n\ndef finalize(state: AgentState) -> AgentState:\n return {\"status\": state.get(\"status\", \"completed\")}\n"

if needle in text and "def finalize" not in text:
    text = text.replace(needle, needle + appendage, 1)
    p.write_text(text, encoding="utf-8")
    print("OK: finalize added to nodes.py")
else:
    print("SKIP: needle not found or finalize already present")
    if "def finalize" in text:
        print("  (finalize already exists)")
