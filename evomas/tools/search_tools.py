import re
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.tools import tool

from evomas.tools.repo_tools import list_files_impl
from evomas.utils.bm25 import BM25, tokenize


class CodeMatch(TypedDict):
    path: str
    score: float
    snippet: str


def _snippet(text: str, query_terms: list[str], context: int = 2, max_lines: int = 8) -> str:
    lines = text.splitlines()
    qset = set(query_terms)
    hits: list[int] = []
    for i, line in enumerate(lines):
        toks = set(tokenize(line))
        if toks & qset:
            hits.append(i)
    if not hits:
        return "\n".join(lines[:max_lines])
    start = max(0, hits[0] - context)
    end = min(len(lines), hits[0] + context + 1)
    block = lines[start:end]
    if len(block) > max_lines:
        block = block[:max_lines]
    return "\n".join(f"{start + i + 1}: {line}" for i, line in enumerate(block))


def search_code_impl(query: str, directory: str, top_k: int = 10) -> list[CodeMatch]:
    base = Path(directory)
    if not base.is_dir():
        raise FileNotFoundError(f"directory not found: {directory}")

    rel_paths: list[str] = list_files_impl(directory, "*.py")
    docs: list[list[str]] = []
    contents: list[str] = []
    abs_paths: list[Path] = []
    for rp in rel_paths:
        ap = base / rp
        try:
            text = ap.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        contents.append(text)
        abs_paths.append(ap)
        docs.append(tokenize(text))

    if not docs:
        return []

    bm25 = BM25()
    bm25.fit(docs)
    q_tokens = tokenize(query)
    if not q_tokens:
        return []

    ranked = bm25.rank(q_tokens, top_k=top_k)
    results: list[CodeMatch] = []
    for idx, score in ranked:
        rel = str(abs_paths[idx].relative_to(base))
        snippet = _snippet(contents[idx], q_tokens)
        results.append({"path": rel, "score": round(score, 3), "snippet": snippet})
    return results


@tool
def search_code(query: str, directory: str, top_k: int = 10) -> list[CodeMatch]:
    """BM25 keyword search across .py files in a directory.

    Args:
        query: free-form natural-language query (function names, error messages, identifiers).
        directory: absolute path to the repo root to search.
        top_k: number of results to return.

    Returns a list of {path, score, snippet} entries ordered by relevance.
    """
    return search_code_impl(query, directory, top_k)


# ─── Bug-class detection ─────────────────────────────────────────────────────
# Deterministic scan that classifies a SWE-bench-style issue as either a
# description / error-message bug (class 1) — fixable by a single-line string
# swap — or a behaviour / API-mismatch bug (class 2 / 3). Pure heuristic over
# the issue text + workspace contents; no LLM. Lives next to `search_code`
# because the core operation is "scan repo files for content matches".

class BugClassResult(TypedDict, total=False):
    bug_class: int                    # 1 = description-string, 2 = behaviour, 3 = API mismatch
    evidence: str                     # one-line rationale
    matched_quoted_string: str        # the OLD literal (class 1 only)
    matched_file: str                 # repo-relative, for human readability
    matched_file_absolute: str        # ABSOLUTE path -- pass this to str_replace_editor
    matched_line: int                 # 1-indexed


# Captures any "..." with at least 5 chars of content; covers both straight
# and "smart" quotes from copy-pasted issue text.
_QUOTED_RE: re.Pattern[str] = re.compile(r'["“]([^"”]{5,}?)["”]')

# Source-file extensions to grep through when looking for a quoted literal.
_SOURCE_EXTS: tuple[str, ...] = (".py", ".js", ".ts", ".tsx", ".rb", ".go")

# Directories to skip when walking — large vendored trees / build artefacts
# blow up grep time without ever matching emitted strings.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".tox", ".venv", "venv", "node_modules", "__pycache__", "dist",
    "build", ".pytest_cache", ".mypy_cache",
})

# Heuristic: when we find an issue-quoted string in source, is its position
# in the file a "string the program emits to the user"?
# These patterns match the LINE containing the literal — keep them broad
# enough to catch the common SWE-bench-style description-message bug shapes.
_EMITTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\bdescription\s*=\s*["“]'),     # description="..."
    re.compile(r'\bmessage\s*=\s*["“]'),         # message="..."
    re.compile(r'\berror_message\s*=\s*["“]'),   # error_message="..."
    re.compile(r'\bmsg\s*=\s*["“]'),             # msg="..."
    re.compile(r'\braise\s+\w+\s*\(\s*["“]'),    # raise X("..."
    re.compile(r'\bself\._error\s*\(\s*["“]'),   # self._error("..."
    re.compile(r'\breturn\s+["“]'),              # return "..."  (helpful for getter-style messages)
)

# Tokens that hint at API-signature bugs when the issue doesn't have a
# quoted-string match.
_API_HINTS: frozenset[str] = frozenset({
    "argument", "arguments", "parameter", "parameters",
    "signature", "kwarg", "kwargs", "return type", "type hint",
})


def _iter_source_files(repo_path: Path) -> list[Path]:
    """Yield candidate source files under `repo_path` -- prioritising the
    canonical `src/` / `lib/` subtrees and skipping vendored / build dirs."""
    out: list[Path] = []
    for sub in (repo_path / "src", repo_path / "lib"):
        if sub.is_dir():
            for p in sub.rglob("*"):
                if p.is_file() and p.suffix in _SOURCE_EXTS \
                        and not any(d in _SKIP_DIRS for d in p.parts):
                    out.append(p)
    # Top-level files (for projects without an src/ layout).
    for p in repo_path.glob("*.py"):
        out.append(p)
    return out


def detect_bug_class_impl(issue_text: str, repo_path: str) -> BugClassResult:
    """Classify a SWE-bench-style issue as description-string (1),
    behaviour (2), or API-mismatch (3). Class-1 matches also pin the
    source location of the offending literal so the follow-up
    `derive_description_fix` can derive the new wording verbatim.

    Pure heuristic; safe to call as a first step in any patcher chain.
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        return {"bug_class": 2, "evidence": f"repo not found: {repo_path}"}

    issue = issue_text or ""
    quoted = [m.group(1).strip() for m in _QUOTED_RE.finditer(issue)]
    # Dedup preserving order; ignore very short or pure-whitespace.
    seen: set[str] = set()
    quoted = [q for q in quoted if q and q not in seen and not seen.add(q)]

    if quoted:
        source_files = _iter_source_files(repo)
        for q in quoted:
            for sf in source_files:
                try:
                    text = sf.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if q not in text:
                    continue
                # Walk lines to pinpoint the exact line + check the
                # emitted-string heuristics.
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if q not in line:
                        continue
                    if any(p.search(line) for p in _EMITTED_PATTERNS):
                        rel = sf.relative_to(repo).as_posix()
                        evidence = (
                            f"matched quoted string {q!r} on an emitted-string "
                            f"line at {rel}:{lineno}"
                        )
                        return {
                            "bug_class": 1,
                            "evidence": evidence,
                            "matched_quoted_string": q,
                            "matched_file": rel,
                            "matched_file_absolute": str(sf.resolve()),
                            "matched_line": lineno,
                        }
                # The literal exists in the file but not on an emitted-string
                # line. Note it as evidence and keep scanning other files.
        # Quoted strings exist but none on an emitted-string line → behaviour bug.
        # Fall through.

    if any(h in issue.lower() for h in _API_HINTS):
        return {"bug_class": 3, "evidence": "issue uses API-signature vocabulary without an emitted-string match"}

    return {"bug_class": 2, "evidence": "no emitted-string match for any quoted issue text"}


@tool
def detect_bug_class(issue_text: str, repo_path: str) -> dict[str, Any]:
    """Heuristically classify the SWE-bench-style issue as one of:
      * `bug_class=1` - description / error-message bug. The issue quotes
        a specific emitted string (e.g. a `description=\"...\"` argument,
        a `raise X(\"...\")`, an `error_message=\"...\"`). The fix is to
        change ONLY that string literal. The response includes
        `matched_quoted_string`, `matched_file` (repo-relative),
        `matched_file_absolute` (use THIS as the `path` argument for
        `str_replace_editor`), and `matched_line`.
      * `bug_class=2` - behaviour bug. Logic / triggering change needed.
      * `bug_class=3` - API signature / typing mismatch.

    Call this BEFORE attempting any edit so subsequent steps can pick the
    right strategy. Pure deterministic heuristic over the issue text and
    workspace contents -- no LLM, no flakiness.

    Args:
        issue_text: the SWE-bench issue / problem statement.
        repo_path:  absolute path to the cloned workspace root.

    Returns: a dict with `bug_class`, `evidence`, and (for class 1)
        `matched_quoted_string`, `matched_file` (relative),
        `matched_file_absolute`, `matched_line`.
    """
    return dict(detect_bug_class_impl(issue_text, repo_path))
