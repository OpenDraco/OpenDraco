"""claude_coder tool re-implementations.

Upstream's `extension/src/agent/v1/tools/schema/index.ts` re-exports
15 named tools. Each gets its own OpenDraco-authored Python module here,
named with the exact upstream identifier so prompts/catalogs continue
to resolve. Most modules are thin delegators to canonical OpenHands /
augment / lingma helpers; a few are intentional stubs for runtimes
OpenDraco doesn't currently ship (web search, browser screenshots, dev
server, interactive followup, sub-agent spawn).
"""
from opendraco.tools.repo.claude_coder.executeCommandTool import executeCommandTool
from opendraco.tools.repo.claude_coder.listFilesTool import listFilesTool
from opendraco.tools.repo.claude_coder.ExploreRepoFolderTool import ExploreRepoFolderTool
from opendraco.tools.repo.claude_coder.searchFilesTool import searchFilesTool
from opendraco.tools.repo.claude_coder.readFileTool import readFileTool
from opendraco.tools.repo.claude_coder.askFollowupQuestionTool import askFollowupQuestionTool
from opendraco.tools.repo.claude_coder.attemptCompletionTool import attemptCompletionTool
from opendraco.tools.repo.claude_coder.webSearchTool import webSearchTool
from opendraco.tools.repo.claude_coder.urlScreenshotTool import urlScreenshotTool
from opendraco.tools.repo.claude_coder.devServerTool import devServerTool
from opendraco.tools.repo.claude_coder.searchSymbolTool import searchSymbolTool
from opendraco.tools.repo.claude_coder.addInterestedFileTool import addInterestedFileTool
from opendraco.tools.repo.claude_coder.fileEditorTool import fileEditorTool
from opendraco.tools.repo.claude_coder.spawnAgentTool import spawnAgentTool
from opendraco.tools.repo.claude_coder.exitAgentTool import exitAgentTool

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
