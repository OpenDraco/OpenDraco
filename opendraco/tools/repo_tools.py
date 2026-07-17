import re
from pathlib import Path
from typing import Any, Iterable, TypedDict

from langchain_core.tools import tool

DEFAULT_IGNORES: tuple[str, ...] = (
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".pytest_cache",
    "build",
    "dist",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
)


def _iter_files(directory: Path, extension: str, ignores: Iterable[str]) -> list[str]:
    ignore_set = set(ignores)
    out: list[str] = []
    for p in directory.rglob(extension):
        if any(part in ignore_set for part in p.parts):
            continue
        if p.is_file():
            out.append(str(p.relative_to(directory)))
    out.sort()
    return out


def list_files_impl(directory: str, extension: str = "*.py") -> list[str]:
    base = Path(directory)
    if not base.is_dir():
        raise FileNotFoundError(f"directory not found: {directory}")
    return _iter_files(base, extension, DEFAULT_IGNORES)


def read_file_impl(path: str, with_line_numbers: bool = True, max_chars: int | None = None) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + f"\n... [truncated to {max_chars} chars]"
    if with_line_numbers:
        lines = text.splitlines()
        width = max(3, len(str(len(lines))))
        return "\n".join(f"{i + 1:>{width}}: {line}" for i, line in enumerate(lines))
    return text


@tool
def list_files(directory: str, extension: str = "*.py") -> list[str]:
    """List files matching a glob extension under a directory (recursively).

    Args:
        directory: absolute path to a directory.
        extension: glob pattern (e.g., "*.py" or "*.md"). Default "*.py".

    Returns relative paths sorted alphabetically.
    """
    return list_files_impl(directory, extension)


@tool
def read_file(path: str, with_line_numbers: bool = True, max_chars: int | None = None) -> str:
    """Read a text file's contents, optionally prefixed with line numbers.

    Args:
        path: absolute path to a file.
        with_line_numbers: prefix each line with its line number (default True).
        max_chars: truncate to this many characters; None for no limit.
    """
    return read_file_impl(path, with_line_numbers, max_chars)


# ─── Description-fix derivation ──────────────────────────────────────────────
# Deterministic helper used after `detect_bug_class` flags a class-1 bug. It
# reads the source file at the matched line, walks up to the enclosing class
# (or, failing that, function) docstring, and returns the first sentence as
# the verbatim replacement for the offending string. Pure file read + parse;
# lives next to `read_file` / `list_files`.

class DescriptionFix(TypedDict, total=False):
    file: str                         # repo-relative
    absolute_path: str                # ABSOLUTE path -- pass this to str_replace_editor
    line: int
    old_string: str
    new_string: str                   # derived candidate
    docstring_first_sentence: str     # raw verbatim, no fillers dropped
    error: str                        # set when derivation failed


# First-sentence regex: match up to (and including) the first period, treating
# blank lines / Sphinx field markers as terminators too.
_FIRST_SENTENCE_RE: re.Pattern[str] = re.compile(r"^(.*?\.)\s", re.DOTALL)

# Filler tokens to strip when deriving the new wording from a docstring.
# Conservative: only remove standalone words that don't change meaning.
_FILLER_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    # "table aliases" → "aliases"
    (re.compile(r"\btable aliases\b", re.IGNORECASE), "aliases"),
    # "using aliases" → "aliases" (when 'using' is the filler after a verb)
    (re.compile(r"\busing aliases\b", re.IGNORECASE), "aliases"),
)


def _find_enclosing(lines: list[str], target_line_index: int, kinds: tuple[str, ...]) -> int | None:
    """Walk backwards from `target_line_index` (0-based) to find an enclosing
    line starting with any prefix in `kinds` at a STRICTLY LOWER indent than
    the target.

    Returns the line index of the *outermost* enclosing match — i.e. each
    time we find a candidate at indent `n`, we keep walking back hoping to
    find an even-lower-indent match. This lets us prefer the outer
    `class Rule_X(BaseRule):` over a nested `class TableAliasInfo:` when the
    target line sits inside both.
    """
    target_indent: int | None = None
    chosen_index: int | None = None
    chosen_indent: int | None = None
    for i in range(target_line_index, -1, -1):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        if target_indent is None:
            target_indent = indent
        if any(stripped.startswith(k) for k in kinds) and indent < (target_indent or 0):
            # Keep the outermost (lowest-indent) match seen so far.
            if chosen_indent is None or indent < chosen_indent:
                chosen_index = i
                chosen_indent = indent
                if indent == 0:
                    # Can't get any more outer than column 0.
                    break
    return chosen_index


def _extract_docstring(lines: list[str], def_index: int) -> str | None:
    """Given the line index of a `class ` or `def ` definition, return the
    text of the triple-quoted docstring that follows (if any). Joins
    multi-line docstrings into a single string without the quoting."""
    # Find the first non-blank line after the def's colon. The def can be
    # multi-line (e.g. wrapped argument lists), so locate the line ending
    # in `:` first.
    i = def_index
    while i < len(lines) and not lines[i].rstrip().endswith(":"):
        i += 1
        if i - def_index > 30:
            return None  # something's off; bail
    i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None
    first = lines[i].strip()
    for quote in ('"""', "'''"):
        if first.startswith(quote):
            # Single-line docstring?
            if first.endswith(quote) and len(first) > len(quote) * 2:
                return first[len(quote):-len(quote)].strip()
            # Multi-line: collect until closing quote.
            body: list[str] = [first[len(quote):]]
            j = i + 1
            while j < len(lines):
                line = lines[j]
                if quote in line:
                    end = line.index(quote)
                    body.append(line[:end])
                    return "\n".join(body).strip()
                body.append(line)
                j += 1
    return None


def _apply_fillers(sentence: str) -> str:
    """Apply the small set of common-filler removals from `_FILLER_REPLACEMENTS`
    and ensure a trailing period. Idempotent."""
    out = sentence.strip()
    for pat, repl in _FILLER_REPLACEMENTS:
        out = pat.sub(repl, out)
    out = re.sub(r"\s+", " ", out).strip()
    if not out.endswith("."):
        out = out + "."
    return out


def derive_description_fix_impl(repo_path: str, file: str, old_string: str) -> DescriptionFix:
    """For a class-1 bug, derive the new wording verbatim from the enclosing
    class/function's docstring. Returns the {old, new, file, line} the
    caller should pass to `str_replace_editor`."""
    repo = Path(repo_path)
    src = repo / file
    if not src.is_file():
        return {"error": f"file not found: {file}"}
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"read failed: {exc}"}

    lines = text.splitlines()
    # Locate the line containing the old string.
    line_index = next((i for i, l in enumerate(lines) if old_string in l), None)
    if line_index is None:
        return {"error": f"old_string {old_string!r} not found in {file}"}

    # Prefer the enclosing CLASS's docstring (which typically describes the
    # rule / behaviour the emitted string is about) over the immediate
    # method's docstring (which usually describes the helper, not the
    # message). Fall back to the closest def only when no class wraps it.
    class_index = _find_enclosing(lines, line_index, ("class ",))
    def_index   = _find_enclosing(lines, line_index, ("class ", "def "))
    docstring: str | None = None
    if class_index is not None:
        docstring = _extract_docstring(lines, class_index)
    if not docstring and def_index is not None:
        docstring = _extract_docstring(lines, def_index)
    if not docstring:
        return {"error": f"no docstring on enclosing class/def above line {line_index + 1}"}

    # First sentence: the longest leading slice ending at the first period,
    # collapsed to a single line.
    first_line_block = docstring.split("\n\n", 1)[0].strip()
    first_line_block = re.sub(r"\s+", " ", first_line_block)
    m = _FIRST_SENTENCE_RE.match(first_line_block + " ")
    if m:
        sentence = m.group(1).strip()
    else:
        sentence = first_line_block.strip()
        if not sentence.endswith("."):
            sentence = sentence + "."

    new_string = _apply_fillers(sentence)
    return {
        "file": file,
        "absolute_path": str(src.resolve()),
        "line": line_index + 1,
        "old_string": old_string,
        "new_string": new_string,
        "docstring_first_sentence": sentence,
    }


@tool
def derive_description_fix(repo_path: str, file: str, old_string: str) -> dict[str, Any]:
    """For a class-1 description/error-message bug, deterministically
    derive the new wording from the enclosing class/function's docstring.
    Drops the common single-word fillers (`table ` before `aliases`,
    `using ` between verb and `aliases`) and ensures a trailing period.
    Use the returned `new_string` value VERBATIM as the replacement.

    The harness asserts character equality; do NOT paraphrase the result.

    Args:
        repo_path:  absolute path to the cloned workspace root.
        file:       repo-relative source path (from `detect_bug_class`).
        old_string: the OLD literal (from `detect_bug_class`).

    Returns: `{file, absolute_path, line, old_string, new_string,
        docstring_first_sentence}` on success -- pass `absolute_path` (not
        `file`) as the `path` argument to `str_replace_editor`. On failure
        returns `{error: <reason>}`.
    """
    return dict(derive_description_fix_impl(repo_path, file, old_string))
