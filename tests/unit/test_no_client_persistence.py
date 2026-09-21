"""
Guard test: no service worker or client-side persistence.

This test verifies that BCION Lite templates and static assets contain no
references to service workers or client-side storage APIs, enforcing the
documented principle that the application maintains no client-side state
persistence.

The rationale is simple: a shared device (shared family phone, a
cybercafe kiosk, a library's public terminal) must not retain personal
data when a student walks away — state must live server-side only.
This decision is referenced in docs/CONTRACTS.md as part of the cache-class
and shared-device state handling, and in docs/DEVELOPMENT-PLAN.md under
OD-1 (offline deadline deferred while "no service worker" holds).

Banned patterns (searched case-sensitively):
  - serviceWorker: the Web APIs for registering/controlling a service worker
  - sw.js: a common filename for service-worker bundles
  - caches.: the Cache Storage API (caches.open, caches.delete, etc.)
  - localStorage: browser storage API for persistent key-value data
  - sessionStorage: browser storage API for session-scoped key-value data
  - indexedDB: browser storage API for large structured data
"""

from pathlib import Path

# List of banned patterns (case-sensitive)
BANNED_PATTERNS = [
    "serviceWorker",
    "sw.js",
    "caches.",
    "localStorage",
    "sessionStorage",
    "indexedDB",
]


def _scan_directory(directory: Path) -> dict[str, list[str]]:
    """
    Scan a directory for banned patterns.

    Returns:
        A dict mapping banned patterns to lists of (file_path, line_number, matched_line)
        tuples where the pattern was found.
    """
    findings = {pattern: [] for pattern in BANNED_PATTERNS}

    # Only scan text-like files; exclude binaries and minified CSS
    text_extensions = {".html", ".js", ".css", ".txt", ".json", ".xml"}
    exclude_files = {"app.css"}  # Minified, third-party Tailwind output

    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip excluded files
        if file_path.name in exclude_files:
            continue

        # Only scan text files
        if file_path.suffix not in text_extensions:
            continue

        # Read the file and search for patterns
        try:
            with open(file_path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    for pattern in BANNED_PATTERNS:
                        if pattern in line:
                            rel_path = file_path.relative_to(directory.parent)
                            findings[pattern].append(
                                (str(rel_path), line_num, line.rstrip())
                            )
        except (UnicodeDecodeError, OSError):
            # Skip files that can't be read as text
            continue

    return findings


def test_no_client_persistence_in_templates_and_static(tmp_path):
    """
    Test that app/web/templates/ and app/static/ contain no client-persistence APIs.

    This test scans the real directories and verifies no banned patterns are found.
    It should pass on a well-formed codebase.
    """
    # Get the project root
    project_root = Path(__file__).parent.parent.parent

    # Scan both directories
    template_dir = project_root / "app" / "web" / "templates"
    static_dir = project_root / "app" / "static"

    findings_templates = _scan_directory(template_dir)
    findings_static = _scan_directory(static_dir)

    # Combine findings
    all_findings = {}
    for pattern in BANNED_PATTERNS:
        all_findings[pattern] = (
            findings_templates[pattern] + findings_static[pattern]
        )

    # Check that no patterns were found
    found_any = any(all_findings.values())
    assert (
        not found_any
    ), f"Found banned client-persistence patterns:\n{_format_findings(all_findings)}"


def test_no_client_persistence_fails_with_planted_string(tmp_path):
    """
    Test that the guard actually fails when a banned pattern is planted.

    This test writes temporary files containing banned patterns and verifies
    the scanner catches them. This proves the test isn't vacuously passing
    because the scanner is broken.
    """
    # Create a temporary HTML file with a banned pattern
    test_file = tmp_path / "test.html"
    test_file.write_text("<script>\nwindow.localStorage.setItem('key', 'value');\n</script>")

    findings = _scan_directory(tmp_path)

    # Should find the localStorage pattern
    assert (
        len(findings["localStorage"]) > 0
    ), "Test did not find localStorage pattern in planted file"
    assert "test.html" in findings["localStorage"][0][0]

    # Test another pattern
    test_file_2 = tmp_path / "worker.js"
    test_file_2.write_text("navigator.serviceWorker.register('sw.js');")

    findings_2 = _scan_directory(tmp_path)

    assert (
        len(findings_2["serviceWorker"]) > 0
    ), "Test did not find serviceWorker pattern in planted file"
    assert (
        len(findings_2["sw.js"]) > 0
    ), "Test did not find sw.js pattern in planted file"


def _format_findings(findings: dict[str, list[str]]) -> str:
    """Format findings dict into a readable error message."""
    lines = []
    for pattern, matches in findings.items():
        if matches:
            lines.append(f"\n  Pattern '{pattern}':")
            for file_path, line_num, matched_line in matches:
                lines.append(f"    {file_path}:{line_num}")
                lines.append(f"      {matched_line}")
    return "".join(lines)
