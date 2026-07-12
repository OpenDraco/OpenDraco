# Acknowledgements

EvoMas ships a catalogue of agent "variants" sourced from 22 open-source
SWE-bench / general-coding agent projects. Each `<repo>.json` file in this
directory carries the prompts and tool whitelists of one upstream project,
with a `source_url` deep-link (commit-pinned) next to every prompt and tool
so the original authorship stays traceable.

EvoMas itself is the multi-agent orchestration framework; it does not claim
authorship of any prompt or tool design listed below. When a variant is
selected from the Topology page, the prompt text is loaded as-is from the
upstream project at the commit the catalogue was generated against.

## Per-repository inventory

| Repo | Upstream | Agents | Tools |
|---|---|---:|---:|
| `aider` | https://github.com/Aider-AI/aider | 14 | 0 |
| `augment-swebench-agent` | https://github.com/augmentcode/augment-swebench-agent | 1 | 3 |
| `auto_code_rover` | https://github.com/AutoCodeRoverSG/auto-code-rover | 6 | 1 |
| `claude-coder` | https://github.com/kodu-ai/claude-coder | 1 | 15 |
| `composio` | https://github.com/ComposioHQ/composio | 14 | 4 |
| `DARS-Agent` | https://github.com/darsagent/DARS-Agent | 2 | 0 |
| `debug-gym` | https://github.com/microsoft/debug-gym | 4 | 1 |
| `ExpeRepair` | https://github.com/ExpeRepair/ExpeRepair | 4 | 0 |
| `HyperAgent` | https://github.com/FSoft-AI4Code/HyperAgent | 7 | 0 |
| `joycode-agent` | https://github.com/jd-opensource/joycode-agent | 1 | 3 |
| `KGCompass` | https://github.com/GLEAM-Lab/KGCompass | 3 | 0 |
| `Lingma_SWE_GPT` | https://github.com/LingmaTongyi/Lingma-SWE-GPT | 6 | 24 |
| `Lingxi` | https://github.com/lingxi-agent/Lingxi | 4 | 0 |
| `mini-SWE-agent` | https://github.com/SWE-agent/mini-swe-agent | 2 | 0 |
| `OpenHands` | https://github.com/OpenHands/OpenHands | 8 | 13 |
| `OrcaLoca` | https://github.com/fishmingyu/OrcaLoca | 6 | 0 |
| `patchwork` | https://github.com/patched-codes/patchwork | 15 | 8 |
| `programmer` | https://github.com/wandb/programmer | 3 | 0 |
| `R2E-Gym` | https://github.com/agentica-project/R2E-Gym | 1 | 0 |
| `suna` | https://github.com/kortix-ai/suna | 9 | 3 |
| `SWE_agent` | https://github.com/SWE-agent/SWE-agent | 9 | 9 |
| `trae_agent` | https://github.com/bytedance/trae-agent | 4 | 24 |

## License-sensitive subset

Four upstream repos carry licenses that do not permit verbatim
redistribution of their prompt strings; their prompts are tracked in
`TODO.md` for paraphrasing and are imported here only for research
reproduction. EvoMas's own redistribution will replace the verbatim
text with role/instruction-equivalent paraphrases before release.

| Repo | License | Posture |
|---|---|---|
| `Lingma_SWE_GPT` | No LICENSE (all-rights-reserved by default) | No redistribution grant |
| `auto_code_rover` | SONAR Source-Available v1.0 | Forbids competing / commercial use of the literal text |
| `claude-coder` | AGPL-3.0-or-later | Copyleft + network-use trigger |
| `patchwork` | AGPL-3.0-only | Copyleft + network-use trigger |

Every other repo in the table above ships under MIT, Apache-2.0, or BSD —
verbatim import is permitted and no paraphrase pass is required.

## Tool implementations

The "Tools" column counts tool *names* declared by the upstream project.
EvoMas re-implements every callable tool from scratch in `evomas/tools/`
rather than importing the upstream code, so the binary tool surface is
EvoMas-authored. The acknowledgement here covers tool *design* and
*naming*, not implementation.

The tool-side counterpart of this file lives at
[`evomas/tools/repo/ACKNOWLEDGEMENTS.md`](../../tools/repo/ACKNOWLEDGEMENTS.md);
it enumerates the per-repo subdirs under `evomas/tools/repo/` and
mirrors the license-sensitive subset table for callers who need it
for the tool docstrings rather than the agent prompts.

## Citation

If you use EvoMas in research, please also credit the upstream projects
whose agents you instantiated — the `source_url` on every catalogue entry
points at the exact commit and file authoritative for that variant.
