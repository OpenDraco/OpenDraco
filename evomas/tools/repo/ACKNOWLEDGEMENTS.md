# Acknowledgements — tool implementations

EvoMas ships re-implementations of callable tools sourced from 12 open-source
SWE-bench / general-coding agent projects. Each `<repo>/` subdirectory under
this folder carries the Python implementations of the tools declared by one
upstream project; the upstream `source_url` for every tool is preserved in
the module docstring so the original design stays traceable.

EvoMas's tool implementations are written from scratch against the MCP
binding contract — the upstream code is **not** vendored. The
acknowledgement below therefore covers tool *design*, *naming*, and
*intended behaviour*, not the implementation bytes that ship here.

This file is the tool-side counterpart to
[`evomas/config/agent_types/ACKNOWLEDGEMENTS.md`](../../config/agent_types/ACKNOWLEDGEMENTS.md),
which credits the upstream agent *prompts* selected via the Topology
page's variant picker. The two together cover the full provenance of
EvoMas's catalogue.

## Per-repository inventory

| Repo | Upstream | Subdir | Notes |
|---|---|---|---|
| `augment-swebench-agent` | https://github.com/augmentcode/augment-swebench-agent | [`augment_swebench_agent/`](./augment_swebench_agent/) | `CompleteTool`, `SequentialThinkingTool` |
| `auto_code_rover` | https://github.com/AutoCodeRoverSG/auto-code-rover | [`auto_code_rover/`](./auto_code_rover/) | `agent_write_patch` |
| `claude-coder` | https://github.com/kodu-ai/claude-coder | [`claude_coder/`](./claude_coder/) | 15-tool coding assistant surface (read / search / exec / edit / spawn / web) |
| `composio` | https://github.com/ComposioHQ/composio | [`composio/`](./composio/) | MCP/HostedMCP client wrappers for OpenAI Agents and LangChain |
| `debug-gym` | https://github.com/microsoft/debug-gym | [`debug_gym/`](./debug_gym/) | `EnvironmentTool` |
| `joycode-agent` | https://github.com/jd-opensource/joycode-agent | [`joycode_agent/`](./joycode_agent/) | re-export shim — no JoyCode-specific tools at the moment |
| `Lingma_SWE_GPT` | https://github.com/LingmaTongyi/Lingma-SWE-GPT | [`lingma_swe_gpt/`](./lingma_swe_gpt/) | AST-based code search + patch helpers |
| `OpenHands` | https://github.com/OpenHands/OpenHands | [`openhands/`](./openhands/) | Shell / Python / glob / grep / editor / browser toolkit |
| `patchwork` | https://github.com/patched-codes/patchwork | [`patchwork/`](./patchwork/) | Code-edit, csvkit, git, grep, workspace-manifest helpers |
| `suna` | https://github.com/kortix-ai/suna | [`suna/`](./suna/) | MCP-tool filtering helper |
| `SWE_agent` | https://github.com/SWE-agent/SWE-agent | [`swe_agent/`](./swe_agent/) | SWE-agent's core action surface (read / write / search / submit) |
| `trae_agent` | https://github.com/bytedance/trae-agent | [`trae_agent/`](./trae_agent/) | 24-tool action set covering FS, exec, network, planning |

EvoMas-authored helpers that don't have a single-repo origin
(`patch_tools.py`, `repo_tools.py`, `search_tools.py`, `lint_tools.py`)
live one level up at `evomas/tools/` and are not listed here.

## License-sensitive subset

The same four upstream repos flagged in the agent-prompt acknowledgements
also restrict re-distribution of their *tool design notes / docstrings*.
Since the implementations here are EvoMas-authored, the binary surface
ships freely — but anyone copying upstream docstrings into the tool
modules should respect the upstream license terms:

| Repo | License | Posture |
|---|---|---|
| `Lingma_SWE_GPT` | No LICENSE (all-rights-reserved by default) | No redistribution grant for upstream text |
| `auto_code_rover` | SONAR Source-Available v1.0 | Forbids competing / commercial use of the literal text |
| `claude-coder` | AGPL-3.0-or-later | Copyleft + network-use trigger |
| `patchwork` | AGPL-3.0-only | Copyleft + network-use trigger |

Every other repo in the table above ships under MIT, Apache-2.0, or BSD —
verbatim-doc reuse is permitted with attribution.

## Citation

If you use EvoMas in research, please also credit the upstream projects
whose tools you invoked — see the matching agent-prompt acknowledgements
at [`evomas/config/agent_types/ACKNOWLEDGEMENTS.md`](../../config/agent_types/ACKNOWLEDGEMENTS.md)
for the catalogue's prompt-side provenance.
