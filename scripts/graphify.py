#!/usr/bin/env python3
"""
graphify.py — Parse the codebase into a knowledge graph, output LLM-friendly XML.

Usage:
    python scripts/graphify.py [--root .] [--out codebase_graph.md] [--json graph.json]
"""
import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class Node:
    id: str
    kind: str        # "file" | "class" | "function"
    name: str
    file: str
    line: Optional[int] = None
    parent: Optional[str] = None


@dataclass
class Edge:
    src: str
    dst: str
    kind: str        # "imports" | "inherits" | "contains"


@dataclass
class Graph:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)


# ── Python parsing ────────────────────────────────────────────────────────────

def _parse_python(path: Path, root: Path, graph: Graph) -> None:
    rel = str(path.relative_to(root))
    file_id = rel

    graph.nodes.append(Node(id=file_id, kind="file", name=path.name, file=rel))

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                graph.edges.append(Edge(src=file_id, dst=alias.name, kind="imports"))
        elif isinstance(node, ast.ImportFrom):
            graph.edges.append(Edge(src=file_id, dst=node.module or "", kind="imports"))

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            class_id = f"{rel}::{node.name}"
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    pass
            graph.nodes.append(Node(id=class_id, kind="class", name=node.name, file=rel, line=node.lineno, parent=file_id))
            graph.edges.append(Edge(src=file_id, dst=class_id, kind="contains"))
            for base in bases:
                graph.edges.append(Edge(src=class_id, dst=base, kind="inherits"))
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn_id = f"{rel}::{node.name}::{child.name}"
                    graph.nodes.append(Node(id=fn_id, kind="function", name=child.name, file=rel, line=child.lineno, parent=class_id))
                    graph.edges.append(Edge(src=class_id, dst=fn_id, kind="contains"))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_id = f"{rel}::{node.name}"
            graph.nodes.append(Node(id=fn_id, kind="function", name=node.name, file=rel, line=node.lineno, parent=file_id))
            graph.edges.append(Edge(src=file_id, dst=fn_id, kind="contains"))


# ── TypeScript parsing (regex) ────────────────────────────────────────────────

_TS_IMPORT = re.compile(r"^import\s+.+?\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
_TS_CLASS = re.compile(r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?", re.MULTILINE)
_TS_EXPORT_FN = re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE)
_TS_EXPORT_CONST = re.compile(r"^export\s+const\s+(\w+)\s*[=:]", re.MULTILINE)


def _parse_typescript(path: Path, root: Path, graph: Graph) -> None:
    rel = str(path.relative_to(root))
    file_id = rel

    graph.nodes.append(Node(id=file_id, kind="file", name=path.name, file=rel))

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return

    for m in _TS_IMPORT.finditer(text):
        graph.edges.append(Edge(src=file_id, dst=m.group(1), kind="imports"))

    for m in _TS_CLASS.finditer(text):
        class_id = f"{rel}::{m.group(1)}"
        graph.nodes.append(Node(id=class_id, kind="class", name=m.group(1), file=rel, parent=file_id))
        graph.edges.append(Edge(src=file_id, dst=class_id, kind="contains"))
        if m.group(2):
            graph.edges.append(Edge(src=class_id, dst=m.group(2), kind="inherits"))

    seen_fns: set[str] = set()
    for m in _TS_EXPORT_FN.finditer(text):
        name = m.group(1)
        if name not in seen_fns:
            seen_fns.add(name)
            fn_id = f"{rel}::{name}"
            graph.nodes.append(Node(id=fn_id, kind="function", name=name, file=rel, parent=file_id))
            graph.edges.append(Edge(src=file_id, dst=fn_id, kind="contains"))

    for m in _TS_EXPORT_CONST.finditer(text):
        name = m.group(1)
        if name not in seen_fns:
            seen_fns.add(name)
            fn_id = f"{rel}::{name}"
            graph.nodes.append(Node(id=fn_id, kind="function", name=name, file=rel, parent=file_id))
            graph.edges.append(Edge(src=file_id, dst=fn_id, kind="contains"))


# ── Serialization ─────────────────────────────────────────────────────────────

def _to_xml(graph: Graph) -> str:
    file_nodes = {n.id: n for n in graph.nodes if n.kind == "file"}
    class_nodes = {n.id: n for n in graph.nodes if n.kind == "class"}
    fn_nodes = {n.id: n for n in graph.nodes if n.kind == "function"}

    imports_by: dict[str, list[str]] = {}
    contains_by: dict[str, list[str]] = {}
    inherits_by: dict[str, list[str]] = {}
    for e in graph.edges:
        if e.kind == "imports":
            imports_by.setdefault(e.src, []).append(e.dst)
        elif e.kind == "contains":
            contains_by.setdefault(e.src, []).append(e.dst)
        elif e.kind == "inherits":
            inherits_by.setdefault(e.src, []).append(e.dst)

    lines = ["<codebase>"]
    for file_id, fnode in sorted(file_nodes.items()):
        lang = "python" if fnode.name.endswith(".py") else "typescript"
        lines.append(f'  <file path="{fnode.file}" lang="{lang}">')

        imports = sorted(set(imports_by.get(file_id, [])))
        if imports:
            lines.append(f'    <imports>{", ".join(imports)}</imports>')

        children = contains_by.get(file_id, [])
        for class_id in [c for c in children if c in class_nodes]:
            cnode = class_nodes[class_id]
            bases = inherits_by.get(class_id, [])
            ext = f' extends="{", ".join(bases)}"' if bases else ""
            line_attr = f' line="{cnode.line}"' if cnode.line else ""
            methods = [fn_nodes[m].name for m in contains_by.get(class_id, []) if m in fn_nodes]
            if methods:
                lines.append(f'    <class name="{cnode.name}"{ext}{line_attr}>')
                lines.append(f'      <methods>{", ".join(methods)}</methods>')
                lines.append(f'    </class>')
            else:
                lines.append(f'    <class name="{cnode.name}"{ext}{line_attr}/>')

        fns = [fn_nodes[f].name for f in children if f in fn_nodes]
        if fns:
            lines.append(f'    <functions>{", ".join(fns)}</functions>')

        lines.append("  </file>")
    lines.append("</codebase>")
    return "\n".join(lines)


def _to_json(graph: Graph) -> str:
    return json.dumps({
        "nodes": [vars(n) for n in graph.nodes],
        "edges": [vars(e) for e in graph.edges],
    }, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "dist", "build",
    ".claude", "chroma_market_opinion", "early_work", "screener_scripts",
}


def build_graph(root: Path) -> Graph:
    graph = Graph()
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix == ".py":
            _parse_python(path, root, graph)
        elif path.suffix in {".ts", ".tsx"}:
            _parse_typescript(path, root, graph)
    return graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Graphify: codebase knowledge graph for LLMs")
    parser.add_argument("--root", default=".", help="Repo root (default: current directory)")
    parser.add_argument("--out", default="codebase_graph.md", help="LLM-friendly XML output file")
    parser.add_argument("--json", default=None, metavar="PATH", help="Optional JSON graph output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    graph = build_graph(root)

    xml = _to_xml(graph)
    out = Path(args.out)
    out.write_text(f"```xml\n{xml}\n```\n", encoding="utf-8")
    print(f"[graphify] {out}: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    if args.json:
        jpath = Path(args.json)
        jpath.write_text(_to_json(graph), encoding="utf-8")
        print(f"[graphify] {jpath}: JSON graph written")


if __name__ == "__main__":
    main()
