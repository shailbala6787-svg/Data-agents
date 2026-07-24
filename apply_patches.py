"""apply_patches.py — apply precise patches to the UP Police agent source tree."""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path("F:/4. Other/Shail/AI Training/phase 2nd/Data-agents")

# ── helpers ───────────────────────────────────────────────────────────────────

def write(rel: str, content: str) -> None:
    p = REPO / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def patch(rel: str, old: str, new: str) -> None:
    text = read(rel)
    if old not in text:
        raise ValueError(f"OLD string not found in {rel!r}: {old[:80]!r}")
    text = text.replace(old, new, 1)
    write(rel, text)


# ── 1. Restore git-tracked baseline of connections.py (damaged by earlier write) ─
print("Restoring connections.py from git...")
shutil.copy(REPO / "src/db/connections.py", REPO / "src/db/connections.py.bak.before_patch")
git_result = __import__("subprocess").run(
    ["git", "show", "HEAD:src/db/connections.py"],
    cwd=REPO, capture_output=True, text=True
)
if git_result.returncode == 0:
    write("src/db/connections.py", git_result.stdout)
    print("  Ok from git HEAD")
else:
    print("  git show failed; must patch manually:", git_result.stderr[:200])
    raise SystemExit(1)

# ── 2. settings.py ────────────────────────────────────────────────────────────
print("Patching settings.py...")
patch("src/config/settings.py",
    ''' anthropic_api_key: str = Field(default="")
 gemini_api_key: str = Field(default="")
 openrouter_api_key: str = Field(default="")
 openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")

 log_level: str = Field(default="INFO")
''',
    ''' llm_provider: str = Field(default="ollama")
 llm_model: str = Field(default="")
 ollama_base_url: str = Field(default="http://localhost:11434")
 ollama_model: str = Field(default="llama3.2:3b")
 fernet_key: str = Field(default="")

 anthropic_api_key: str = Field(default="")
 gemini_api_key: str = Field(default="")
 openrouter_api_key: str = Field(default="")
 openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")

 log_level: str = Field(default="INFO")
''')

patch("src/config/settings.py",
    ''' # "auto" resolves to whichever provider key is set.
 llm_provider: str = Field(default="auto")
 llm_model: str = Field(default="")
''',
    ''' # Default provider for privacy-first (on-premises) deployment.
 # Change to "auto" to pick based on which API key is set in .env.
 llm_provider: str = Field(default="ollama")
 llm_model: str = Field(default="")
''')

patch("src/config/settings.py",
    ''' if self.openrouter_api_key:
  return "openrouter"
 return "stub"
''',
    ''' if self.openrouter_api_key:
  return "openrouter"
 # no key required for local ollama — fall straight through to it
 return "ollama"
''')

# ── 3. factory.py ─────────────────────────────────────────────────────────────
print("Patching factory.py...")
patch("src/llm/providers/factory.py",
    "from src.llm.providers.openrouter import OpenRouterProvider",
    "from src.llm.providers.openrouter import OpenRouterProvider\nfrom src.llm.providers.ollama import OllamaProvider")

patch("src/llm/providers/factory.py",
    ''' if provider == "openrouter":
  return OpenRouterProvider(
   api_key=s.openrouter_api_key, model=model, base_url=s.openrouter_base_url
  )
 raise LLMError(
  "No LLM API key configured. Set exactly one of AGENT_ANTHROPIC_API_KEY, "
  "AGENT_GEMINI_API_KEY, or AGENT_OPENROUTER_API_KEY in .env "
  "(see .env.example)."
 )
''',
    ''' if provider == "openrouter":
  return OpenRouterProvider(
   api_key=s.openrouter_api_key, model=model, base_url=s.openrouter_base_url
  )
 if provider == "ollama":
  return OllamaProvider(
   base_url=s.ollama_base_url or "http://localhost:11434",
   model=model or s.ollama_model or "llama3.2:3b",
  )
 raise LLMError(
  "No LLM provider configured. Set AGENT_LLM_PROVIDER=ollama and start "
  "a local Ollama instance (default http://localhost:11434), or set a "
  "cloud provider key in .env."
 )
''')

# ── 4. .env.example ───────────────────────────────────────────────────────────
print("Patching .env.example...")
patch(".env.example",
    "AGENT_OPENROUTER_API_KEY=\n",
    "AGENT_OPENROUTER_API_KEY=\n\n# --- Ollama (local default for privacy-first deployment) ---\nAGENT_LLM_PROVIDER=ollama\nAGENT_OLLAMA_BASE_URL=http://localhost:11434\nAGENT_OLLAMA_MODEL=llama3.2:3b\n\n# --- MsSQL credential encryption ---\n# Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key())\"\nAGENT_FERNET_KEY=\n")

# ── 5. pyproject.toml ─────────────────────────────────────────────────────────
print("Patching pyproject.toml...")
patch("pyproject.toml",
    '"structlog>=24.1",\n]',
    '"structlog>=24.1",\n"pyodbc>=5.1",\n"cryptography>=42.0",\n"pandas>=2.2",\n"pyyaml>=6.0",\n]')

# ── 6. state.py (ensure csv_files key, csv_tables alias) ───────────────────────
print("Patching graph/state.py...")
patch("src/graph/state.py",
    "csv_tables: list[dict]   # [{'table_name': str, 'original_name': str, 'rows': int, 'columns': list[dict]}]\n",
    "")

patch("src/graph/state.py",
    "def_below",
    "csv_files: list[dict]   # [{'table_name': str, 'original_name': str, 'rows': int, 'columns': list[dict]}]\n    csv_tables: list[dict]   # derived from csv_files at ingest time\n")

print("\nAll patches applied. Verify with: git diff --stat")
