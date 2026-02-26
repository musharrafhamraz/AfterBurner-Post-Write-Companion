"""GitHub tools — PyGithub wrappers for PR creation and management."""

import os
from typing import List, Optional

from loguru import logger


def create_pr(
    repo_name: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
    labels: Optional[List[str]] = None,
    reviewers: Optional[List[str]] = None,
    github_token: Optional[str] = None,
) -> dict:
    """
    Create a Pull Request on GitHub.

    Args:
        repo_name: Repository in 'owner/repo' format.
        branch: Head branch name.
        title: PR title.
        body: PR body (Markdown).
        base: Base branch to merge into.
        labels: Labels to apply to the PR.
        reviewers: GitHub usernames to request review from.
        github_token: GitHub personal access token.

    Returns:
        Dict with 'url', 'number', and 'html_url' keys.
    """
    from github import Github

    token = github_token or os.environ.get("AFTERBURNER_GITHUB_TOKEN")
    if not token:
        logger.error("GitHub token not provided — cannot create PR")
        return {"url": None, "number": None, "html_url": None, "error": "No GitHub token"}

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)

        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=base,
        )

        logger.info("Created PR #{}: {}", pr.number, pr.html_url)

        # Apply labels
        if labels:
            try:
                pr.set_labels(*labels)
            except Exception as e:
                logger.warning("Could not apply labels: {}", str(e))

        # Request reviewers
        if reviewers:
            try:
                pr.create_review_request(reviewers=reviewers)
            except Exception as e:
                logger.warning("Could not request reviewers: {}", str(e))

        return {
            "url": pr.html_url,
            "number": pr.number,
            "html_url": pr.html_url,
        }

    except Exception as e:
        logger.error("Failed to create PR: {}", str(e))
        return {"url": None, "number": None, "html_url": None, "error": str(e)}


def add_pr_comment(
    repo_name: str,
    pr_number: int,
    body: str,
    github_token: Optional[str] = None,
) -> bool:
    """
    Add a comment to an existing Pull Request.

    Args:
        repo_name: Repository in 'owner/repo' format.
        pr_number: PR number.
        body: Comment body (Markdown).
        github_token: GitHub personal access token.

    Returns:
        True if comment was added successfully.
    """
    from github import Github

    token = github_token or os.environ.get("AFTERBURNER_GITHUB_TOKEN")
    if not token:
        logger.error("GitHub token not provided")
        return False

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(body)
        logger.info("Added comment to PR #{}", pr_number)
        return True
    except Exception as e:
        logger.error("Failed to comment on PR #{}: {}", pr_number, str(e))
        return False


def get_codeowners(repo_path: str) -> List[str]:
    """
    Parse CODEOWNERS file to extract reviewer usernames.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        List of GitHub usernames (without @ prefix).
    """
    codeowners_paths = [
        os.path.join(repo_path, "CODEOWNERS"),
        os.path.join(repo_path, ".github", "CODEOWNERS"),
        os.path.join(repo_path, "docs", "CODEOWNERS"),
    ]

    for path in codeowners_paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    owners = set()
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Extract @usernames (not team handles)
                            parts = line.split()
                            for part in parts[1:]:  # Skip the file pattern
                                if part.startswith("@") and "/" not in part:
                                    owners.add(part.lstrip("@"))
                    logger.debug("Found CODEOWNERS: {}", owners)
                    return list(owners)
            except Exception as e:
                logger.warning("Failed to parse CODEOWNERS: {}", str(e))

    return []


def generate_pr_body(
    diff_summary: str,
    security_passed: bool,
    security_details: str,
    test_summary: str,
    deployment_url: Optional[str] = None,
) -> str:
    """
    Generate a standardised PR description.

    Args:
        diff_summary: Git diff stat summary.
        security_passed: Whether security checks passed.
        security_details: Human-readable security summary.
        test_summary: Human-readable test summary.
        deployment_url: Deployment URL if deployed.

    Returns:
        Markdown PR body.
    """
    sec_icon = "✅" if security_passed else "⚠️"

    body = f"""## 🚀 Afterburner Auto-PR

### Changes
```
{diff_summary}
```

### Security {sec_icon}
{security_details}

### Tests
{test_summary}
"""

    if deployment_url:
        body += f"""
### Deployment
- URL: {deployment_url}
"""

    body += """
---
*This PR was automatically created by [Afterburner](https://github.com/afterburner/afterburner) 🔥*
"""

    return body
