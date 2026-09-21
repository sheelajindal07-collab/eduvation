"""SEC-7: sanity checks on the hashed lockfiles and the CI wiring around
them — not a substitute for actually running `pip install --require-
hashes` (this dev machine is Windows; the lockfiles are Linux/py3.11 —
see requirements.lock's own header), but enough to catch a hand-edit that
breaks the hash-pinning contract or silently drops a required tool.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _requirement_names(lock_text: str) -> dict[str, bool]:
    """Map each top-level pinned package name to whether it carries at
    least one `--hash=sha256:` line -- `pip install --require-hashes`
    refuses to install anything that doesn't."""
    names: dict[str, bool] = {}
    current: str | None = None
    for raw_line in lock_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("--hash") and "==" in line:
            # e.g. "fastapi==0.115.0 \" -- the package name starts a new entry.
            current = line.split("==", 1)[0].strip()
            names[current] = False
        elif line.startswith("--hash") and current is not None:
            names[current] = True
    return names


class TestRuntimeLockfile:
    def test_every_pin_carries_a_hash(self) -> None:
        text = (REPO_ROOT / "requirements.lock").read_text(encoding="utf-8")
        names = _requirement_names(text)
        assert names, "requirements.lock parsed no requirements at all"
        unhashed = [name for name, hashed in names.items() if not hashed]
        assert not unhashed, f"unhashed pin(s) in requirements.lock: {unhashed}"

    def test_declared_runtime_dependencies_are_present(self) -> None:
        text = (REPO_ROOT / "requirements.lock").read_text(encoding="utf-8").lower()
        for package in ("fastapi", "uvicorn", "pydantic", "jinja2", "httpx", "supabase", "psycopg"):
            assert package in text, f"{package} missing from requirements.lock"


class TestDevLockfile:
    def test_every_pin_carries_a_hash(self) -> None:
        text = (REPO_ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
        names = _requirement_names(text)
        assert names, "requirements-dev.lock parsed no requirements at all"
        unhashed = [name for name, hashed in names.items() if not hashed]
        assert not unhashed, f"unhashed pin(s) in requirements-dev.lock: {unhashed}"

    def test_is_a_superset_of_the_runtime_lockfile(self) -> None:
        runtime_names = set(
            _requirement_names(
                (REPO_ROOT / "requirements.lock").read_text(encoding="utf-8")
            ).keys()
        )
        dev_names = set(
            _requirement_names(
                (REPO_ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
            ).keys()
        )
        missing = runtime_names - dev_names
        assert not missing, f"requirements-dev.lock is missing runtime pin(s): {missing}"

    def test_dev_tooling_is_present(self) -> None:
        text = (REPO_ROOT / "requirements-dev.lock").read_text(encoding="utf-8").lower()
        for tool in ("pytest", "ruff", "mypy", "pip-audit", "pytest-playwright"):
            assert tool in text, f"{tool} missing from requirements-dev.lock"


class TestCiWorkflow:
    def _load(self) -> dict[str, object]:
        text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        return yaml.safe_load(text)

    def test_parses_as_valid_yaml_with_the_expected_jobs(self) -> None:
        workflow = self._load()
        jobs = workflow["jobs"]
        assert "secret-scan" in jobs
        assert "lint-typecheck-test" in jobs

    def test_install_step_uses_the_hashed_lockfile(self) -> None:
        workflow = self._load()
        steps = workflow["jobs"]["lint-typecheck-test"]["steps"]
        install_steps = [s for s in steps if "requirements-dev.lock" in str(s.get("run", ""))]
        assert install_steps, "no CI step installs from requirements-dev.lock"
        assert "--require-hashes" in install_steps[0]["run"]

    def test_pip_audit_step_is_present(self) -> None:
        workflow = self._load()
        steps = workflow["jobs"]["lint-typecheck-test"]["steps"]
        assert any("pip-audit" in str(s.get("run", "")) for s in steps)

    def test_secret_scan_job_uses_gitleaks(self) -> None:
        workflow = self._load()
        steps = workflow["jobs"]["secret-scan"]["steps"]
        assert any("gitleaks" in str(s.get("uses", "")) for s in steps)
