"""Data models for Afterburner reports and results."""

from typing import Optional, List
from pydantic import BaseModel, Field


class SecurityFinding(BaseModel):
    """A single finding from a security scan tool."""

    tool: str = Field(description="Scanner that produced this finding: semgrep | bandit | cargo_audit | npm_audit")
    severity: str = Field(description="Severity level: critical | warning | info")
    file: str = Field(description="File path where the issue was found")
    line: Optional[int] = Field(default=None, description="Line number of the finding")
    message: str = Field(description="Human-readable description of the issue")
    rule_id: Optional[str] = Field(default=None, description="Scanner rule ID (e.g. B307 for bandit)")


class SecurityReport(BaseModel):
    """Aggregated security scan report across all tools."""

    findings: List[SecurityFinding] = Field(default_factory=list)
    passed: bool = Field(default=True, description="True if no findings at or above the blocking severity")
    scan_duration_ms: float = Field(default=0.0, description="Total scan time in milliseconds")

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "info")


class TestRun(BaseModel):
    """Result of a single test-framework execution."""

    framework: str = Field(description="Test framework: pytest | vitest | cargo | playwright")
    passed: int = Field(default=0, description="Number of tests passed")
    failed: int = Field(default=0, description="Number of tests failed")
    skipped: int = Field(default=0, description="Number of tests skipped")
    errors: List[str] = Field(default_factory=list, description="Error messages from failed tests")
    duration_ms: float = Field(default=0.0, description="Test run duration in milliseconds")
    output: str = Field(default="", description="Raw stdout/stderr output from the test run")

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and len(self.errors) == 0


class DeployResult(BaseModel):
    """Result of a deployment attempt."""

    target: str = Field(description="Deployment target: vercel | docker")
    url: Optional[str] = Field(default=None, description="Deployment URL (if successful)")
    status: str = Field(default="pending", description="Deployment status: success | failed | skipped")
    logs: Optional[str] = Field(default=None, description="Deployment logs or error output")


class AfterburnerReport(BaseModel):
    """Final summary report for the entire Afterburner run."""

    changed_files: List[str] = Field(default_factory=list)
    diff_summary: str = Field(default="")
    security_report: Optional[SecurityReport] = None
    test_results: List[TestRun] = Field(default_factory=list)
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    pr_url: Optional[str] = None
    deployment: Optional[DeployResult] = None
    hard_fail: bool = False
    errors: List[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        """Generate a rich Markdown summary of the Afterburner run."""
        lines = ["# 🚀 Afterburner Report\n"]

        # Changes
        lines.append("## Changes Detected")
        lines.append(f"- {len(self.changed_files)} file(s) changed")
        if self.diff_summary:
            lines.append(f"- {self.diff_summary}")
        for f in self.changed_files[:10]:
            lines.append(f"  - `{f}`")
        if len(self.changed_files) > 10:
            lines.append(f"  - ... and {len(self.changed_files) - 10} more")
        lines.append("")

        # Security
        if self.security_report:
            sr = self.security_report
            icon = "✅" if sr.passed else "❌"
            lines.append(f"## Security {icon}")
            lines.append(f"- Critical: {sr.critical_count}")
            lines.append(f"- Warnings: {sr.warning_count}")
            lines.append(f"- Info: {sr.info_count}")
            if not sr.passed:
                for finding in sr.findings:
                    if finding.severity == "critical":
                        lines.append(f"  - **{finding.tool}**: {finding.message} (`{finding.file}:{finding.line}`)")
            lines.append("")

        # Tests
        if self.test_results:
            all_ok = all(tr.all_passed for tr in self.test_results)
            icon = "✅" if all_ok else "❌"
            lines.append(f"## Tests {icon}")
            for tr in self.test_results:
                lines.append(f"- {tr.framework}: {tr.passed} passed, {tr.failed} failed ({tr.duration_ms:.0f}ms)")
            lines.append("")

        # Git
        if self.branch_name or self.commit_sha or self.pr_url:
            lines.append("## Git")
            if self.branch_name:
                lines.append(f"- Branch: `{self.branch_name}`")
            if self.commit_sha:
                lines.append(f"- Commit: `{self.commit_sha[:8]}`")
            if self.pr_url:
                lines.append(f"- PR: [{self.pr_url}]({self.pr_url})")
            lines.append("")

        # Deployment
        if self.deployment and self.deployment.status != "skipped":
            icon = "✅" if self.deployment.status == "success" else "❌"
            lines.append(f"## Deployment {icon}")
            lines.append(f"- Target: {self.deployment.target}")
            if self.deployment.url:
                lines.append(f"- URL: {self.deployment.url}")
            lines.append(f"- Status: {self.deployment.status}")
            lines.append("")

        # Errors
        if self.errors:
            lines.append("## ⚠️ Errors")
            for err in self.errors:
                lines.append(f"- {err}")
            lines.append("")

        if self.hard_fail:
            lines.append("> ❌ **Pipeline hard-failed.** See errors above for details.\n")

        return "\n".join(lines)
