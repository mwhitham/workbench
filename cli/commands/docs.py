"""workbench docs — open or serve documentation."""

from __future__ import annotations

import http.server
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import typer
from rich.console import Console

console = Console()

_CSS = """\
body {
  max-width: 800px; margin: 40px auto; padding: 0 20px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  color: #1a1a2e; background: #fafbfc; line-height: 1.6; font-size: 16px;
}
h1, h2, h3, h4 { color: #0f172a; margin-top: 1.8em; }
h1 { border-bottom: 2px solid #e2e8f0; padding-bottom: 0.3em; }
h2 { border-bottom: 1px solid #e2e8f0; padding-bottom: 0.2em; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  background: #f1f5f9; padding: 0.15em 0.4em; border-radius: 4px;
  font-size: 0.9em; font-family: "SF Mono", Menlo, monospace;
}
pre {
  background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 8px;
  overflow-x: auto; line-height: 1.5;
}
pre code { background: none; padding: 0; color: inherit; }
table {
  border-collapse: collapse; width: 100%; margin: 1em 0;
}
th, td {
  border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left;
}
th { background: #f1f5f9; font-weight: 600; }
blockquote {
  border-left: 4px solid #2563eb; margin: 1em 0; padding: 0.5em 1em;
  background: #eff6ff; color: #1e40af;
}
nav { background: #f1f5f9; padding: 12px 16px; border-radius: 8px; margin-bottom: 2em; font-size: 0.9em; }
nav a { margin-right: 8px; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 2em 0; }
"""


def _render_markdown(text: str) -> str:
    """Convert markdown to HTML using a simple regex-based renderer."""
    html = text

    # Extract fenced code blocks and inline code first to protect them from markdown parsing
    code_blocks = []
    def _stash_code_block(m):
        code = m.group(2).strip("\n")
        code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        placeholder = f"\x00CODEBLOCK{len(code_blocks)}\x00"
        code_blocks.append(f"<pre><code>{code}</code></pre>")
        return placeholder
    html = re.sub(r"```(\w*)\n(.*?)```", _stash_code_block, html, flags=re.DOTALL)

    inline_codes = []
    def _stash_inline_code(m):
        code = m.group(1).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        placeholder = f"\x00INLINECODE{len(inline_codes)}\x00"
        inline_codes.append(f"<code>{code}</code>")
        return placeholder
    html = re.sub(r"`([^`]+)`", _stash_inline_code, html)

    # Headers
    html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # Bold and italic
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

    # Links — rewrite .md links to work in the browser
    def _rewrite_link(m):
        label, href = m.group(1), m.group(2)
        if href.endswith(".md") or ".md#" in href:
            href = href.replace(".md", "")
        return f'<a href="{href}">{label}</a>'
    html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _rewrite_link, html)

    # Horizontal rules
    html = re.sub(r"^---+$", "<hr>", html, flags=re.MULTILINE)

    # Blockquotes
    lines = html.split("\n")
    result = []
    in_quote = False
    for line in lines:
        if line.startswith("&gt; ") or line.startswith("> "):
            content = re.sub(r"^(&gt; |> )", "", line)
            if not in_quote:
                result.append("<blockquote>")
                in_quote = True
            result.append(content)
        else:
            if in_quote:
                result.append("</blockquote>")
                in_quote = False
            result.append(line)
    if in_quote:
        result.append("</blockquote>")
    html = "\n".join(result)

    # Tables
    def _render_table(m):
        rows = [r.strip() for r in m.group(0).strip().split("\n") if r.strip()]
        if len(rows) < 2:
            return m.group(0)
        header_cells = [c.strip() for c in rows[0].strip("|").split("|")]
        out = "<table><thead><tr>"
        for c in header_cells:
            out += f"<th>{c}</th>"
        out += "</tr></thead><tbody>"
        for row in rows[2:]:
            cells = [c.strip() for c in row.strip("|").split("|")]
            out += "<tr>"
            for c in cells:
                out += f"<td>{c}</td>"
            out += "</tr>"
        out += "</tbody></table>"
        return out
    html = re.sub(r"(\|.+\|[\t ]*\n\|[-| :]+\|[\t ]*\n(?:\|.+\|[\t ]*\n?)+)", _render_table, html)

    # Unordered lists
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", html)

    # Paragraphs — add breaks between loose text blocks
    html = re.sub(r"\n\n(?!<)", "\n<p>\n", html)

    # Restore stashed code blocks
    for i, block in enumerate(code_blocks):
        html = html.replace(f"\x00CODEBLOCK{i}\x00", block)
    for i, code in enumerate(inline_codes):
        html = html.replace(f"\x00INLINECODE{i}\x00", code)

    return html


class _MarkdownHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that renders .md files as styled HTML."""

    docs_dir: Path = Path(".")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path).lstrip("/")

        if path == "" or path.endswith("/"):
            path += "INDEX"

        # Try exact path, then with .md extension
        file_path = self.docs_dir / path
        if not file_path.exists() and not file_path.suffix:
            file_path = file_path.with_suffix(".md")

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, f"Not found: {path}")
            return

        if file_path.suffix == ".md":
            self._serve_markdown(file_path)
        else:
            self._serve_static(file_path)

    def _serve_markdown(self, file_path: Path):
        text = file_path.read_text(encoding="utf-8")
        body = _render_markdown(text)
        title = file_path.stem.replace("-", " ").title()

        # Build breadcrumb nav
        rel = file_path.relative_to(self.docs_dir)
        nav = '<nav><a href="/">docs</a>'
        parts = list(rel.parts)
        for i, part in enumerate(parts[:-1]):
            link = "/".join(parts[: i + 1])
            nav += f' / <a href="/{link}">{part}</a>'
        nav += f" / {parts[-1]}</nav>"

        html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Workbench Docs</title>
<style>{_CSS}</style>
</head><body>
{nav}
{body}
</body></html>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_static(self, file_path: Path):
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        """Suppress default logging."""
        pass


def docs_cmd(
    serve: bool = typer.Option(False, "--serve", "-s", help="Start a local documentation server."),
    port: int = typer.Option(8080, "--port", "-p", help="Port for the docs server."),
) -> None:
    """Open or serve the documentation."""
    from cli.main import banner, state

    banner()

    from cli.utils.config import find_workbench_yaml

    workbench_root = find_workbench_yaml().parent
    docs_dir = workbench_root / "docs"

    if not docs_dir.exists():
        console.print("  [red]✗[/red] No docs/ directory found.\n")
        raise typer.Exit(1)

    if serve:
        _serve_docs(docs_dir, port, state.quiet)
    else:
        _open_docs(docs_dir)


def _open_docs(docs_dir: Path) -> None:
    """Open docs/INDEX.md in the default editor or viewer."""
    index = docs_dir / "INDEX.md"
    if not index.exists():
        console.print("  [yellow]○[/yellow] docs/INDEX.md not found.\n")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR")
    if editor:
        console.print(f"  [bold]→[/bold] Opening docs/INDEX.md in {editor}...\n")
        subprocess.run([editor, str(index)])
    else:
        console.print("  [bold]→[/bold] Opening docs/INDEX.md...\n")
        if sys.platform == "darwin":
            subprocess.run(["open", str(index)])
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(index)])
        else:
            subprocess.run(["start", str(index)], shell=True)


def _serve_docs(docs_dir: Path, port: int, quiet: bool) -> None:
    """Serve docs with markdown rendering."""
    console.print(f"  [bold]→[/bold] Serving docs at [bold cyan]http://localhost:{port}[/bold cyan]\n")
    console.print("  [dim]Press Ctrl+C to stop.[/dim]\n")

    _MarkdownHandler.docs_dir = docs_dir

    try:
        with http.server.HTTPServer(("", port), _MarkdownHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n  [dim]Docs server stopped.[/dim]\n")
    except OSError as exc:
        if "Address already in use" in str(exc):
            console.print(f"  [red]✗[/red] Port {port} is already in use.")
            console.print(f"  [dim]Try: workbench docs --serve --port {port + 1}[/dim]\n")
        else:
            raise
