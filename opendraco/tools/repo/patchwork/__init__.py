"""patchwork tool re-implementations.

Mirror of `opendraco.tools.openhands` for the patchwork repo. Each tool is a
LangChain `@tool`-decorated function exposed via `PATCHWORK_TOOLS` and registered
with the MCP server in `opendraco.mcp.server.default_registry`.

Intentionally NOT exported (require external services that aren't wired in
this OpenDraco install — comparable to the 15 fully-empty repos under
`opendraco/tools/`):
  * `api_tool`     — would need a configurable HTTP endpoint + payload.
  * `db_query_tool` — would need `DATABASE_URL` and a SQLAlchemy session.
  * `github_tool`  — would need `GITHUB_TOKEN` (and ideally the `gh` CLI).

Wire those upstream tools by re-adding their `.py` modules and re-listing
them in `PATCHWORK_TOOLS` once the corresponding credentials/config land.
"""
from opendraco.tools.repo.patchwork.code_edit_tools import code_edit_tools
from opendraco.tools.repo.patchwork.csvkit_tool import csvkit_tool
from opendraco.tools.repo.patchwork.git_tool import git_tool
from opendraco.tools.repo.patchwork.grep_tool import grep_tool
from opendraco.tools.repo.patchwork.workspace_manifest import workspace_manifest

PATCHWORK_TOOLS = (code_edit_tools, csvkit_tool, git_tool, grep_tool, workspace_manifest,)

__all__ = ["PATCHWORK_TOOLS", "code_edit_tools", "csvkit_tool", "git_tool", "grep_tool", "workspace_manifest"]
