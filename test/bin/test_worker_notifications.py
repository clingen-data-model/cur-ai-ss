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


def _flag(session, paper, resolved: bool = False):
    from datetime import datetime, timezone

    from lib.models.flag import FlagDB

    session.add(
        FlagDB(
            paper_id=paper.id,
            source='VARIANT_HARMONIZATION',
            kind='conflict',
            subject='s',
            evidence={},
            resolved_at=datetime.now(timezone.utc) if resolved else None,
        )
    )
    session.flush()


def test_links_to_the_paper_and_counts_open_flags(db_session, paper_with_owner, sent):
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)
    _flag(db_session, paper)
    _flag(db_session, paper)
    _flag(db_session, paper, resolved=True)

    _maybe_notify_completion(db_session, paper.id)

    body = sent[0]['body']
    assert f'/papers/{paper.id}/extraction?tab=flags' in body
    assert '2 flags to review' in body


def test_no_flags_links_to_the_default_tab(db_session, paper_with_owner, sent):
    paper, _ = paper_with_owner()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)

    _maybe_notify_completion(db_session, paper.id)

    body = sent[0]['body']
    assert body.count(f'/papers/{paper.id}/extraction') == 1
    assert 'tab=flags' not in body
    assert 'to review' not in body


def test_a_rerun_rearms_the_email_for_the_user_who_asked(
    db_session, paper_with_owner, sent
):
    from lib.tasks.misc import notify_on_next_completion

    paper, owner = paper_with_owner()
    other = UserDB(
        email='rerunner@example.com',
        hashed_password='x',
        first_name='Grace',
        last_name='Hopper',
        notify_on_paper_complete=True,
    )
    db_session.add(other)
    db_session.flush()
    _add_tasks(db_session, paper, TaskStatus.COMPLETED)
    _maybe_notify_completion(db_session, paper.id)
    assert [c['to'] for c in sent] == [owner.email]

    notify_on_next_completion(db_session, paper.id, other.id)
    _maybe_notify_completion(db_session, paper.id)

    assert [c['to'] for c in sent] == [owner.email, other.email]
