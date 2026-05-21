import subprocess

from sqlalchemy.orm import Session

from lib.models.agent_run import AgentRunDB, AgentRunResp


def get_current_git_hash() -> str:
    """Get the current git commit hash."""
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def ensure_agent_run(
    session: Session,
    description: str,
    git_hash: str | None = None,
) -> AgentRunResp:
    """Get or create an agent run.

    Args:
        session: Database session
        description: Human-readable description of the run
        git_hash: Git commit hash (if None, uses current HEAD)

    Returns:
        AgentRunResp with the existing or newly created run
    """
    if git_hash is None:
        git_hash = get_current_git_hash()

    run = (
        session.query(AgentRunDB)
        .filter_by(
            git_hash=git_hash,
            description=description,
        )
        .first()
    )

    if run is None:
        run = AgentRunDB(
            git_hash=git_hash,
            description=description,
        )
        session.add(run)
        session.flush()

    return AgentRunResp(
        id=run.id,
        git_hash=run.git_hash,
        description=run.description,
        updated_at=run.updated_at,
    )
