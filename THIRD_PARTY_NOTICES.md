# Third-Party Notices

OpenDrago's original code is licensed under the MIT License. The agent catalog
also contains prompt text, role descriptions, tool names, and related metadata
derived from the third-party projects listed below. Those materials remain
subject to their respective upstream licenses and copyright notices.

Each catalog entry contains one or more commit-pinned `source_url` fields that
identify the upstream files from which the material was derived. OpenDrago may
adapt formatting, organize the material into its JSON schema, and add role
metadata. Callable tool implementations in `opendrago/tools/` are implemented
by the OpenDrago project; where their names or behavior are based on an
upstream project, that provenance is recorded in the catalog and associated
acknowledgements.

OpenDrago does not claim authorship of the third-party materials identified
below. Project names and trademarks belong to their respective owners.

## Included third-party projects

| Project | Upstream repository | Referenced revision(s) | License |
|---|---|---|---|
| Aider | https://github.com/Aider-AI/aider | `7afaa26f8b8b7b56146f0674d2a67e795b616b7c` | Apache-2.0 |
| Augment SWE-bench Agent | https://github.com/augmentcode/augment-swebench-agent | `17d813385f50ec59d58fdfe1576f758ed3daaa4e` | MIT |
| Composio | https://github.com/ComposioHQ/composio | `e726e3c7eef0c8cfe567f1b505573c5049c218e5`, `7831d2c58309f57e31da280c989539baeb48c449` | MIT |
| DARS-Agent | https://github.com/darsagent/DARS-Agent | `eab35168a90b7dc5b5a05a29d7d41993cdb74bdf` | Apache-2.0 |
| debug-gym | https://github.com/microsoft/debug-gym | `f260483f06f4083db8c21f60e64e3c109943167c` | MIT |
| ExpeRepair | https://github.com/ExpeRepair/ExpeRepair | `5594f2c02c23d2bf204e5db76949425e6d170922` | MIT |
| HyperAgent | https://github.com/FSoft-AI4Code/HyperAgent | `c3092f2601ab3bf7f890fac2cd5b1290d3f59256` | Apache-2.0 |
| JoyCode Agent | https://github.com/jd-opensource/joycode-agent | `1bace2ab9f1d6345789cd6bb16aff32cca09b518` | MIT |
| KGCompass | https://github.com/GLEAM-Lab/KGCompass | `e79c97b73c8ab12e52b3e6c20be949f48241e084` | MIT |
| Lingxi | https://github.com/lingxi-agent/Lingxi | `fe0b1d36323234c3c90eaa05a82ffc53c77064f9` | MIT |
| mini-SWE-agent | https://github.com/SWE-agent/mini-swe-agent | `6f1b1966166301d68f54bd5b427ec9a596ea853c` | MIT |
| OpenHands | https://github.com/OpenHands/OpenHands | `5f958ab60d564cefce51e10b3ca94bc2994b6673`, `b37adbc1e6f14b1ce70c6ad424ee9cc9786d9f99` | MIT (referenced non-enterprise files) |
| OrcaLoca | https://github.com/fishmingyu/OrcaLoca | `37db289be2dc3b7432183fe08b3f06becce87c27` | MIT |
| R2E-Gym | https://github.com/agentica-project/R2E-Gym | `353348a0ff690f2592025eff41b3fef4201a4d8b` | Apache-2.0 |
| SWE-agent | https://github.com/SWE-agent/SWE-agent | `39e2931a81c8698265e2db40ec4f3911b630d942` | MIT |
| Trae Agent | https://github.com/bytedance/trae-agent | `e839e559ac61bdd0e057c375dd1dee391fee797d` | MIT |

The exact upstream file and line range associated with each prompt or tool
definition is recorded in the corresponding catalog JSON file.

## MIT-licensed materials

The following upstream copyright notices apply:

- Copyright (c) 2025 Augment Code
- Copyright (c) 2024 Anthropic, PBC (for portions of Augment SWE-bench Agent
  identified by its upstream third-party notice)
- Copyright (c) 2025 Sampark Inc.
- Copyright (c) Microsoft Corporation.
- Copyright (c) 2025 Fangwen Mu, Junjie Wang, Lin Shi, Song Wang, Shoubin Li,
  Qing Wang
- Copyright <2025> <JD JoyCode算法组>
- Copyright (c) 2025 GLEAM Lab
- Copyright (c) 2025 nimasteryang
- Copyright (c) 2025 Kilian A. Lieret and Carlos E. Jimenez
- Copyright © 2025 OpenHands contributors
- Copyright (c) 2025 Leo Yu
- Copyright (c) 2024 John Yang, Carlos E. Jimenez, Alexander Wettig, Shunyu
  Yao, Karthik Narasimhan, Ofir Press
- Copyright 2025 ByteDance Ltd. and/or its affiliates

### MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The applicable copyright notice(s) above and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Apache-2.0-licensed materials

Materials derived from Aider, DARS-Agent, HyperAgent, and R2E-Gym are licensed
under the Apache License, Version 2.0. OpenDrago has adapted these materials to
its catalog representation; the corresponding JSON files therefore contain
modified forms of the upstream material.

The complete Apache License, Version 2.0 is available at:
https://www.apache.org/licenses/LICENSE-2.0

Copyright and attribution notices contained in the referenced upstream files
remain the property of their respective owners and contributors.