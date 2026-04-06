"""
AST-aware chunker using tree-sitter for supported languages.
Falls back to sliding window for unsupported file types.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import tiktoken

try:
    import tree_sitter_python as tspython
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_typescript as tstypescript
    import tree_sitter_go as tsgo
    import tree_sitter_java as tsjava
    import tree_sitter_rust as tsrust
    import tree_sitter_c as tsc
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser
    TS_AVAILABLE = True
except ImportError:
    TS_AVAILABLE = False

from core.config import settings

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


@dataclass
class Chunk:
    file_path: str
    content: str
    chunk_type: str  # function | class | module | doc
    name: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)


LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}

SLIDING_WINDOW_EXTS = {".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".rst", ".ini", ".cfg"}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".next", "venv", ".venv", ".tox", ".mypy_cache", "coverage",
    "vendor", ".gradle", "target", "out",
}

SKIP_PATTERNS = re.compile(
    r"(\.lock$|\.min\.js$|\.min\.css$|\.map$|\.svg$|\.png$|\.jpg$|"
    r"\.jpeg$|\.gif$|\.webp$|\.woff$|\.woff2$|\.ttf$|\.eot$|"
    r"\.ico$|\.pdf$|\.zip$|\.tar$|\.gz$|\.exe$|\.bin$)"
)


def should_skip_file(path: Path) -> bool:
    if SKIP_PATTERNS.search(path.name):
        return True
    try:
        if path.stat().st_size > settings.max_file_size_bytes:
            return True
    except OSError:
        return True
    return False


def should_skip_dir(dirname: str) -> bool:
    return dirname in SKIP_DIRS or dirname.startswith(".")


def _get_parser(language: str) -> Optional["Parser"]:
    if not TS_AVAILABLE:
        return None
    lang_map = {
        "python": tspython.language(),
        "javascript": tsjavascript.language(),
        "typescript": tstypescript.language_typescript(),
        "go": tsgo.language(),
        "java": tsjava.language(),
        "rust": tsrust.language(),
        "c": tsc.language(),
        "cpp": tscpp.language(),
    }
    lang_obj = lang_map.get(language)
    if not lang_obj:
        return None
    parser = Parser(Language(lang_obj))
    return parser


def _extract_ts_chunks(source: str, file_path: str, language: str) -> List[Chunk]:
    parser = _get_parser(language)
    if not parser:
        return []

    tree = parser.parse(source.encode())
    chunks = []
    lines = source.splitlines()

    def node_name(node) -> Optional[str]:
        for child in node.children:
            if child.type in ("identifier", "name", "type_identifier"):
                return child.text.decode() if child.text else None
        return None

    def visit(node, parent_name=None):
        is_func = node.type in (
            "function_definition", "function_declaration", "method_definition",
            "arrow_function", "func_declaration", "function_item",
            "method_declaration", "constructor_declaration",
        )
        is_class = node.type in (
            "class_definition", "class_declaration", "impl_item",
            "struct_item", "interface_declaration",
        )

        if is_func or is_class:
            chunk_type = "function" if is_func else "class"
            name = node_name(node)
            if parent_name and name:
                full_name = f"{parent_name}.{name}"
            else:
                full_name = name

            start = node.start_point[0]
            end = node.end_point[0]
            content = "\n".join(lines[start : end + 1])
            tokens = count_tokens(content)

            if tokens < settings.chunk_min_tokens:
                # too small — include in parent
                pass
            elif tokens <= settings.chunk_max_tokens:
                chunks.append(
                    Chunk(
                        file_path=file_path,
                        content=content,
                        chunk_type=chunk_type,
                        name=full_name,
                        start_line=start + 1,
                        end_line=end + 1,
                        language=language,
                    )
                )
                return  # don't descend — already captured whole node

            # Oversized: descend into children
            for child in node.children:
                visit(child, full_name)
        else:
            for child in node.children:
                visit(child, parent_name)

    visit(tree.root_node)

    # If no chunks found, treat whole file as module chunk
    if not chunks:
        return _sliding_window_chunks(source, file_path, language, "module")

    # Fill gaps: code before first chunk, between chunks, after last chunk
    total_lines = len(lines)
    sorted_chunks = sorted(chunks, key=lambda c: c.start_line)
    gap_chunks = []
    prev_end_line = 0  # 1-indexed end of last processed chunk

    for chunk in sorted_chunks:
        gap_start = prev_end_line + 1
        gap_end = chunk.start_line - 1
        if gap_start <= gap_end:
            gap_content = "\n".join(lines[gap_start - 1 : gap_end]).strip()
            if gap_content:
                gap_chunks.append(Chunk(
                    file_path=file_path,
                    content=gap_content,
                    chunk_type="block",
                    start_line=gap_start,
                    end_line=gap_end,
                    language=language,
                ))
        prev_end_line = chunk.end_line

    # After last chunk
    gap_start = prev_end_line + 1
    if gap_start <= total_lines:
        gap_content = "\n".join(lines[gap_start - 1 :]).strip()
        if gap_content:
            gap_chunks.append(Chunk(
                file_path=file_path,
                content=gap_content,
                chunk_type="block",
                start_line=gap_start,
                end_line=total_lines,
                language=language,
            ))

    return sorted(chunks + gap_chunks, key=lambda c: c.start_line)


def _sliding_window_chunks(
    source: str,
    file_path: str,
    language: Optional[str],
    chunk_type: str = "doc",
) -> List[Chunk]:
    window = 256
    overlap = 50
    tokens = _enc.encode(source)
    lines = source.splitlines()
    chunks = []
    pos = 0
    while pos < len(tokens):
        window_tokens = tokens[pos : pos + window]
        content = _enc.decode(window_tokens)
        # Rough line estimation
        start_char = len(_enc.decode(tokens[:pos])) if pos > 0 else 0
        chunks.append(
            Chunk(
                file_path=file_path,
                content=content,
                chunk_type=chunk_type,
                start_line=1,
                end_line=len(lines),
                language=language,
            )
        )
        pos += window - overlap
    return chunks


def chunk_file(file_path: str, source: str) -> List[Chunk]:
    ext = Path(file_path).suffix.lower()
    language = LANG_MAP.get(ext)

    # Count lines
    line_count = source.count("\n") + 1
    if line_count > settings.max_file_lines:
        return []

    if language and TS_AVAILABLE:
        chunks = _extract_ts_chunks(source, file_path, language)
        if chunks:
            return chunks

    if ext in SLIDING_WINDOW_EXTS or language:
        chunk_type = "doc" if ext in SLIDING_WINDOW_EXTS else "module"
        return _sliding_window_chunks(source, file_path, language, chunk_type)

    return []
