"""claude_coder tool re-implementations.

Upstream's `extension/src/agent/v1/tools/schema/index.ts` re-exports
15 named tools. Each gets its own EvoMas-authored Python module here,
named with the exact upstream identifier so prompts/catalogs continue
to resolve. Most modules are thin delegators to canonical OpenHands /
augment / lingma helpers; a few are intentional stubs for runtimes
EvoMas doesn't currently ship (web search, browser screenshots, dev
server, interactive followup, sub-agent spawn).
"""
from evomas.tools.repo.claude_coder.executeCommandTool import executeCommandTool
from evomas.tools.repo.claude_coder.listFilesTool import listFilesTool
from evomas.tools.repo.claude_coder.ExploreRepoFolderTool import ExploreRepoFolderTool
from evomas.tools.repo.claude_coder.searchFilesTool import searchFilesTool
from evomas.tools.repo.claude_coder.readFileTool import readFileTool
from evomas.tools.repo.claude_coder.askFollowupQuestionTool import askFollowupQuestionTool
from evomas.tools.repo.claude_coder.attemptCompletionTool import attemptCompletionTool
from evomas.tools.repo.claude_coder.webSearchTool import webSearchTool
from evomas.tools.repo.claude_coder.urlScreenshotTool import urlScreenshotTool
from evomas.tools.repo.claude_coder.devServerTool import devServerTool
from evomas.tools.repo.claude_coder.searchSymbolTool import searchSymbolTool
from evomas.tools.repo.claude_coder.addInterestedFileTool import addInterestedFileTool
from evomas.tools.repo.claude_coder.fileEditorTool import fileEditorTool
from evomas.tools.repo.claude_coder.spawnAgentTool import spawnAgentTool
from evomas.tools.repo.claude_coder.exitAgentTool import exitAgentTool

CLAUDE_CODER_TOOLS = (
    executeCommandTool,
    listFilesTool,
    ExploreRepoFolderTool,
    searchFilesTool,
    readFileTool,
    askFollowupQuestionTool,
    attemptCompletionTool,
    webSearchTool,
    urlScreenshotTool,
    devServerTool,
    searchSymbolTool,
    addInterestedFileTool,
    fileEditorTool,
    spawnAgentTool,
    exitAgentTool,
)

__all__ = [
    "CLAUDE_CODER_TOOLS",
    "executeCommandTool",
    "listFilesTool",
    "ExploreRepoFolderTool",
    "searchFilesTool",
    "readFileTool",
    "askFollowupQuestionTool",
    "attemptCompletionTool",
    "webSearchTool",
    "urlScreenshotTool",
    "devServerTool",
    "searchSymbolTool",
    "addInterestedFileTool",
    "fileEditorTool",
    "spawnAgentTool",
    "exitAgentTool",
]
