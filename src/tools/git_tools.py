"""Git tools — GitPython wrappers for diff, branch, commit, push operations."""

from typing import List, Optional, Dict
from pathlib import Path

import git
from loguru import logger


def get_changed_files(repo_path: str, ref: str = "HEAD") -> List[str]:
    """
    Get list of changed file paths relative to the given ref.

    Falls back to staged files if HEAD comparison yields nothing,
    then to untracked files as a last resort.

    Args:
        repo_path: Absolute path to the git repository.
        ref: Git ref to compare against (default: HEAD).

    Returns:
        List of relative file paths that changed.
    """
    repo = git.Repo(repo_path)

    # Try diff against ref
    try:
        diff_output = repo.git.diff("--name-only", ref)
        if diff_output.strip():
            files = [f.strip() for f in diff_output.strip().split("\n") if f.strip()]
            logger.info("Found {} changed files vs {}", len(files), ref)
            return files
    except git.GitCommandError:
        logger.debug("Could not diff against {}, trying staged files", ref)

    # Fall back to staged files
    staged_output = repo.git.diff("--name-only", "--cached")
    if staged_output.strip():
        files = [f.strip() for f in staged_output.strip().split("\n") if f.strip()]
        logger.info("Found {} staged files", len(files))
        return files

    # Fall back to untracked files
    untracked = repo.untracked_files
    if untracked:
        logger.info("Found {} untracked files", len(untracked))
        return list(untracked)

    logger.warning("No changed, staged, or untracked files found")
    return []


def get_diff_summary(repo_path: str, ref: str = "HEAD") -> str:
    """
    Get a human-readable diff summary (git diff --stat).

    Args:
        repo_path: Absolute path to the git repository.
        ref: Git ref to compare against.

    Returns:
        The git diff --stat output as a string.
    """
    repo = git.Repo(repo_path)
    try:
        return repo.git.diff("--stat", ref)
    except git.GitCommandError:
        return repo.git.diff("--stat", "--cached")


def get_full_diff(repo_path: str, ref: str = "HEAD") -> str:
    """
    Get the full diff content for LLM analysis.

    Args:
        repo_path: Absolute path to the git repository.
        ref: Git ref to compare against.

    Returns:
        Full unified diff as a string.
    """
    repo = git.Repo(repo_path)
    try:
        return repo.git.diff(ref)
    except git.GitCommandError:
        return repo.git.diff("--cached")


def classify_file_types(files: List[str]) -> Dict[str, List[str]]:
    """
    Group files by their programming language / type.

    Args:
        files: List of relative file paths.

    Returns:
        Dict mapping type names to file lists.
    """
    type_map: Dict[str, List[str]] = {}
    extension_types = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".json": "config",
        ".yaml": "config",
        ".yml": "config",
        ".toml": "config",
        ".md": "docs",
        ".txt": "docs",
        ".html": "web",
        ".css": "web",
        ".scss": "web",
        ".dockerfile": "docker",
    }

    for file_path in files:
        ext = Path(file_path).suffix.lower()
        name = Path(file_path).name.lower()

        # Special file name checks
        if name == "dockerfile" or name.startswith("dockerfile."):
            file_type = "docker"
        elif name == "docker-compose.yml" or name == "docker-compose.yaml":
            file_type = "docker"
        else:
            file_type = extension_types.get(ext, "other")

        type_map.setdefault(file_type, []).append(file_path)

    return type_map


def create_branch(repo_path: str, branch_name: str) -> str:
    """
    Create and checkout a new branch.

    Args:
        repo_path: Absolute path to the git repository.
        branch_name: Name of the branch to create.

    Returns:
        The name of the created branch.
    """
    repo = git.Repo(repo_path)

    # Check if already on a feature branch (not main/master/develop)
    current = repo.active_branch.name
    protected = {"main", "master", "develop", "dev"}

    if current not in protected:
        logger.info("Already on feature branch '{}', skipping branch creation", current)
        return current

    # Create and checkout new branch
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    logger.info("Created and checked out branch '{}'", branch_name)
    return branch_name


def commit(
    repo_path: str,
    files: List[str],
    message: str,
    sign: bool = False,
) -> str:
    """
    Stage specific files and commit with a message.

    Args:
        repo_path: Absolute path to the git repository.
        files: List of file paths to stage (relative to repo root).
        message: Commit message.
        sign: Whether to GPG-sign the commit.

    Returns:
        The commit SHA.
    """
    repo = git.Repo(repo_path)

    # Stage only the specified files
    repo.index.add(files)
    logger.debug("Staged {} files", len(files))

    # Commit
    commit_args = {}
    if sign:
        commit_args["gpg_sign"] = True

    new_commit = repo.index.commit(message, **commit_args)
    sha = new_commit.hexsha
    logger.info("Committed: {} ({})", message.split("\n")[0], sha[:8])
    return sha


def push(repo_path: str, branch: Optional[str] = None) -> bool:
    """
    Push the current branch to origin.

    Args:
        repo_path: Absolute path to the git repository.
        branch: Branch name to push (default: current branch).

    Returns:
        True if push succeeded.
    """
    repo = git.Repo(repo_path)
    branch = branch or repo.active_branch.name

    try:
        origin = repo.remote("origin")
        origin.push(branch)
        logger.info("Pushed branch '{}' to origin", branch)
        return True
    except Exception as e:
        logger.error("Push failed: {}", str(e))
        return False
