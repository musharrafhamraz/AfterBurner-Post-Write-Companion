"""Launch Controller — CI/CD generation, deployment, and monitoring setup."""

from loguru import logger

from src.config import settings
from src.graph.state import AfterburnerState
from src.models.reports import DeployResult, AfterburnerReport
from src.tools.deploy_tools import deploy_vercel, deploy_docker_compose, generate_github_actions_workflow
from src.tools.monitoring_tools import setup_sentry, generate_prometheus_config, verify_health


def launch_controller_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: generate CI/CD config, deploy, set up monitoring.

    Handles:
    1. GitHub Actions workflow generation (always)
    2. Deployment to Vercel or Docker Compose (if configured)
    3. Sentry DSN injection (if configured)
    4. Prometheus config generation (if enabled)
    5. Health check on deployed URL

    Respects skip_deploy flag — only generates CI config and skips deploy.

    Returns state updates for:
        - deployment_url
        - deployment_status
        - monitoring_configured
        - current_stage
    """
    repo_path = state["repo_path"]
    skip_deploy = state.get("skip_deploy", settings.SKIP_DEPLOY)

    logger.info("🚀 Launch Controller: CI/CD + Deploy + Monitoring")

    # Generate CI/CD config
    if not skip_deploy:
        try:
            ci_path = generate_github_actions_workflow(repo_path)
            logger.info("CI/CD workflow: {}", ci_path)
        except Exception as e:
            logger.warning("CI/CD generation failed: {}", str(e))
    else:
        logger.info("Skipping CI/CD workflow generation (skip_deploy=True)")

    # Deploy
    deploy_result = None
    deploy_target = settings.DEPLOY_TARGET

    if skip_deploy or not deploy_target:
        logger.info("Deployment skipped (skip_deploy={}, target={})", skip_deploy, deploy_target)
        deploy_result = DeployResult(target="none", status="skipped")
    elif deploy_target == "vercel":
        deploy_result = deploy_vercel(repo_path, token=settings.VERCEL_TOKEN)
    elif deploy_target == "docker":
        deploy_result = deploy_docker_compose(repo_path)
    else:
        logger.warning("Unknown deploy target '{}' — skipping", deploy_target)
        deploy_result = DeployResult(target=deploy_target, status="skipped")

    # Monitoring
    monitoring_configured = False

    if settings.SENTRY_DSN:
        monitoring_configured = setup_sentry(repo_path, settings.SENTRY_DSN)

    if settings.ENABLE_PROMETHEUS:
        generate_prometheus_config(repo_path)
        monitoring_configured = True

    # Health check on deployed URL
    if deploy_result and deploy_result.url and deploy_result.status == "success":
        health = verify_health(deploy_result.url)
        if health["healthy"]:
            logger.info("Health check passed: {} ({}ms)", health["url"], health["response_time_ms"])
        else:
            logger.warning("Health check failed: {}", health.get("error"))

    return {
        "deployment_url": deploy_result.url if deploy_result else None,
        "deployment_status": deploy_result.status if deploy_result else "skipped",
        "monitoring_configured": monitoring_configured,
        "current_stage": "deployment_complete",
    }


def summarize_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: generate the final Markdown summary report.

    Collects results from all previous stages and produces a rich
    Markdown report suitable for IDE display.

    Returns state updates for:
        - final_summary
        - current_stage
    """
    logger.info("📋 Generating final summary...")

    # Reconstruct report from state
    from src.models.reports import SecurityReport

    security_report = None
    if state.get("security_report"):
        try:
            security_report = SecurityReport(**state["security_report"])
        except Exception:
            pass

    deploy_result = None
    if state.get("deployment_status"):
        deploy_result = DeployResult(
            target=settings.DEPLOY_TARGET or "none",
            url=state.get("deployment_url"),
            status=state.get("deployment_status", "skipped"),
        )

    # Build test runs
    from src.models.reports import TestRun
    test_runs = []
    for tr_data in state.get("test_results", []):
        try:
            test_runs.append(TestRun(**tr_data))
        except Exception:
            pass

    report = AfterburnerReport(
        changed_files=state.get("changed_files", []),
        diff_summary=state.get("diff_summary", ""),
        security_report=security_report,
        test_results=test_runs,
        branch_name=state.get("branch_name"),
        commit_sha=state.get("commit_sha"),
        pr_url=state.get("pr_url"),
        deployment=deploy_result,
        hard_fail=state.get("hard_fail", False),
        errors=state.get("errors", []),
    )

    summary = report.to_markdown()
    logger.info("Summary generated ({} chars)", len(summary))

    return {
        "final_summary": summary,
        "current_stage": "complete",
    }


def hard_fail_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: mark the pipeline as hard-failed.

    Called when reflection retries are exhausted.

    Returns state updates for:
        - hard_fail
        - current_stage
    """
    logger.error("💥 Pipeline hard-failed after {} retries", state.get("reflection_count", 0))
    return {
        "hard_fail": True,
        "current_stage": "hard_fail",
    }
