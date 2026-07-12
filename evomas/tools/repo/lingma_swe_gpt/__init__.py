"""lingma_swe_gpt tools — EvoMas re-implementations of Lingma-SWE-GPT's
`ProjectApiManager` search + patch-handoff surface.

Each tool here is a fresh EvoMas-authored implementation that matches
the upstream method's behavioral contract (function name + parameter
shape + a `{"result", "summary", "ok"}` JSON return that maps onto
upstream's `Tuple[str, str, bool]`). No upstream code is reused —
implementations are built on EvoMas's own search helpers
(`evomas.tools.search_tools.search_code_impl`,
`evomas.tools.repo_tools.list_files_impl`) and the Python `ast` module.
"""
from evomas.tools.repo.lingma_swe_gpt.search_class import search_class
from evomas.tools.repo.lingma_swe_gpt.search_class_in_file import search_class_in_file
from evomas.tools.repo.lingma_swe_gpt.search_method_in_file import search_method_in_file
from evomas.tools.repo.lingma_swe_gpt.search_method_in_class import search_method_in_class
from evomas.tools.repo.lingma_swe_gpt.search_method import search_method
from evomas.tools.repo.lingma_swe_gpt.search_code_in_file import search_code_in_file
from evomas.tools.repo.lingma_swe_gpt.write_patch import write_patch
# `search_code` is the canonical EvoMas BM25 keyword search. Lingma's
# upstream `ProjectApiManager.search_code` does the same thing, so we
# re-export the canonical here instead of duplicating it — that keeps
# MCP from registering two `search_code` tools (the duplicate caused a
# last-write-wins clobber that broke the canonical's tests). The Lingma
# catalog's `tools[].name = "search_code"` resolves to the canonical at
# runtime.
from evomas.tools.search_tools import search_code

LINGMA_SWE_GPT_TOOLS = (
    search_class,
    search_class_in_file,
    search_method_in_file,
    search_method_in_class,
    search_method,
    # search_code is NOT included here — already registered with MCP via
    # `evomas.tools.search_tools` to avoid the duplicate-registration
    # clobber. The lingma catalog's tool whitelist references it by name
    # and MCP resolves to the canonical.
    search_code_in_file,
    write_patch,
)

__all__ = [
    "LINGMA_SWE_GPT_TOOLS",
    "search_class",
    "search_class_in_file",
    "search_method_in_file",
    "search_method_in_class",
    "search_method",
    "search_code",
    "search_code_in_file",
    "write_patch",
]
