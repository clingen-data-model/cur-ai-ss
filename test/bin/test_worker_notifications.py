"""Completion emails fire once, to the right person, and never retroactively."""

import pytest

from lib.bin.worker import _maybe_notify_completion
from lib.models import GeneDB, PaperDB, TaskDB, UserDB
from lib.tasks.models import TaskStatus, TaskType


@pytest.fixture
def sent(monkeypatch):
    """Capture send_email calls as the worker module resolved it at import."""
    calls: list[dict] = []
    monkeypatch.setattr(
        'lib.bin.worker.send_email',
        lambda **kwargs: calls.append(kwargs),
    )
    return calls


@pytest.fixture
def paper_with_owner(db_session):
    def _make(notify: bool = True) -> tuple[PaperDB, UserDB]:
        user = UserDB(
            email='owner@example.com',
            hashed_password='x',
            first_name='Ada',
            last_name='Lovelace',
            notify_on_paper_complete=notify,
        )
        gene = GeneDB(symbol='BRCA1')
        db_session.add_all([user, gene])
        db_session.flush()
        paper = PaperDB(
            gene_id=gene.id,
            filename='p.pdf',
            content_hash='hash',
            title='A paper',
            updated_by_user_id=user.id,
        )
        db_session.add(paper)
        db_session.flush()
        return paper, user

    return _make


def _add_tasks(session, paper, *statuses, task_type=TaskType.PDF_PARSING):
    for s in statuses:
        session.add(TaskDB(paper_id=paper.id, type=task_type, status=s))
    session.flush()


def test_emails_the_owner_when_every_task_completes(db_session, paper_with_owner, sent):
    paper, user = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED, TaskStatus.COMPLETED)

    _maybe_notify_completion(db_session, paper.id)

    assert len(sent) == 1
    assert sent[0]['to'] == user.email
    assert 'A paper' in sent[0]['subject']
    assert paper.completion_notified_at is not None


def test_sends_exactly_once(db_session, paper_with_owner, sent):
    """The 'all complete' condition stays true and is re-checked on every
    terminal task, so without the stamp this would mail on each one."""
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)

    _maybe_notify_completion(db_session, paper.id)
    _maybe_notify_completion(db_session, paper.id)
    _maybe_notify_completion(db_session, paper.id)

    assert len(sent) == 1


def test_silent_while_any_task_is_unfinished(db_session, paper_with_owner, sent):
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED, TaskStatus.RUNNING)

    _maybe_notify_completion(db_session, paper.id)

    assert sent == []
    assert paper.completion_notified_at is None


def test_silent_when_a_task_failed(db_session, paper_with_owner, sent):
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED, TaskStatus.FAILED)

    _maybe_notify_completion(db_session, paper.id)

    assert sent == []


def test_chat_tasks_do_not_hold_the_pipeline_open(db_session, paper_with_owner, sent):
    """GENERAL_PAPER_QUESTION is ad hoc chat, not pipeline work -- a pending one
    must not stop the completion notice, matching _maybe_write_snapshot."""
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)
    _add_tasks(
        db_session,
        paper,
        TaskStatus.PENDING,
        task_type=TaskType.GENERAL_PAPER_QUESTION,
    )

    _maybe_notify_completion(db_session, paper.id)

    assert len(sent) == 1


def test_opted_out_user_is_not_emailed_but_is_stamped(
    db_session, paper_with_owner, sent
):
    """Stamping matters: enabling the preference later must not produce mail
    about work that finished before it was switched on."""
    paper, _ = paper_with_owner(notify=False)
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)

    _maybe_notify_completion(db_session, paper.id)

    assert sent == []
    assert paper.completion_notified_at is not None


def test_a_paper_with_no_tasks_is_not_complete(db_session, paper_with_owner, sent):
    """An empty task list would satisfy all() vacuously."""
    paper, _ = paper_with_owner()

    _maybe_notify_completion(db_session, paper.id)

    assert sent == []
    assert paper.completion_notified_at is None


def test_send_failure_leaves_the_paper_eligible(
    db_session, paper_with_owner, monkeypatch
):
    """A transient SMTP outage must not silently consume the notification."""
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)

    def _boom(**_):
        raise RuntimeError('smtp down')

    monkeypatch.setattr('lib.bin.worker.send_email', _boom)
    _maybe_notify_completion(db_session, paper.id)
    assert paper.completion_notified_at is None

    sent: list[dict] = []
    monkeypatch.setattr(
        'lib.bin.worker.send_email', lambda **kwargs: sent.append(kwargs)
    )
    _maybe_notify_completion(db_session, paper.id)
    assert len(sent) == 1
