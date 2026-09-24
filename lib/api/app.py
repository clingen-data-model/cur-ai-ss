import asyncio
import json
import logging
import secrets
import shutil
import time
import traceback
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from agents import Runner
from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, func, select, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.agents.chat_agent import (
    ChatRunContext,
    build_paper_chat_context,
    make_chat_agent,
)
from lib.api.auth import get_current_user, get_current_user_optional
from lib.api.db import get_session, session_scope
from lib.api.middleware import make_log_request_middleware
from lib.core.agents_init import init_agents_sdk
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from lib.misc.avatars import (
    InvalidAvatarError,
    avatar_path,
    delete_avatar,
    store_avatar,
)
from lib.misc.curation.models import CurationSummaryRow
from lib.misc.curation.pptx import build_curation_pptx
from lib.misc.curation.summary import build_curation_row
from lib.misc.pdf.highlight import (
    GrobidAnnotation,
    figures_to_grobid_annotations,
    find_best_match,
    highlight_figures_in_pdf,
    highlight_words_in_pdf,
    parse_hex_color,
    words_to_grobid_annotations,
)
from lib.misc.pdf.misc import (
    pdf_first_page_to_thumbnail_pymupdf_bytes,
)
from lib.misc.pdf.parse import WordLoc
from lib.misc.pdf.paths import (
    pdf_dir,
    pdf_highlighted_path,
    pdf_image_path,
    pdf_raw_path,
    pdf_supplements_dir,
    pdf_thumbnail_path,
    pdf_words_json_path,
)
from lib.misc.snapshots import (
    InvalidSnapshotNameError,
    SnapshotIncompatibleError,
    SnapshotNotFoundError,
    current_state_hash,
    list_snapshots,
    restore_snapshot,
    write_snapshot_safe,
)
from lib.models import (
    AnnotatedVariantDB,
    AnnotatedVariantResp,
    ChangePasswordRequest,
    ChatMessageCreateRequest,
    ChatMessageDB,
    ChatMessageResp,
    ChatRole,
    FamilyCreateRequest,
    FamilyDB,
    FamilyResp,
    FamilyUpdateRequest,
    FileFormat,
    GeneDB,
    GeneResp,
    HarmonizedVariantDB,
    HarmonizedVariantResp,
    HighlightRequest,
    HpoCandidate,
    HpoDB,
    HpoRelinkRequest,
    HPOTerm,
    HumanEvidenceBlock,
    LoginRequest,
    OccurrencePairRequest,
    PaperDB,
    PaperResetRequest,
    PaperResetResp,
    PaperResp,
    PaperReviewUpdateRequest,
    PaperSummaryResp,
    PaperTag,
    PaperUpdateRequest,
    PatientCreateRequest,
    PatientDB,
    PatientResp,
    PatientUpdateRequest,
    PatientVariantOccurrenceCreateRequest,
    PatientVariantOccurrenceDB,
    PatientVariantOccurrenceResp,
    PatientVariantOccurrenceUpdateRequest,
    PedigreeDB,
    PedigreeResp,
    PhenotypeCreateRequest,
    PhenotypeDB,
    PhenotypeResp,
    SegregationAnalysisComputedDB,
    SegregationAnalysisResp,
    SegregationEvidenceDB,
    SegregationEvidenceUpdateRequest,
    SnapshotMeta,
    TaskDB,
    TokenResp,
    UserCreateRequest,
    UserDB,
    UserResp,
    UserSettingsUpdateRequest,
    UserSummaryResp,
    VariantCreateRequest,
    VariantDB,
    VariantResp,
    VariantUpdateRequest,
)
from lib.models.base import (
    Base,
    PatchModel,
    _editor_display_name,
    manual_evidence_block,
)
from lib.models.deletion_log import DeletionLogDB, DeletionLogResp, record_deletion
from lib.models.edit import EditDB, latest_edits_for, record_edit, record_edits
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.mondo import MondoComponentMapping, MondoTerm
from lib.models.patient import (
    AffectedStatus,
    CountryCode,
    Ethnicity,
    ProbandStatus,
    Race,
    RelationshipToProband,
    SexAtBirth,
    TwinType,
)
from lib.models.segregation_analysis import SegregationAnalysisComputedNestedResp
from lib.models.stats import (
    TaskStatsResp,
    TrackDurationStat,
)
from lib.reference_data.hpo import (
    find_matching_hpo_terms,
    get_ontology,
    warm_term_lookup_if_cached,
)
from lib.tasks import (
    TaskCreateRequest,
    TaskResp,
    enqueue_all_instances,
    enqueue_task,
    invalidate_descendants,
)
from lib.tasks.agent_session import chat_session
from lib.tasks.handlers import log_run_metrics
from lib.tasks.misc import summarize_paper_task_status
from lib.tasks.models import ACTIVE_STATUSES, TaskStatus, TaskType
from lib.tasks.tracks import PIPELINE_TRACKS

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config('alembic.ini')
    await asyncio.to_thread(command.upgrade, alembic_cfg, 'head')

    setup_logging()  # NB: run setup logging after the alembic setup to prevent it from overriding.
    init_agents_sdk()
    try:
        await asyncio.to_thread(warm_term_lookup_if_cached)
    except Exception:
        logger.warning(
            'Failed to warm the HPO term lookup cache at startup', exc_info=True
        )
    yield


app = FastAPI(title='PDF Extracting Jobs API', lifespan=lifespan)

# Static File Handling
app.mount(
    env.CAA_ROOT,  # URL path
    StaticFiles(directory=env.CAA_ROOT, html=False),
    name='caa',
)
# Parse CORS origins from env (comma-separated)
_cors_origins = [
    origin.strip() for origin in env.CORS_ALLOWED_ORIGINS.split(',') if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,  # Allows cookies to be sent cross-origin
    allow_methods=['*'],  # Allows all HTTP methods (GET, POST, PUT, etc.)
    allow_headers=['*'],  # Allows all headers
)
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB
app.middleware('http')(make_log_request_middleware(logger))  # Logging middleware


@app.middleware('http')
async def add_cache_headers(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    # Add 24-hour cache headers for static files (thumbnails, PDFs, etc.)
    if request.url.path.startswith(env.CAA_ROOT):
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 24 hours
    return response


@app.get('/status', tags=['health'])
def get_status() -> dict[str, str]:
    return {'status': 'ok'}


@app.post(
    '/auth/register',
    response_model=UserResp,
    status_code=status.HTTP_201_CREATED,
    tags=['auth'],
)
def register_user(
    request: UserCreateRequest, session: Session = Depends(get_session)
) -> Any:
    user = UserDB(
        email=request.email,
        hashed_password=hash_password(secrets.token_urlsafe(16)),
        first_name=request.first_name,
        last_name=request.last_name,
        description_of_use_case=request.description_of_use_case,
        is_active=False,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='A user with this email already exists',
        )
    return user


@app.post('/auth/login', response_model=TokenResp, tags=['auth'])
def login(request: LoginRequest, session: Session = Depends(get_session)) -> Any:
    user = session.query(UserDB).filter(UserDB.email == request.email).one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(
            request.password.get_secret_value(), user.hashed_password
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect email or password',
        )
    return TokenResp(access_token=create_access_token(user.id))


@app.get('/auth/me', response_model=UserResp, tags=['auth'])
def get_me(current_user: UserDB = Depends(get_current_user)) -> Any:
    return current_user


@app.patch('/auth/me', response_model=UserResp, tags=['auth'])
def update_me(
    request: UserSettingsUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Update the signed-in user's own settings.

    Scoped to current_user rather than taking an id: this is self-service, and
    the request model carries only fields a user may change about themselves --
    is_admin, is_active and max_papers are administrative and deliberately
    absent from it.
    """
    if request.notify_on_paper_complete is not None:
        current_user.notify_on_paper_complete = request.notify_on_paper_complete
    session.flush()
    return current_user


@app.put('/auth/me/avatar', response_model=UserResp, tags=['auth'])
async def upload_my_avatar(
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Replace the signed-in user's avatar.

    Scoped to current_user like the rest of /auth/me -- there is no id to
    tamper with, so one user cannot overwrite another's image.

    The uploaded content type is not consulted. store_avatar decides validity by
    decoding the bytes with Pillow and re-encoding them as PNG, so a file that
    merely claims to be an image cannot reach disk. That is a stronger check
    than the content_type comparison the paper upload does, and deliberately so:
    this one accepts input that is rendered straight back to other users.
    """
    try:
        store_avatar(current_user.id, await image.read())
    except InvalidAvatarError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Written after the file lands, so the column never advertises an avatar
    # that is not on disk. Also cache-busts the URL, whose path never changes.
    current_user.avatar_updated_at = datetime.now(timezone.utc)
    session.flush()
    return current_user


@app.delete('/auth/me/avatar', response_model=UserResp, tags=['auth'])
def delete_my_avatar(
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Drop the signed-in user's avatar, falling back to initials.

    Clearing the column is what makes the avatar disappear, so it happens even
    if no file was found -- that combination means the two had drifted, and the
    column is the one the UI reads.
    """
    delete_avatar(current_user.id)
    current_user.avatar_updated_at = None
    session.flush()
    return current_user


@app.post('/auth/change-password', response_model=UserResp, tags=['auth'])
def change_password(
    request: ChangePasswordRequest,
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    if not verify_password(
        request.current_password.get_secret_value(), current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Current password is incorrect',
        )
    current_user.hashed_password = hash_password(
        request.new_password.get_secret_value()
    )
    return current_user


@app.put('/papers', response_model=PaperResp, status_code=status.HTTP_201_CREATED)
def put_paper(
    gene_symbol: str = Form(...),
    uploaded_file: UploadFile = File(...),
    supplement_file: UploadFile | None = File(None),
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    if uploaded_file.content_type != 'application/pdf':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Only PDF files are allowed'
        )
    valid_supplement_types = {
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }
    if supplement_file and supplement_file.content_type not in valid_supplement_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only PDF, DOCX, or XLSX files are allowed for supplements',
        )
    gene = session.execute(
        select(GeneDB).where(GeneDB.symbol == gene_symbol)
    ).scalar_one_or_none()
    if not gene:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Gene {gene_symbol} not found',
        )
    main_content = uploaded_file.file.read()

    if current_user.max_papers is not None and current_user.max_papers <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Paper upload limit reached',
        )

    paper_db = PaperDB.from_content(main_content)
    paper_db.gene_id = gene.id
    paper_db.filename = uploaded_file.filename or ''
    paper_db.updated_by_user_id = current_user.id
    if current_user.max_papers is not None:
        current_user.max_papers -= 1
    session.add(paper_db)
    try:
        # Create initial PDF_PARSING task
        task = TaskDB(
            paper_id=paper_db.id,
            type=TaskType.PDF_PARSING,
            status=TaskStatus.PENDING,
            updated_by_user_id=current_user.id,
        )
        paper_db.tasks.append(task)
        session.flush()

        pdf_raw_path(paper_db.id).parent.mkdir(parents=True, exist_ok=True)
        with open(pdf_raw_path(paper_db.id), 'wb') as f:
            f.write(main_content)
        with open(pdf_highlighted_path(paper_db.id), 'wb') as f:
            f.write(main_content)
        with open(pdf_thumbnail_path(paper_db.id), 'wb') as fp:
            fp.write(pdf_first_page_to_thumbnail_pymupdf_bytes(main_content))

        if supplement_file:
            pdf_supplements_dir(paper_db.id).mkdir(parents=True, exist_ok=True)
            supplement_content = supplement_file.file.read()
            if (
                supplement_file.content_type
                == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ):
                paper_db.supplement_format = FileFormat.DOCX
            elif (
                supplement_file.content_type
                == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ):
                paper_db.supplement_format = FileFormat.XLSX
            else:
                paper_db.supplement_format = FileFormat.PDF
            with open(
                pdf_raw_path(
                    paper_db.id,
                    supplement=True,
                    file_format=paper_db.supplement_format.value,
                ),
                'wb',
            ) as f:
                f.write(supplement_content)
        # We fill in these counts for the response, they are not persisted to DB.
        paper_db.patient_count = len(paper_db.patients)
        paper_db.proband_count = len(
            [
                p
                for p in paper_db.patients
                if p.proband_status == ProbandStatus.Proband.value
            ]
        )
        paper_db.variant_count = len(paper_db.variants)
        paper_db.patient_variant_occurrences_count = len(
            paper_db.patient_variant_occurrences
        )
        return _paper_to_resp(paper_db, session)
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Paper with this content already exists',
        )


def _track_stats() -> list[TrackDurationStat]:
    """The pipeline's tracks, structurally -- which task types belong to which,
    and where each sits in the pipeline's ordering. No historical timing data:
    a track's typical wall-clock duration can't be measured reliably once a
    single task within it can be re-run on its own (see the "Where we are"
    note on this), so nothing here tries to estimate one anymore.
    """
    return [
        TrackDurationStat(
            id=track.id,
            label=track.label,
            task_types=list(track.task_types),
            stage=track.stage,
        )
        for track in PIPELINE_TRACKS
    ]


@app.get('/papers/active', response_model=list[PaperSummaryResp], tags=['papers'])
def list_active_papers(
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Papers with pipeline work in flight, for the header's activity indicator.

    Separate from GET /papers with a filter because that one computes a status
    for every paper before anything could be filtered on it -- the same cost as
    returning all of them. This starts from tasks instead, where RUNNING and
    QUEUED are indexed, so it reads a handful of rows rather than 94 papers.
    That matters: this is the one endpoint the UI polls.

    All three waiting states count, which is the whole of the task lifecycle
    before a handler finishes:

      PENDING  enqueued, not yet claimed. The scheduler polls every 10s, and
               with PDF parsing limited to one at a time a second paper waits
               here for the length of the first paper's parse.
      QUEUED   claimed by the scheduler, about to execute. Set at
               worker.py:282 to stop a task being scheduled twice, so it is
               brief -- but a poll can land inside it.
      RUNNING  a handler is executing it.

    Matching only the last two -- which this did at first -- left a paper the
    user had just queued reading as idle, because PENDING is where it spends the
    wait.
    """
    active_paper_ids = [
        row[0]
        for row in session.query(TaskDB.paper_id)
        .filter(TaskDB.status.in_(ACTIVE_STATUSES))
        .distinct()
    ]
    if not active_paper_ids:
        return []
    return _paper_summaries(session, active_paper_ids)


@app.get('/stats', response_model=TaskStatsResp, tags=['stats'])
def get_task_stats(
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """The pipeline's structure: which task types group into which track.

    A caller uses this alongside a paper's own task list to work out progress
    live from real task status -- not from a historical time estimate, which
    can't be measured reliably once a single task can be re-run on its own
    without disturbing the rest of the pipeline.
    """
    return TaskStatsResp(tracks=_track_stats())


@app.get('/users', response_model=list[UserSummaryResp], tags=['users'])
def list_users(
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Every active account, for pickers that must offer someone who hasn't
    touched a paper yet -- unlike GET /papers/collaborators, which is scoped to
    people who have."""
    users = session.query(UserDB).filter(UserDB.is_active.is_(True)).all()
    return sorted(
        (UserSummaryResp.model_validate(user) for user in users),
        key=lambda u: u.name.lower(),
    )


@app.get('/users/{user_id}/avatar')
def get_user_avatar(user_id: int) -> FileResponse:
    """Serve any user's avatar image, unauthenticated.

    Backs UserSummaryResp.avatar_url, which every avatar rendered for someone
    other than the signed-in user resolves through (collaborators, the
    worked-on-by filter, the review-assignee picker) -- unlike UserResp's,
    which points straight at the static-mounted file since only the caller's
    own avatar needs no path of its own. An <img src> cannot carry a bearer
    token, so this has to be reachable without one, same as the static mount.

    Cached for 24 hours like the static mount's files: the URL carries
    avatar_updated_at as a cache-busting query parameter, so a fresh upload
    is a new URL rather than stale content served from cache.
    """
    path = avatar_path(user_id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No avatar')
    return FileResponse(
        path,
        media_type='image/png',
        headers={'Cache-Control': 'public, max-age=86400'},
    )


@app.get('/papers/collaborators', response_model=list[UserSummaryResp])
def list_paper_collaborators(
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Everyone who has touched at least one paper.

    Backs the "worked on by" filter, whose options must be the full set of
    people regardless of which papers are currently listed -- deriving them from
    a filtered response would shrink the options to whoever is already visible.

    Not GET /users: this is the set that can usefully filter something, which is
    5 of 9 accounts on dev, and it exposes only UserSummaryResp rather than
    account fields.

    **Must stay above /papers/{paper_id}.** FastAPI matches in declaration
    order, so the parameterised route would otherwise take 'collaborators' as a
    paper_id and 422 trying to parse it as an int -- an int annotation narrows
    validation, not matching. A test covers this.
    """
    touchers = _paper_touchers(session)
    user_ids = {uid for uids in touchers.values() for uid in uids}
    if not user_ids:
        return []
    users = session.query(UserDB).filter(UserDB.id.in_(user_ids)).all()
    return sorted(
        (UserSummaryResp.model_validate(user) for user in users),
        key=lambda u: u.name.lower(),
    )


@app.get('/papers/{paper_id}', response_model=PaperResp)
def get_paper(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = (
        session.query(PaperDB)
        .options(
            selectinload(PaperDB.gene),
            selectinload(PaperDB.tasks),
            selectinload(PaperDB.patients),
            selectinload(PaperDB.variants),
            selectinload(PaperDB.patient_variant_occurrences),
        )
        .filter(PaperDB.id == paper_id)
        .one_or_none()
    )
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    paper_db.patient_count = len(paper_db.patients)
    paper_db.proband_count = len(
        [
            p
            for p in paper_db.patients
            if p.proband_status == ProbandStatus.Proband.value
        ]
    )
    paper_db.variant_count = len(paper_db.variants)
    paper_db.patient_variant_occurrences_count = len(
        paper_db.patient_variant_occurrences
    )
    return _paper_to_resp(paper_db, session)


@app.delete('/papers/{paper_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        return

    # Delete extracted PDF directory
    pdf_directory = pdf_dir(paper_id)
    if pdf_directory.exists():
        shutil.rmtree(pdf_directory)

    record_deletion(
        session,
        paper_id=paper_db.id,
        entity_type='paper',
        entity_id=paper_db.id,
        identifier_snapshot=paper_db.title or paper_db.doi or f'paper {paper_db.id}',
        editor=current_user,
    )
    session.delete(paper_db)
    session.flush()


@app.get('/papers/{paper_id}/snapshots', response_model=list[SnapshotMeta])
def get_paper_snapshots(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if paper_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    snapshots = list_snapshots(paper_id, session)
    if snapshots:
        state_hash = current_state_hash(paper_id, paper_db, session)
        for snapshot in snapshots:
            snapshot.matches_current = snapshot.state_hash == state_hash
    return snapshots


@app.post('/papers/{paper_id}/reset', response_model=PaperResetResp)
def reset_paper(
    paper_id: int,
    request: PaperResetRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if paper_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    active_tasks = (
        session.query(TaskDB)
        .filter(
            TaskDB.paper_id == paper_id,
            TaskDB.status.in_(ACTIVE_STATUSES),
        )
        .count()
    )
    if active_tasks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Cannot reset while extraction tasks are pending or running',
        )
    try:
        applied = restore_snapshot(
            paper_id, request.snapshot_name, session, current_user
        )
    except InvalidSnapshotNameError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SnapshotNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SnapshotIncompatibleError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if applied:
        # Bulk deletes/inserts bypass the identity map; expire so the response
        # below reads the restored rows, not stale in-session objects.
        session.expire_all()
    return {'changed': applied, 'paper': get_paper(paper_id, session)}


@app.patch('/papers/{paper_id}', response_model=PaperResp)
def update_paper(
    paper_id: int,
    patch_request: PaperUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = (
        session.query(PaperDB)
        .options(
            selectinload(PaperDB.gene),
            selectinload(PaperDB.tasks),
            selectinload(PaperDB.patients),
            selectinload(PaperDB.variants),
            selectinload(PaperDB.patient_variant_occurrences),
        )
        .filter(PaperDB.id == paper_id)
        .one_or_none()
    )

    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    previous_disease_name = paper_db.disease_name
    patch_request.apply_to(paper_db, current_user, session)
    # Disease MONDO fields are computed from the free-text disease name. Clear
    # them on manual text edits so clients never see a match for stale text.
    if (
        'disease_name' in patch_request.model_fields_set
        and paper_db.disease_name != previous_disease_name
    ):
        paper_db.mondo_id = None
        paper_db.mondo_term = None
        paper_db.mondo_match_context = None
    paper_db.patient_count = len(paper_db.patients)
    paper_db.proband_count = len(
        [
            p
            for p in paper_db.patients
            if p.proband_status == ProbandStatus.Proband.value
        ]
    )
    paper_db.variant_count = len(paper_db.variants)
    paper_db.patient_variant_occurrences_count = len(
        paper_db.patient_variant_occurrences
    )
    return _paper_to_resp(paper_db, session)


@app.patch('/papers/{paper_id}/review', response_model=PaperResp)
def update_paper_review(
    paper_id: int,
    request: PaperReviewUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Assign, start, complete or unassign a paper's curation review.

    Separate from PATCH /papers/{paper_id}: review status is a workflow the
    team manages, not paper metadata a curator edits, and it does not touch
    updated_by_user_id -- assigning a paper to someone else should not read as
    "last edited by" whoever made the assignment.
    """
    paper_db = (
        session.query(PaperDB)
        .options(
            selectinload(PaperDB.gene),
            selectinload(PaperDB.tasks),
            selectinload(PaperDB.patients),
            selectinload(PaperDB.variants),
            selectinload(PaperDB.patient_variant_occurrences),
        )
        .filter(PaperDB.id == paper_id)
        .one_or_none()
    )
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    if request.assignee_user_id is not None:
        assignee = session.get(UserDB, request.assignee_user_id)
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Assignee not found'
            )
    paper_db.review_status = request.review_status
    paper_db.review_assignee_user_id = request.assignee_user_id
    paper_db.patient_count = len(paper_db.patients)
    paper_db.proband_count = len(
        [
            p
            for p in paper_db.patients
            if p.proband_status == ProbandStatus.Proband.value
        ]
    )
    paper_db.variant_count = len(paper_db.variants)
    paper_db.patient_variant_occurrences_count = len(
        paper_db.patient_variant_occurrences
    )
    return _paper_to_resp(paper_db, session)


def _touch_paper(session: Session, paper_id: int, editor: UserDB | None) -> None:
    """Propagate a child-entity edit up to the parent paper's modification
    attribution. Editing a nested entity (variant, patient, family, ...) does not
    otherwise touch the paper row, so the dashboard's "last modified by" reflects
    whoever last edited anything belonging to the paper. No-op for machine writes
    (``editor is None``). ``updated_at`` is set explicitly so it bumps even when the
    same user edits twice (``onupdate`` would not fire on an unchanged FK value)."""
    if editor is None:
        return
    paper_db = session.get(PaperDB, paper_id)
    if paper_db is None:
        return
    paper_db.updated_by_user_id = editor.id
    paper_db.updated_at = func.now()


def _count_by_paper(
    session: Session, paper_id: Any, row_id: Any, where: Any = None
) -> dict[int, int]:
    """{paper_id: row count} from one grouped COUNT.

    Used instead of loading the rows and calling len() on them: the previous
    version selectinload'ed patients, variants and occurrences purely to measure
    their length, and none of those objects were ever serialised -- the response
    carries only the counts.

    `where` narrows what is counted, for a subset like probands among patients.
    """
    query = session.query(paper_id, func.count(row_id))
    if where is not None:
        query = query.filter(where)
    rows = query.group_by(paper_id).all()
    return {pid: n for pid, n in rows}


# Every table that records which user last touched a row *and* links straight to
# a paper. segregation_analysis_computed is deliberately absent: it reaches a
# paper only through a family, and it carries no human edits today.
#
# Measured on dev, the distinct (paper, user) pairs come almost entirely from
# two of these -- tasks 35, papers 27 -- against patients 3, families 2, and
# zero from variants or phenotypes. The latter are included anyway because they
# are where curation edits will land as the UI grows, not because they carry
# weight now.
_TOUCH_SOURCES: list[tuple[Any, Any]] = [
    (PaperDB.id, PaperDB.updated_by_user_id),
    (TaskDB.paper_id, TaskDB.updated_by_user_id),
    (PatientDB.paper_id, PatientDB.updated_by_user_id),
    (VariantDB.paper_id, VariantDB.updated_by_user_id),
    (PhenotypeDB.paper_id, PhenotypeDB.updated_by_user_id),
    (FamilyDB.paper_id, FamilyDB.updated_by_user_id),
]


def _paper_touchers(session: Session) -> dict[int, list[int]]:
    """{paper_id: [user_id, ...]} for every user who has touched each paper.

    One UNION rather than six queries, and DISTINCT in the database rather than
    deduping in Python -- tasks alone holds ~5k attributed rows on dev but only
    ~35 distinct (paper, user) pairs, so nearly all of that collapses before it
    crosses the wire.

    "Touched" is deliberately broader than papers.updated_by_user_id, which
    PATCH overwrites and so means last editor rather than everyone involved.
    """
    selects = [
        select(paper_col.label('paper_id'), user_col.label('user_id')).where(
            user_col.is_not(None)
        )
        for paper_col, user_col in _TOUCH_SOURCES
    ]
    rows = session.execute(union(*selects)).all()

    touchers: dict[int, list[int]] = defaultdict(list)
    for paper_id, user_id in rows:
        touchers[paper_id].append(user_id)
    return touchers


def _paper_summaries(
    session: Session, paper_ids: list[int] | None = None
) -> list[PaperSummaryResp]:
    """Build PaperSummaryResp for every paper, or just the ones named.

    Shared by the list endpoint and the activity indicator so the two cannot
    disagree about what a paper summary contains -- they render the same card.
    """
    patient_counts = _count_by_paper(session, PatientDB.paper_id, PatientDB.id)
    proband_counts = _count_by_paper(
        session,
        PatientDB.paper_id,
        PatientDB.id,
        where=PatientDB.proband_status == ProbandStatus.Proband.value,
    )
    variant_counts = _count_by_paper(session, VariantDB.paper_id, VariantDB.id)
    occurrence_counts = _count_by_paper(
        session,
        PatientVariantOccurrenceDB.paper_id,
        PatientVariantOccurrenceDB.id,
    )

    task_statuses: dict[int, list[TaskStatus]] = defaultdict(list)
    for paper_id, task_status in session.query(TaskDB.paper_id, TaskDB.status):
        task_statuses[paper_id].append(task_status)

    touchers = _paper_touchers(session)
    # Resolved in one pass: there are a handful of users and each appears on
    # many papers, so a lookup beats a per-paper join.
    users = {
        user.id: UserSummaryResp.model_validate(user)
        for user in session.query(UserDB).all()
    }

    query = session.query(PaperDB).options(selectinload(PaperDB.gene))
    if paper_ids is not None:
        if not paper_ids:
            return []
        query = query.filter(PaperDB.id.in_(paper_ids))

    return [
        PaperSummaryResp(
            id=paper.id,
            gene_symbol=paper.gene.symbol,
            collaborators=[
                users[uid] for uid in touchers.get(paper.id, []) if uid in users
            ],
            filename=paper.filename,
            title=paper.title,
            first_author=paper.first_author,
            journal_name=paper.journal_name,
            tags=[PaperTag(tag) for tag in paper.tags],
            updated_at=paper.updated_at,
            status=summarize_paper_task_status(task_statuses.get(paper.id, [])),
            disease_name=paper.disease_name,
            pmid=paper.pmid,
            updated_by=(
                users.get(paper.updated_by_user_id)
                if paper.updated_by_user_id is not None
                else None
            ),
            review_status=paper.review_status,
            review_assignee=(
                users.get(paper.review_assignee_user_id)
                if paper.review_assignee_user_id is not None
                else None
            ),
            patient_count=patient_counts.get(paper.id, 0),
            proband_count=proband_counts.get(paper.id, 0),
            variant_count=variant_counts.get(paper.id, 0),
            patient_variant_occurrences_count=occurrence_counts.get(paper.id, 0),
        )
        for paper in query.all()
    ]


@app.get('/papers', response_model=list[PaperSummaryResp])
def list_papers(
    touched_by: int | None = None,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Summaries for the gene table -- deliberately not the full PaperResp.

    Two things keep this cheap, and both were measured against production (95
    papers, a 4.97 MB response, 0.88s to first byte):

    Tasks are not embedded. They were 90.5% of that payload -- 9,092 objects --
    and the list view reduces them to a single badge per paper. Only the status
    column is read here, so only that column is selected; the full task list is
    fetched per paper from GET /papers/{paper_id}/tasks when the DAG is opened.

    Counts come from grouped COUNTs rather than from len() over eager-loaded
    relationships.

    `touched_by` narrows the list to papers that user has worked on, which backs
    the "My papers" view. It filters rather than paginating, so a user with no
    history gets an empty list -- on dev that is 65 of 95 papers with no human
    toucher at all.
    """
    if touched_by is None:
        return _paper_summaries(session)

    touchers = _paper_touchers(session)
    return _paper_summaries(
        session,
        [pid for pid, user_ids in touchers.items() if touched_by in user_ids],
    )


def _mondo_reasoning_block(
    mondo_id: str | None,
    mondo_term: str | None,
    mondo_match_context: dict | None,
) -> ReasoningBlock[MondoTerm | None]:
    """Reconstruct MONDO response reasoning from flattened DB columns."""
    context = mondo_match_context or {}
    reasoning = context.get('agent_reasoning')
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = 'MONDO linking not yet performed'

    value = (
        MondoTerm(mondo_id=mondo_id, label=mondo_term)
        if mondo_id and mondo_term
        else None
    )
    return ReasoningBlock[MondoTerm | None](
        value=value,
        reasoning=reasoning,
    )


def _mondo_components(
    mondo_match_context: dict | None,
) -> list[MondoComponentMapping]:
    """Extract decomposed disease-text component mappings from stored context.

    The MONDO linker decomposes a disease string into components (e.g. a primary
    disease mapped to MONDO plus a secondary phenotype mapped to HPO) when no
    single MONDO term captures the full text. The flattened ``mondo_id`` /
    ``mondo_term`` columns only carry the primary selection, so the per-component
    mappings are reconstructed here from ``mondo_match_context``.
    """
    context = mondo_match_context or {}
    raw_components = context.get('components') or []
    return [
        MondoComponentMapping.model_validate(component) for component in raw_components
    ]


def _paper_to_resp(row: PaperDB, session: Session) -> PaperResp:
    """Convert PaperDB to PaperResp, including reconstructed MONDO reasoning."""
    from lib.models.paper import PaperType
    from lib.models.patient_variant_occurrences import Inheritance

    resp = PaperResp(
        id=row.id,
        content_hash=row.content_hash,
        gene_symbol=row.gene.symbol,
        filename=row.filename,
        tags=[PaperTag(tag) for tag in row.tags],
        is_paper_relevant=row.is_paper_relevant,
        section_classifications=row.section_classifications,
        disease_name=row.disease_name,
        disease_name_evidence=HumanEvidenceBlock.model_validate(
            row.disease_name_evidence
        )
        if row.disease_name_evidence
        else None,
        disease_inheritance_mode=Inheritance(row.disease_inheritance_mode)
        if row.disease_inheritance_mode
        else None,
        disease_inheritance_mode_evidence=HumanEvidenceBlock.model_validate(
            row.disease_inheritance_mode_evidence
        )
        if row.disease_inheritance_mode_evidence
        else None,
        mondo=_mondo_reasoning_block(
            row.mondo_id,
            row.mondo_term,
            row.mondo_match_context,
        ),
        mondo_components=_mondo_components(row.mondo_match_context),
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by=_user_summary(row.updated_by),
        review_status=row.review_status,
        review_assignee=_user_summary(row.review_assignee),
        tasks=[
            TaskResp.model_validate(task, from_attributes=True) for task in row.tasks
        ],
        patient_count=row.patient_count,
        proband_count=row.proband_count,
        variant_count=row.variant_count,
        patient_variant_occurrences_count=row.patient_variant_occurrences_count,
        title=row.title,
        first_author=row.first_author,
        journal_name=row.journal_name,
        abstract=row.abstract,
        publication_year=row.publication_year,
        doi=row.doi,
        pmid=row.pmid,
        pmcid=row.pmcid,
        paper_types=[PaperType(paper_type) for paper_type in row.paper_types],
    )
    _attach_edit_history(resp, latest_edits_for(session, row), row)
    return resp


@app.get('/papers/{paper_id}/tasks', response_model=list[TaskResp])
def list_tasks(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    tasks = (
        session.query(TaskDB)
        .options(selectinload(TaskDB.updated_by))
        .filter(TaskDB.paper_id == paper_id)
        .order_by(TaskDB.id)
        .all()
    )
    return tasks


@app.post('/papers/{paper_id}/tasks', response_model=list[TaskResp])
def create_task(
    paper_id: int,
    request: TaskCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    # A rerun's handlers delete-and-recreate rows from scratch, which would
    # otherwise silently discard any manual edit made since the last snapshot
    # (pipeline-completion snapshots don't capture edits made afterward).
    # Fires regardless of skip_successors -- even a single scoped rerun
    # deletes and recreates rows for that scope.
    write_snapshot_safe(
        session, paper_id, description=f'Before re-running {request.type.value}'
    )

    # Clear the previous run's downstream rows first. Their COMPLETED status is
    # what the fan-in readiness gates read, and left in place it lets a successor
    # start against state this re-run is about to replace -- see
    # invalidate_descendants. Skipped when the caller asked for this task alone,
    # since nothing downstream will run.
    if not request.skip_successors:
        invalidate_descendants(session, paper_id, request.type)

    if (
        request.family_id is None
        and request.patient_id is None
        and request.variant_id is None
        and request.phenotype_id is None
        and request.patient_variant_occurrence_id is None
    ):
        tasks = enqueue_all_instances(
            session,
            paper_id=paper_id,
            task_type=request.type,
            skip_successors=request.skip_successors,
            additional_context=request.additional_context,
            updated_by_user_id=current_user.id,
        )
    else:
        task = enqueue_task(
            session,
            paper_id=paper_id,
            task_type=request.type,
            family_id=request.family_id,
            patient_id=request.patient_id,
            variant_id=request.variant_id,
            phenotype_id=request.phenotype_id,
            patient_variant_occurrence_id=request.patient_variant_occurrence_id,
            skip_successors=request.skip_successors,
            additional_context=request.additional_context,
            updated_by_user_id=current_user.id,
        )
        tasks = [task]
    return tasks


@app.get('/papers/{paper_id}/chat/messages', response_model=list[ChatMessageResp])
def list_chat_messages(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    return (
        session.query(ChatMessageDB)
        .options(selectinload(ChatMessageDB.created_by))
        .filter(ChatMessageDB.paper_id == paper_id)
        .order_by(ChatMessageDB.id)
        .all()
    )


@app.post('/papers/{paper_id}/chat/messages', response_model=ChatMessageResp)
async def send_chat_message(
    paper_id: int,
    request: ChatMessageCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Post a chat message and get the assistant's reply.

    One Runner.run() call per message, on the paper's own SQLiteSession
    (chat_session) -- the model itself decides whether to answer in prose or
    call queue_task, exactly as the deleted chat_routing_agent did. A queued
    task's confirmation is stored verbatim as the assistant's reply rather
    than whatever the model additionally says, so the visible message always
    matches what actually happened.
    """
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    user_message = ChatMessageDB(
        paper_id=paper_id,
        role=ChatRole.USER,
        content=request.message,
        created_by_user_id=current_user.id,
    )
    session.add(user_message)
    session.flush()

    context = build_paper_chat_context(paper_id)
    run_context = ChatRunContext()
    result = await Runner.run(
        make_chat_agent(paper_id, current_user.id),
        f'PAPER CONTEXT:\n{context}\n\nUser: {request.message}',
        session=chat_session(paper_id),
        context=run_context,
    )
    log_run_metrics('CHAT', result, paper_id=paper_id)
    reply = run_context.confirmation or str(result.final_output)

    assistant_message = ChatMessageDB(
        paper_id=paper_id,
        role=ChatRole.ASSISTANT,
        content=reply,
    )
    session.add(assistant_message)
    session.flush()
    return assistant_message


@app.delete('/papers/{paper_id}/chat/messages', status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_messages(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """Reset a paper's chat to a blank slate: no stored messages, no residual
    agent turn history -- the next message starts from just the paper's
    current DB state, same as the old Streamlit 'Clear Chat' button.

    Two operations because this schema splits what the old ConversationDB row
    held in one place: the stored transcript (ChatMessageDB rows) and the
    agent's own turn history (chat_session's SQLiteSession) are cleared
    separately.
    """
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        return

    session.query(ChatMessageDB).filter(ChatMessageDB.paper_id == paper_id).delete()
    session.flush()
    await chat_session(paper_id).clear_session()


def _user_summary(user: UserDB | None) -> UserSummaryResp | None:
    return UserSummaryResp.model_validate(user) if user else None


def _decode_edit_value(raw: str | None, current_value: Any) -> Any:
    """Decode a JSON-encoded old_value from the edits table, coerced to match
    ``current_value``'s type (e.g. str -> Zygosity) rather than left as the
    plain str/int/bool/list json.loads produces -- HumanEvidenceBlock's
    ``previous_value`` is typed as the field's real type (often a str Enum),
    and a serializer given a raw str where it expects an enum member emits a
    PydanticSerializationUnexpectedValue warning. Falls back to the
    undecorated json.loads result for a type json.loads already produces
    correctly (plain str/int/bool) or that isn't worth coercing (a list)."""
    if raw is None:
        return None
    decoded = json.loads(raw)
    if decoded is not None and current_value is not None:
        try:
            return type(current_value)(decoded)
        except (TypeError, ValueError):
            pass
    return decoded


def _attach_edit_history(resp: BaseModel, edits: dict[str, EditDB], row: Base) -> None:
    """Overlay per-field edit attribution from the edits table onto every
    HumanEvidenceBlock field of an already-built response, keyed by the
    response field name with any ``_evidence`` suffix stripped (e.g.
    ``identifier_evidence`` -> ``identifier``; segregation's evidence fields
    carry no such suffix -- e.g. ``extracted_lod_score`` -- and match as-is).
    Fields never patched via apply_to simply have no entry in ``edits`` and
    keep whatever attribution (if any) was baked into their evidence JSON at
    creation (see manual_evidence_block).

    Also corrects ``value`` itself for an edited field: the evidence JSON's
    embedded value is a snapshot from extraction/creation time that
    apply_to's raw-field branch (``setattr(obj, field, value)``) never
    touches, so without this it would keep showing the pre-edit value forever
    -- a latent inconsistency that previous_value's "changed from X to Y"
    display makes newly visible (Y would silently be stale, not just X
    missing). The corrected value is read straight off ``row`` -- the ORM
    object, which always carries the real, current column (e.g.
    ``row.zygosity`` alongside ``row.zygosity_evidence``) -- rather than
    ``resp``, since for segregation analysis the response's field *is* the
    HumanEvidenceBlock itself with no separate sibling scalar. Reading off the
    live column this way also means there's no need to store or decode a
    "new_value" from the edits table at all."""
    for name, value in resp.__dict__.items():
        if not isinstance(value, HumanEvidenceBlock):
            continue
        field_name = name[: -len('_evidence')] if name.endswith('_evidence') else name
        edit = edits.get(field_name)
        if edit is not None:
            value.edited_by_user_id = edit.user_id
            value.edited_by_name = (
                _editor_display_name(edit.user) if edit.user else None
            )
            value.edited_by_is_active = edit.user.is_active if edit.user else None
            value.edited_at = edit.edited_at
            value.previous_value = _decode_edit_value(edit.old_value, value.value)
            value.value = getattr(row, field_name, value.value)


def _family_to_resp(row: FamilyDB, session: Session) -> FamilyResp:
    resp = FamilyResp(
        id=row.id,
        paper_id=row.paper_id,
        identifier=row.identifier,
        identifier_evidence=HumanEvidenceBlock.model_validate(row.identifier_evidence),
        consanguinity=row.consanguinity,
        consanguinity_evidence=HumanEvidenceBlock.model_validate(
            row.consanguinity_evidence
        ),
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by=_user_summary(row.updated_by),
    )
    _attach_edit_history(resp, latest_edits_for(session, row), row)
    return resp


def _patient_to_resp(row: PatientDB, session: Session) -> PatientResp:
    resp = PatientResp(
        id=row.id,
        paper_id=row.paper_id,
        identifier=row.identifier,
        identifier_evidence=HumanEvidenceBlock.model_validate(row.identifier_evidence),
        proband_status=ProbandStatus(row.proband_status),
        proband_status_evidence=HumanEvidenceBlock.model_validate(
            row.proband_status_evidence
        ),
        sex=SexAtBirth(row.sex),
        sex_evidence=HumanEvidenceBlock.model_validate(row.sex_evidence),
        age_diagnosis=row.age_diagnosis,
        age_diagnosis_unit=row.age_diagnosis_unit,
        age_diagnosis_evidence=HumanEvidenceBlock.model_validate(
            row.age_diagnosis_evidence
        ),
        age_report=row.age_report,
        age_report_unit=row.age_report_unit,
        age_report_evidence=HumanEvidenceBlock.model_validate(row.age_report_evidence),
        age_death=row.age_death,
        age_death_unit=row.age_death_unit,
        age_death_evidence=HumanEvidenceBlock.model_validate(row.age_death_evidence),
        country_of_origin=CountryCode(row.country_of_origin),
        country_of_origin_evidence=HumanEvidenceBlock.model_validate(
            row.country_of_origin_evidence
        ),
        race=Race(row.race),
        race_evidence=HumanEvidenceBlock.model_validate(row.race_evidence),
        ethnicity=Ethnicity(row.ethnicity),
        ethnicity_evidence=HumanEvidenceBlock.model_validate(row.ethnicity_evidence),
        affected_status=AffectedStatus(row.affected_status),
        affected_status_evidence=HumanEvidenceBlock.model_validate(
            row.affected_status_evidence
        ),
        is_obligate_carrier=row.is_obligate_carrier,
        relationship_to_proband=RelationshipToProband(row.relationship_to_proband)
        if row.relationship_to_proband
        else None,
        twin_type=TwinType(row.twin_type) if row.twin_type else None,
        is_obligate_carrier_evidence=HumanEvidenceBlock.model_validate(
            row.is_obligate_carrier_evidence
        )
        if row.is_obligate_carrier_evidence
        else None,
        relationship_to_proband_evidence=HumanEvidenceBlock.model_validate(
            row.relationship_to_proband_evidence
        )
        if row.relationship_to_proband_evidence
        else None,
        twin_type_evidence=HumanEvidenceBlock.model_validate(row.twin_type_evidence)
        if row.twin_type_evidence
        else None,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by=_user_summary(row.updated_by),
        family_id=row.family.id,
        family_identifier=row.family.identifier,
        family_assignment_evidence=HumanEvidenceBlock.model_validate(
            row.family_assignment_evidence
        ),
    )
    _attach_edit_history(resp, latest_edits_for(session, row), row)
    return resp


@app.get('/papers/{paper_id}/patients', response_model=list[PatientResp])
def get_patients(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patients = (
        session.query(PatientDB)
        .options(selectinload(PatientDB.family), selectinload(PatientDB.updated_by))
        .filter(PatientDB.paper_id == paper_id)
        .order_by(PatientDB.id)
        .all()
    )
    return [_patient_to_resp(p, session) for p in patients]


@app.get('/papers/{paper_id}/families', response_model=list[FamilyResp])
def get_families(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    families = (
        session.query(FamilyDB)
        .options(selectinload(FamilyDB.updated_by))
        .filter(FamilyDB.paper_id == paper_id)
        .order_by(FamilyDB.id)
        .all()
    )
    return [_family_to_resp(f, session) for f in families]


@app.post('/papers/{paper_id}/families', response_model=FamilyResp)
def create_family(
    paper_id: int,
    create_request: FamilyCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Create a new family (e.g. to attach a manually added, unassociated patient to)."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    family_db = FamilyDB(
        paper_id=paper_id,
        identifier=create_request.identifier,
        identifier_evidence=manual_evidence_block(create_request.identifier),
        consanguinity=False,
        consanguinity_evidence=manual_evidence_block(False),
        updated_by_user_id=current_user.id,
    )

    session.add(family_db)
    session.flush()
    record_edits(session, family_db, ['identifier', 'consanguinity'], current_user)
    _touch_paper(session, paper_id, current_user)
    session.commit()
    session.refresh(family_db)
    return _family_to_resp(family_db, session)


@app.patch('/papers/{paper_id}/families/{family_id}', response_model=FamilyResp)
def update_family(
    paper_id: int,
    family_id: int,
    patch_request: FamilyUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    family_db = (
        session.query(FamilyDB)
        .filter(FamilyDB.id == family_id, FamilyDB.paper_id == paper_id)
        .one_or_none()
    )
    if not family_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Family not found'
        )
    patch_request.apply_to(family_db, current_user, session)
    _touch_paper(session, paper_id, current_user)
    return _family_to_resp(family_db, session)


@app.get('/papers/{paper_id}/pedigree', response_model=PedigreeResp | None)
def get_pedigree(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    pedigree = (
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).one_or_none()
    )
    if not pedigree:
        return None
    return PedigreeResp(
        image_id=pedigree.image_id,
        description=pedigree.description,
        image_url=str(pdf_image_path(paper_id, pedigree.image_id)),
    )


def _seg_evidence_block(value: Any, evidence_dict: dict | None) -> HumanEvidenceBlock:
    """Build a segregation evidence block, taking ``value`` from the scalar column
    (the source of truth for edits) and reasoning/quote/note from the JSON block."""
    data = dict(evidence_dict or {})
    data['value'] = value
    return HumanEvidenceBlock.model_validate(data)


def _segregation_analysis_to_resp(
    family: FamilyDB,
    evidence: SegregationEvidenceDB,
    computed: SegregationAnalysisComputedDB | None,
    session: Session,
) -> SegregationAnalysisResp:
    computed_nested = None
    if computed:
        computed_nested = SegregationAnalysisComputedNestedResp(
            segregation_count=ReasoningBlock.model_validate(
                computed.segregation_count_reasoning
            ),
            affected_count=ReasoningBlock.model_validate(
                computed.affected_count_reasoning
            ),
            unaffected_count=ReasoningBlock.model_validate(
                computed.unaffected_count_reasoning
            ),
            computed_lod_score=ReasoningBlock.model_validate(
                computed.computed_lod_score_reasoning
            ),
            points_assigned=ReasoningBlock.model_validate(
                computed.points_assigned_reasoning
            ),
            meets_minimum_criteria=ReasoningBlock.model_validate(
                computed.meets_minimum_criteria_reasoning
            ),
        )

    resp = SegregationAnalysisResp(
        id=computed.id if computed else evidence.id,
        family_id=family.id,
        extracted_lod_score=_seg_evidence_block(
            evidence.extracted_lod_score, evidence.extracted_lod_score_evidence
        ),
        has_unexplainable_non_segregations=_seg_evidence_block(
            evidence.has_unexplainable_non_segregations,
            evidence.has_unexplainable_non_segregations_evidence,
        ),
        computed=computed_nested,
        updated_at=computed.updated_at if computed else evidence.updated_at,
        updated_by_user_id=evidence.updated_by_user_id,
        updated_by=_user_summary(evidence.updated_by),
    )
    _attach_edit_history(resp, latest_edits_for(session, evidence), evidence)
    return resp


@app.get(
    '/papers/{paper_id}/segregation-analysis',
    response_model=list[SegregationAnalysisResp],
)
def get_segregation_analysis(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    # Get all families with their evidence and computed analysis using join
    rows = (
        session.query(FamilyDB, SegregationEvidenceDB, SegregationAnalysisComputedDB)
        .filter(FamilyDB.paper_id == paper_id)
        .join(SegregationEvidenceDB, FamilyDB.id == SegregationEvidenceDB.family_id)
        .outerjoin(
            SegregationAnalysisComputedDB,
            FamilyDB.id == SegregationAnalysisComputedDB.family_id,
        )
        .all()
    )
    result = [
        _segregation_analysis_to_resp(family, evidence, computed, session)
        for family, evidence, computed in rows
    ]
    return result


@app.patch(
    '/papers/{paper_id}/segregation-analysis/{family_id}',
    response_model=SegregationAnalysisResp,
)
def update_segregation_evidence(
    paper_id: int,
    family_id: int,
    patch_request: SegregationEvidenceUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    row = (
        session.query(FamilyDB, SegregationEvidenceDB)
        .join(SegregationEvidenceDB, FamilyDB.id == SegregationEvidenceDB.family_id)
        .filter(FamilyDB.paper_id == paper_id, FamilyDB.id == family_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Segregation evidence not found',
        )
    family, evidence = row
    patch_request.apply_to(evidence, current_user, session)
    _touch_paper(session, paper_id, current_user)
    computed = (
        session.query(SegregationAnalysisComputedDB)
        .filter(SegregationAnalysisComputedDB.family_id == family_id)
        .one_or_none()
    )
    return _segregation_analysis_to_resp(family, evidence, computed, session)


@app.get('/papers/{paper_id}/variants', response_model=list[VariantResp])
def get_variants(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    variants = (
        session.query(VariantDB)
        .options(
            joinedload(VariantDB.harmonized_variant).joinedload(
                HarmonizedVariantDB.updated_by
            ),
            joinedload(VariantDB.annotated_variant),
            selectinload(VariantDB.updated_by),
        )
        .filter(VariantDB.paper_id == paper_id)
        .order_by(VariantDB.id)
        .all()
    )
    return [_variant_to_resp(v, session) for v in variants]


def _variant_to_resp(row: VariantDB, session: Session) -> VariantResp:
    """Convert VariantDB to VariantResp, including harmonized and enriched data."""
    hv = row.harmonized_variant
    if hv:
        harmonized = ReasoningBlock[HarmonizedVariantResp | None](
            value=HarmonizedVariantResp(
                gnomad_style_coordinates=hv.gnomad_style_coordinates,
                rsid=hv.rsid,
                caid=hv.caid,
                hgvs_c=hv.hgvs_c,
                hgvs_p=hv.hgvs_p,
                hgvs_g=hv.hgvs_g,
                updated_by_user_id=hv.updated_by_user_id,
                updated_by=_user_summary(hv.updated_by),
            ),
            reasoning=hv.reasoning,
        )
    else:
        harmonized = ReasoningBlock[HarmonizedVariantResp | None](
            value=None,
            reasoning='Harmonization not yet performed',
        )
    enriched = (
        AnnotatedVariantResp(
            gnomad_style_coordinates=row.annotated_variant.gnomad_style_coordinates,
            rsid=row.annotated_variant.rsid,
            caid=row.annotated_variant.caid,
            pathogenicity=row.annotated_variant.pathogenicity,
            submissions=row.annotated_variant.submissions,
            stars=row.annotated_variant.stars,
            exon=row.annotated_variant.exon,
            vep_consequence=row.annotated_variant.vep_consequence,
            revel=row.annotated_variant.revel,
            alphamissense_class=row.annotated_variant.alphamissense_class,
            alphamissense_score=row.annotated_variant.alphamissense_score,
            spliceai=row.annotated_variant.spliceai,
            gnomad_top_level_af=row.annotated_variant.gnomad_top_level_af,
            gnomad_ac=row.annotated_variant.gnomad_ac,
            gnomad_an=row.annotated_variant.gnomad_an,
            gnomad_popmax_af=row.annotated_variant.gnomad_popmax_af,
            gnomad_popmax_population=row.annotated_variant.gnomad_popmax_population,
            gnomad_popmax_ac=row.annotated_variant.gnomad_popmax_ac,
            gnomad_popmax_an=row.annotated_variant.gnomad_popmax_an,
        )
        if row.annotated_variant
        else None
    )
    resp = VariantResp(
        id=row.id,
        paper_id=row.paper_id,
        variant=row.variant,
        transcript=row.transcript,
        protein_accession=row.protein_accession,
        genomic_accession=row.genomic_accession,
        lrg_accession=row.lrg_accession,
        gene_accession=row.gene_accession,
        genomic_coordinates=row.genomic_coordinates,
        genome_build=row.genome_build,
        rsid=row.rsid,
        caid=row.caid,
        hgvs_c=row.hgvs_c,
        hgvs_p=row.hgvs_p,
        hgvs_g=row.hgvs_g,
        variant_type=row.variant_type,
        functional_evidence=row.functional_evidence,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by=_user_summary(row.updated_by),
        transcript_evidence=EvidenceBlock.model_validate(row.transcript_evidence),
        protein_accession_evidence=EvidenceBlock.model_validate(
            row.protein_accession_evidence
        ),
        genomic_accession_evidence=EvidenceBlock.model_validate(
            row.genomic_accession_evidence
        ),
        lrg_accession_evidence=EvidenceBlock.model_validate(row.lrg_accession_evidence),
        gene_accession_evidence=EvidenceBlock.model_validate(
            row.gene_accession_evidence
        ),
        genomic_coordinates_evidence=EvidenceBlock.model_validate(
            row.genomic_coordinates_evidence
        ),
        genome_build_evidence=EvidenceBlock.model_validate(row.genome_build_evidence),
        rsid_evidence=EvidenceBlock.model_validate(row.rsid_evidence),
        caid_evidence=EvidenceBlock.model_validate(row.caid_evidence),
        variant_evidence=EvidenceBlock.model_validate(row.variant_evidence),
        hgvs_c_evidence=EvidenceBlock.model_validate(row.hgvs_c_evidence),
        hgvs_p_evidence=EvidenceBlock.model_validate(row.hgvs_p_evidence),
        hgvs_g_evidence=EvidenceBlock.model_validate(row.hgvs_g_evidence),
        variant_type_evidence=HumanEvidenceBlock.model_validate(
            row.variant_type_evidence
        ),
        functional_evidence_evidence=HumanEvidenceBlock.model_validate(
            row.functional_evidence_evidence
        ),
        main_focus=row.main_focus,
        main_focus_evidence=HumanEvidenceBlock.model_validate(row.main_focus_evidence),
        harmonized_variant=harmonized,
        annotated_variant=enriched,
    )
    _attach_edit_history(resp, latest_edits_for(session, row), row)
    return resp


@app.patch('/papers/{paper_id}/variants/{variant_id}', response_model=VariantResp)
def update_variant(
    paper_id: int,
    variant_id: int,
    patch_request: VariantUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    variant_db = (
        session.query(VariantDB)
        .options(
            joinedload(VariantDB.harmonized_variant),
            joinedload(VariantDB.annotated_variant),
        )
        .filter(VariantDB.id == variant_id, VariantDB.paper_id == paper_id)
        .one_or_none()
    )
    if not variant_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Variant not found'
        )
    patch_request.apply_to(variant_db, current_user, session)
    # Editing any harmonized field invalidates the downstream enrichment row,
    # which was computed by key lookup from the pre-edit coordinates. Treat
    # all harmonized siblings uniformly so a future enrichment lookup added
    # for e.g. hgvs_p cannot silently produce stale annotations. The
    # LLM-generated reasoning on harmonized_variant is intentionally kept
    # intact: it remains the agent's explanation of its original choices,
    # and the curator's rationale belongs in human_edit_note fields.
    harmonized_update = (
        patch_request.harmonized_variant
        if 'harmonized_variant' in patch_request.model_fields_set
        else None
    )
    if harmonized_update is not None:
        if variant_db.harmonized_variant is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Variant has not been harmonized by the server yet',
            )
        harmonized_update.apply_to(variant_db.harmonized_variant, current_user)
        # delete-orphan cascade removes the row
        variant_db.annotated_variant = None
    _touch_paper(session, paper_id, current_user)
    session.flush()
    return _variant_to_resp(variant_db, session)


def _phenotype_to_resp(session: Session, row: PhenotypeDB) -> PhenotypeResp:
    edits = latest_edits_for(session, row)
    if row.hpo:
        hpo_value = (
            HPOTerm(id=row.hpo.hpo_id, name=row.hpo.hpo_name)
            if row.hpo.hpo_id and row.hpo.hpo_name
            else None
        )
        hpo_edits = latest_edits_for(session, row.hpo)
        hpo = ReasoningBlock[HPOTerm | None](
            value=hpo_value,
            reasoning=row.hpo.reasoning,
            manually_entered='hpo' in hpo_edits,
        )
    else:
        hpo = ReasoningBlock[HPOTerm | None](
            value=None,
            reasoning='HPO linking not yet performed',
        )
    return PhenotypeResp(
        id=row.id,
        paper_id=row.paper_id,
        patient_id=row.patient_id,
        concept=row.concept,
        concept_evidence=EvidenceBlock.model_validate(row.concept_evidence),
        negated=row.negated,
        uncertain=row.uncertain,
        family_history=row.family_history,
        onset=row.onset,
        location=row.location,
        severity=row.severity,
        modifier=row.modifier,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        hpo=hpo,
    )


@app.get(
    '/papers/{paper_id}/occurrences',
    response_model=list[PatientVariantOccurrenceResp],
)
def get_occurrences(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Get all patient-variant occurrences for a paper."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantOccurrenceDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantOccurrenceDB.patient_id == PatientDB.id)
        .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
        .order_by(
            PatientVariantOccurrenceDB.patient_id, PatientVariantOccurrenceDB.variant_id
        )
        .all()
    )
    return [
        _patient_variant_occurrence_to_resp(
            link[0], patient_identifier=link[1], session=session
        )
        for link in links
    ]


@app.get(
    '/papers/{paper_id}/variants/{variant_id}/occurrences',
    response_model=list[PatientVariantOccurrenceResp],
)
def get_variant_occurrences(
    paper_id: int,
    variant_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Get all patient occurrences of a specific variant."""
    variant_db = session.get(VariantDB, variant_id)
    if not variant_db or variant_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Variant not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantOccurrenceDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantOccurrenceDB.patient_id == PatientDB.id)
        .filter(
            PatientVariantOccurrenceDB.variant_id == variant_id,
            PatientVariantOccurrenceDB.paper_id == paper_id,
        )
        .order_by(PatientVariantOccurrenceDB.patient_id)
        .all()
    )
    return [
        _patient_variant_occurrence_to_resp(
            link[0], patient_identifier=link[1], session=session
        )
        for link in links
    ]


@app.get(
    '/papers/{paper_id}/patients/{patient_id}/occurrences',
    response_model=list[PatientVariantOccurrenceResp],
)
def get_patient_occurrences(
    paper_id: int,
    patient_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Get all variant occurrences for a specific patient."""
    patient_db = session.get(PatientDB, patient_id)
    if not patient_db or patient_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    from lib.models.patient import PatientDB

    links = (
        session.query(PatientVariantOccurrenceDB, PatientDB.identifier)
        .join(PatientDB, PatientVariantOccurrenceDB.patient_id == PatientDB.id)
        .filter(
            PatientVariantOccurrenceDB.patient_id == patient_id,
            PatientVariantOccurrenceDB.paper_id == paper_id,
        )
        .order_by(PatientVariantOccurrenceDB.variant_id)
        .all()
    )
    return [
        _patient_variant_occurrence_to_resp(
            link[0], patient_identifier=link[1], session=session
        )
        for link in links
    ]


@app.patch(
    '/papers/{paper_id}/occurrences/{occurrence_id}',
    response_model=PatientVariantOccurrenceResp,
)
def update_occurrence(
    paper_id: int,
    occurrence_id: int,
    patch_request: PatientVariantOccurrenceUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    occurrence_db = (
        session.query(PatientVariantOccurrenceDB)
        .filter(
            PatientVariantOccurrenceDB.id == occurrence_id,
            PatientVariantOccurrenceDB.paper_id == paper_id,
        )
        .one_or_none()
    )
    if not occurrence_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Occurrence not found'
        )
    patch_request.apply_to(occurrence_db, current_user, session)
    _touch_paper(session, paper_id, current_user)
    patient = session.get(PatientDB, occurrence_db.patient_id)
    return _patient_variant_occurrence_to_resp(
        occurrence_db,
        patient_identifier=patient.identifier if patient else '',
        session=session,
    )


def _clear_pairing(row: PatientVariantOccurrenceDB) -> None:
    row.paired_variant_link_id = None
    row.paired_variant_confidence = None
    row.paired_variant_confidence_reasoning = None
    flag_modified(row, 'paired_variant_confidence_reasoning')


@app.patch(
    '/papers/{paper_id}/occurrences/{occurrence_id}/pair',
    response_model=list[PatientVariantOccurrenceResp],
)
def pair_occurrence(
    paper_id: int,
    occurrence_id: int,
    pair_request: OccurrencePairRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Manually pair (or, with paired_occurrence_id=None, unpair) this
    occurrence with another occurrence of the same patient, as a
    curator-confirmed compound-het pair. Unlike update_occurrence, this
    mutates up to two rows symmetrically (the pairing FK points both ways),
    plus a stale partner on either side when re-pairing, so it can't go
    through PatchModel.apply_to's single-row mechanism -- mirrors
    relink_phenotype_hpo in shape (a dedicated PATCH for a relationship the
    generic patch endpoint can't express) but returns every row it touched
    rather than just the primary one, since the client needs to see a former
    partner come back unpaired too."""
    from lib.models.patient_variant_occurrences import CompoundHetConfidence

    occurrence_a = (
        session.query(PatientVariantOccurrenceDB)
        .filter(
            PatientVariantOccurrenceDB.id == occurrence_id,
            PatientVariantOccurrenceDB.paper_id == paper_id,
        )
        .one_or_none()
    )
    if not occurrence_a:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Occurrence not found'
        )

    affected: list[PatientVariantOccurrenceDB] = [occurrence_a]

    if pair_request.paired_occurrence_id is None:
        if occurrence_a.paired_variant_link_id is not None:
            old_partner = session.get(
                PatientVariantOccurrenceDB, occurrence_a.paired_variant_link_id
            )
            _clear_pairing(occurrence_a)
            if old_partner:
                _clear_pairing(old_partner)
                affected.append(old_partner)
    else:
        if pair_request.paired_occurrence_id == occurrence_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Cannot pair an occurrence with itself',
            )
        occurrence_b = (
            session.query(PatientVariantOccurrenceDB)
            .filter(
                PatientVariantOccurrenceDB.id == pair_request.paired_occurrence_id,
                PatientVariantOccurrenceDB.paper_id == paper_id,
            )
            .one_or_none()
        )
        if not occurrence_b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Partner occurrence not found',
            )
        if occurrence_b.patient_id != occurrence_a.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Paired occurrences must belong to the same patient',
            )

        if occurrence_a.paired_variant_link_id not in (None, occurrence_b.id):
            old_a_partner = session.get(
                PatientVariantOccurrenceDB, occurrence_a.paired_variant_link_id
            )
            if old_a_partner:
                _clear_pairing(old_a_partner)
                affected.append(old_a_partner)
        if occurrence_b.paired_variant_link_id not in (None, occurrence_a.id):
            old_b_partner = session.get(
                PatientVariantOccurrenceDB, occurrence_b.paired_variant_link_id
            )
            if old_b_partner:
                _clear_pairing(old_b_partner)
                affected.append(old_b_partner)

        reasoning_block = ReasoningBlock[CompoundHetConfidence](
            value=CompoundHetConfidence.confirmed,
            reasoning='Manually paired by curator.',
            manually_entered=True,
        ).model_dump(mode='json')

        occurrence_a.paired_variant_link_id = occurrence_b.id
        occurrence_b.paired_variant_link_id = occurrence_a.id
        occurrence_a.paired_variant_confidence = CompoundHetConfidence.confirmed.value
        occurrence_b.paired_variant_confidence = CompoundHetConfidence.confirmed.value
        occurrence_a.paired_variant_confidence_reasoning = reasoning_block
        occurrence_b.paired_variant_confidence_reasoning = reasoning_block
        flag_modified(occurrence_a, 'paired_variant_confidence_reasoning')
        flag_modified(occurrence_b, 'paired_variant_confidence_reasoning')
        affected.append(occurrence_b)

    for row in affected:
        PatchModel.stamp_updated_by(row, current_user)
        row.updated_at = func.now()

    _touch_paper(session, paper_id, current_user)
    session.commit()
    for row in affected:
        session.refresh(row)

    patients_by_id = {
        row.patient_id: session.get(PatientDB, row.patient_id) for row in affected
    }
    resps = []
    for row in affected:
        patient = patients_by_id[row.patient_id]
        resps.append(
            _patient_variant_occurrence_to_resp(
                row,
                patient_identifier=patient.identifier if patient else '',
                session=session,
            )
        )
    return resps


def _patient_variant_occurrence_to_resp(
    row: PatientVariantOccurrenceDB,
    patient_identifier: str,
    session: Session,
) -> PatientVariantOccurrenceResp:
    """Convert PatientVariantOccurrenceDB to PatientVariantOccurrenceResp."""
    from lib.models import Inheritance, TestingMethod, Zygosity
    from lib.models.evidence_block import ReasoningBlock
    from lib.models.patient_variant_occurrences import CompoundHetConfidence

    resp = PatientVariantOccurrenceResp(
        id=row.id,
        paper_id=row.paper_id,
        patient_id=row.patient_id,
        patient_identifier=patient_identifier,
        variant_id=row.variant_id,
        zygosity=Zygosity(row.zygosity),
        zygosity_evidence=HumanEvidenceBlock.model_validate(row.zygosity_evidence),
        inheritance=Inheritance(row.inheritance),
        inheritance_evidence=HumanEvidenceBlock.model_validate(
            row.inheritance_evidence
        ),
        de_novo=row.de_novo,
        de_novo_evidence=HumanEvidenceBlock.model_validate(row.de_novo_evidence),
        testing_methods=[TestingMethod(m) for m in row.testing_methods],
        testing_methods_evidence=[
            EvidenceBlock.model_validate(m) for m in row.testing_methods_evidence
        ],
        testing_methods_note=row.testing_methods_note,
        disease_name=row.disease_name,
        disease_name_evidence=HumanEvidenceBlock.model_validate(
            row.disease_name_evidence
        )
        if row.disease_name_evidence
        else None,
        mondo=_mondo_reasoning_block(
            row.mondo_id,
            row.mondo_term,
            row.mondo_match_context,
        ),
        mondo_components=_mondo_components(row.mondo_match_context),
        paired_variant_link_id=row.paired_variant_link_id,
        paired_variant_confidence=CompoundHetConfidence(row.paired_variant_confidence)
        if row.paired_variant_confidence
        else None,
        paired_variant_confidence_reasoning=ReasoningBlock[
            CompoundHetConfidence
        ].model_validate(row.paired_variant_confidence_reasoning)
        if row.paired_variant_confidence_reasoning
        else None,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by=_user_summary(row.updated_by),
    )
    _attach_edit_history(resp, latest_edits_for(session, row), row)
    return resp


# ==============================
# Patient CRUD
# ==============================


@app.post('/papers/{paper_id}/patients', response_model=PatientResp)
def create_patient(
    paper_id: int,
    create_request: PatientCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Create a new patient."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    family_db = session.get(FamilyDB, create_request.family_id)
    if not family_db or family_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Family not found'
        )

    patient_db = PatientDB(
        paper_id=paper_id,
        family_id=create_request.family_id,
        identifier=create_request.identifier,
        identifier_evidence=manual_evidence_block(create_request.identifier),
        proband_status=create_request.proband_status,
        proband_status_evidence=manual_evidence_block(create_request.proband_status),
        affected_status=create_request.affected_status,
        affected_status_evidence=manual_evidence_block(create_request.affected_status),
        sex=create_request.sex,
        sex_evidence=manual_evidence_block(create_request.sex),
        country_of_origin=create_request.country_of_origin,
        country_of_origin_evidence=manual_evidence_block(
            create_request.country_of_origin
        ),
        race=create_request.race,
        race_evidence=manual_evidence_block(create_request.race),
        ethnicity=create_request.ethnicity,
        ethnicity_evidence=manual_evidence_block(create_request.ethnicity),
        age_diagnosis=create_request.age_diagnosis,
        age_diagnosis_evidence=manual_evidence_block(create_request.age_diagnosis),
        age_diagnosis_unit=create_request.age_diagnosis_unit,
        age_report=create_request.age_report,
        age_report_evidence=manual_evidence_block(create_request.age_report),
        age_report_unit=create_request.age_report_unit,
        age_death=create_request.age_death,
        age_death_evidence=manual_evidence_block(create_request.age_death),
        age_death_unit=create_request.age_death_unit,
        is_obligate_carrier=create_request.is_obligate_carrier,
        relationship_to_proband=create_request.relationship_to_proband,
        twin_type=create_request.twin_type,
        family_assignment_evidence=manual_evidence_block(family_db.identifier),
        updated_by_user_id=current_user.id,
    )

    session.add(patient_db)
    session.flush()
    record_edits(
        session,
        patient_db,
        [
            'identifier',
            'proband_status',
            'affected_status',
            'sex',
            'country_of_origin',
            'race',
            'ethnicity',
            'age_diagnosis',
            'age_report',
            'age_death',
            'family_assignment',
        ],
        current_user,
    )
    _touch_paper(session, paper_id, current_user)
    session.commit()
    session.refresh(patient_db)
    return _patient_to_resp(patient_db, session)


@app.delete(
    '/papers/{paper_id}/patients/{patient_id}', status_code=status.HTTP_204_NO_CONTENT
)
def delete_patient(
    paper_id: int,
    patient_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """Delete a patient (cascades to occurrences)."""
    patient_db = session.get(PatientDB, patient_id)
    if not patient_db or patient_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )

    record_deletion(
        session,
        paper_id=patient_db.paper_id,
        entity_type='patient',
        entity_id=patient_db.id,
        identifier_snapshot=patient_db.identifier,
        editor=current_user,
    )
    session.delete(patient_db)
    _touch_paper(session, paper_id, current_user)
    session.commit()


# ==============================
# Variant CRUD
# ==============================


@app.post('/papers/{paper_id}/variants', response_model=VariantResp)
def create_variant(
    paper_id: int,
    create_request: VariantCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Create a new raw (unharmonized) variant."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    variant_db = VariantDB(
        paper_id=paper_id,
        variant=create_request.variant,
        variant_evidence=manual_evidence_block(create_request.variant),
        transcript=create_request.transcript,
        transcript_evidence=manual_evidence_block(create_request.transcript),
        protein_accession=create_request.protein_accession,
        protein_accession_evidence=manual_evidence_block(
            create_request.protein_accession
        ),
        genomic_accession=create_request.genomic_accession,
        genomic_accession_evidence=manual_evidence_block(
            create_request.genomic_accession
        ),
        lrg_accession=create_request.lrg_accession,
        lrg_accession_evidence=manual_evidence_block(create_request.lrg_accession),
        gene_accession=create_request.gene_accession,
        gene_accession_evidence=manual_evidence_block(create_request.gene_accession),
        genomic_coordinates=create_request.genomic_coordinates,
        genomic_coordinates_evidence=manual_evidence_block(
            create_request.genomic_coordinates
        ),
        genome_build=create_request.genome_build,
        genome_build_evidence=manual_evidence_block(create_request.genome_build),
        rsid=create_request.rsid,
        rsid_evidence=manual_evidence_block(create_request.rsid),
        caid=create_request.caid,
        caid_evidence=manual_evidence_block(create_request.caid),
        hgvs_c=create_request.hgvs_c,
        hgvs_c_evidence=manual_evidence_block(create_request.hgvs_c),
        hgvs_p=create_request.hgvs_p,
        hgvs_p_evidence=manual_evidence_block(create_request.hgvs_p),
        hgvs_g=create_request.hgvs_g,
        hgvs_g_evidence=manual_evidence_block(create_request.hgvs_g),
        variant_type=create_request.variant_type,
        variant_type_evidence=manual_evidence_block(create_request.variant_type),
        functional_evidence=create_request.functional_evidence,
        functional_evidence_evidence=manual_evidence_block(
            create_request.functional_evidence
        ),
        main_focus=create_request.main_focus,
        main_focus_evidence=manual_evidence_block(create_request.main_focus),
        updated_by_user_id=current_user.id,
    )

    session.add(variant_db)
    session.flush()
    # Only variant_type/functional_evidence/main_focus are HumanEvidenceBlock
    # fields (the only ones VariantUpdateRequest can *_human_edit_note patch);
    # the rest are plain EvidenceBlock with no edit attribution to record.
    record_edits(
        session,
        variant_db,
        ['variant_type', 'functional_evidence', 'main_focus'],
        current_user,
    )
    _touch_paper(session, paper_id, current_user)
    session.commit()
    session.refresh(variant_db)
    return _variant_to_resp(variant_db, session)


@app.delete(
    '/papers/{paper_id}/variants/{variant_id}', status_code=status.HTTP_204_NO_CONTENT
)
def delete_variant(
    paper_id: int,
    variant_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """Delete a variant (cascades to occurrences)."""
    variant_db = session.get(VariantDB, variant_id)
    if not variant_db or variant_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Variant not found'
        )

    record_deletion(
        session,
        paper_id=variant_db.paper_id,
        entity_type='variant',
        entity_id=variant_db.id,
        identifier_snapshot=variant_db.variant or variant_db.hgvs_c,
        editor=current_user,
    )
    session.delete(variant_db)
    _touch_paper(session, paper_id, current_user)
    session.commit()


# ==============================
# Occurrence CRUD
# ==============================


@app.post('/papers/{paper_id}/occurrences', response_model=PatientVariantOccurrenceResp)
def create_occurrence(
    paper_id: int,
    create_request: PatientVariantOccurrenceCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Create a new patient-variant occurrence."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    patient_db = session.get(PatientDB, create_request.patient_id)
    if not patient_db or patient_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )

    variant_db = session.get(VariantDB, create_request.variant_id)
    if not variant_db or variant_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Variant not found'
        )

    occurrence_db = PatientVariantOccurrenceDB(
        paper_id=paper_id,
        patient_id=create_request.patient_id,
        variant_id=create_request.variant_id,
        zygosity=create_request.zygosity,
        zygosity_evidence=manual_evidence_block(create_request.zygosity),
        inheritance=create_request.inheritance,
        inheritance_evidence=manual_evidence_block(create_request.inheritance),
        de_novo=create_request.de_novo,
        de_novo_evidence=manual_evidence_block(create_request.de_novo),
        testing_methods=create_request.testing_methods,
        testing_methods_evidence=[
            manual_evidence_block(method) for method in create_request.testing_methods
        ],
        disease_name=create_request.disease_name,
        updated_by_user_id=current_user.id,
    )

    session.add(occurrence_db)
    session.flush()
    # testing_methods_evidence is a list of plain EvidenceBlock (no per-item
    # attribution -- see testing_methods_note); only these three are
    # HumanEvidenceBlock fields.
    record_edits(
        session, occurrence_db, ['zygosity', 'inheritance', 'de_novo'], current_user
    )
    _touch_paper(session, paper_id, current_user)
    session.commit()
    session.refresh(occurrence_db)
    return _patient_variant_occurrence_to_resp(
        occurrence_db, patient_identifier=patient_db.identifier, session=session
    )


@app.delete(
    '/papers/{paper_id}/occurrences/{occurrence_id}',
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_occurrence(
    paper_id: int,
    occurrence_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """Delete a patient-variant occurrence."""
    occurrence_db = session.get(PatientVariantOccurrenceDB, occurrence_id)
    if not occurrence_db or occurrence_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Occurrence not found'
        )

    record_deletion(
        session,
        paper_id=occurrence_db.paper_id,
        entity_type='occurrence',
        entity_id=occurrence_db.id,
        identifier_snapshot=(
            f'patient {occurrence_db.patient_id}, variant {occurrence_db.variant_id} '
            f'({occurrence_db.zygosity})'
        ),
        editor=current_user,
    )
    session.delete(occurrence_db)
    _touch_paper(session, paper_id, current_user)
    session.commit()


@app.get('/papers/{paper_id}/deletion-log', response_model=list[DeletionLogResp])
def list_deletion_log(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Every patient/variant/occurrence/phenotype/paper deletion recorded for
    this paper.

    Deliberately does not 404 when the paper itself no longer exists -- a
    paper's own deletion entry (entity_type='paper') must stay visible after
    the paper is gone, since paper_id here is a snapshot, not a live FK."""
    return (
        session.query(DeletionLogDB)
        .options(selectinload(DeletionLogDB.deleted_by))
        .filter(DeletionLogDB.paper_id == paper_id)
        .order_by(DeletionLogDB.id)
        .all()
    )


@app.get(
    '/papers/{paper_id}/curation-row',
    response_model=CurationSummaryRow,
)
def get_curation_row(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Get a curation summary row for a single paper."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    try:
        return build_curation_row(paper_id, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    '/papers/{paper_id}/curation-export',
)
def get_curation_export(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Response:
    """Export a curation summary as a PPTX file."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    try:
        rows = build_curation_row(paper_id, session)
        pptx_bytes = build_curation_pptx(rows)
        return Response(
            content=pptx_bytes,
            media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            headers={
                'Content-Disposition': f'attachment; filename="curation_{paper_id}.pptx"'
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    '/papers/{paper_id}/patients/{patient_id}/phenotypes',
    response_model=list[PhenotypeResp],
)
def get_phenotypes(
    paper_id: int,
    patient_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patient_db = (
        session.query(PatientDB).filter(PatientDB.id == patient_id).one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    phenotypes = (
        session.query(PhenotypeDB)
        .options(joinedload(PhenotypeDB.hpo))
        .filter(
            PhenotypeDB.patient_id == patient_id,
        )
        .order_by(PhenotypeDB.id)
        .all()
    )
    return [_phenotype_to_resp(session, p) for p in phenotypes]


@app.post(
    '/papers/{paper_id}/patients/{patient_id}/phenotypes',
    response_model=PhenotypeResp,
)
def create_phenotype(
    paper_id: int,
    patient_id: int,
    create_request: PhenotypeCreateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Manually add a phenotype row. HPO id is optional; when given, it must
    resolve to a real term in the ontology."""
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )
    patient_db = (
        session.query(PatientDB)
        .filter(PatientDB.id == patient_id, PatientDB.paper_id == paper_id)
        .one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )

    hpo_name: str | None = None
    if create_request.hpo_id is not None:
        hpo_name = get_ontology().get_term_name(create_request.hpo_id)
        if hpo_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Unknown HPO id: {create_request.hpo_id}',
            )

    phenotype_db = PhenotypeDB(
        paper_id=paper_id,
        patient_id=patient_id,
        concept=create_request.concept,
        concept_evidence=manual_evidence_block(create_request.concept),
        updated_by_user_id=current_user.id,
    )
    session.add(phenotype_db)
    session.flush()
    record_edits(session, phenotype_db, ['concept'], current_user)

    if create_request.hpo_id is not None:
        phenotype_db.hpo = HpoDB(
            hpo_id=create_request.hpo_id,
            hpo_name=hpo_name,
            reasoning='Manually linked by curator',
        )
        session.flush()  # hpo needs a real id before edits can reference it
        record_edits(session, phenotype_db.hpo, ['hpo'], current_user)

    _touch_paper(session, paper_id, current_user)
    session.commit()
    session.refresh(phenotype_db)
    return _phenotype_to_resp(session, phenotype_db)


@app.delete(
    '/papers/{paper_id}/phenotypes/{phenotype_id}',
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_phenotype(
    paper_id: int,
    phenotype_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """Delete a phenotype (cascades to its HPO link, if any)."""
    phenotype_db = session.get(PhenotypeDB, phenotype_id)
    if not phenotype_db or phenotype_db.paper_id != paper_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Phenotype not found'
        )

    record_deletion(
        session,
        paper_id=phenotype_db.paper_id,
        entity_type='phenotype',
        entity_id=phenotype_db.id,
        identifier_snapshot=phenotype_db.concept,
        editor=current_user,
    )
    session.delete(phenotype_db)
    _touch_paper(session, paper_id, current_user)
    session.commit()


@app.patch(
    '/papers/{paper_id}/phenotypes/{phenotype_id}/hpo',
    response_model=PhenotypeResp,
)
def relink_phenotype_hpo(
    paper_id: int,
    phenotype_id: int,
    relink_request: HpoRelinkRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Change (or, with hpo_id=None, clear) which HPO term a phenotype is
    linked to."""
    phenotype_db = (
        session.query(PhenotypeDB)
        .options(joinedload(PhenotypeDB.hpo))
        .filter(PhenotypeDB.id == phenotype_id, PhenotypeDB.paper_id == paper_id)
        .one_or_none()
    )
    if not phenotype_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Phenotype not found'
        )

    if relink_request.hpo_id is None:
        hpo_name = None
        reasoning = 'Unlinked by curator'
    else:
        hpo_name = get_ontology().get_term_name(relink_request.hpo_id)
        if hpo_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Unknown HPO id: {relink_request.hpo_id}',
            )
        reasoning = 'Manually linked by curator'

    old_hpo_id = phenotype_db.hpo.hpo_id if phenotype_db.hpo else None
    if phenotype_db.hpo:
        phenotype_db.hpo.hpo_id = relink_request.hpo_id
        phenotype_db.hpo.hpo_name = hpo_name
        phenotype_db.hpo.reasoning = reasoning
    else:
        phenotype_db.hpo = HpoDB(
            hpo_id=relink_request.hpo_id,
            hpo_name=hpo_name,
            reasoning=reasoning,
        )
        session.flush()  # hpo needs a real id before edits can reference it
    record_edit(session, phenotype_db.hpo, 'hpo', current_user, old_value=old_hpo_id)
    phenotype_db.updated_by_user_id = current_user.id
    phenotype_db.updated_at = func.now()

    _touch_paper(session, paper_id, current_user)
    session.commit()
    session.refresh(phenotype_db)
    return _phenotype_to_resp(session, phenotype_db)


@app.get('/hpo/search', response_model=list[HpoCandidate])
def search_hpo_terms(
    text: str = Query(..., min_length=2),
    limit: int = Query(10, le=25),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    """Fuzzy-match free text against HPO term names/synonyms, for a curator
    picking a term to (re-)link -- the same matching function the extraction
    pipeline uses to propose candidates. Note: when nothing clears the
    similarity cutoff, this falls back to the ontology root term rather than
    an empty list (see find_matching_hpo_terms), so a very short or unrelated
    query can still show one low-relevance result."""
    return find_matching_hpo_terms(text, limit=limit)


@app.patch('/papers/{paper_id}/patients/{patient_id}', response_model=PatientResp)
def update_patient(
    paper_id: int,
    patient_id: int,
    patch_request: PatientUpdateRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    patient_db = (
        session.query(PatientDB)
        .options(selectinload(PatientDB.family))
        .filter(PatientDB.id == patient_id, PatientDB.paper_id == paper_id)
        .one_or_none()
    )
    if not patient_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found'
        )
    patch_request.apply_to(patient_db, current_user, session)
    _touch_paper(session, paper_id, current_user)
    return _patient_to_resp(patient_db, session)


@app.get('/genes/search', response_model=list[GeneResp])
def search_genes(
    prefix: str = Query(...),
    limit: int = Query(10),
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    query = (
        session.query(GeneDB)
        .filter(GeneDB.symbol.startswith(prefix))
        .order_by(GeneDB.symbol)
        .limit(limit)
    )
    return query.all()


@app.get('/genes', response_model=list[GeneResp])
def list_genes(
    limit: int | None = Query(None),
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> Any:
    query = session.query(GeneDB).order_by(GeneDB.symbol)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@app.post('/papers/{paper_id}/highlight', status_code=status.HTTP_204_NO_CONTENT)
def highlight_pdf(
    paper_id: int,
    request: HighlightRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """
    Highlight text in a PDF and save the highlighted version.

    Args:
        paper_id: The ID of the paper
        request: JSON body with queries (list) and color fields
    """
    # Verify paper exists
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    # Parse and validate color
    try:
        rgb_color = parse_hex_color(request.color)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Return early if no highlightable evidence (e.g., all from supplements)
    if not request.queries and not request.image_ids and not request.table_ids:
        return

    # Load words from JSON file
    words_file = pdf_words_json_path(paper_id)
    with open(words_file, 'r') as f:
        words = json.load(f)
        words = [WordLoc(**word) for word in words]

    # Process each query
    for query in request.queries:
        # Find best match for the query in the PDF
        matched_words = find_best_match(query, words)
        if not matched_words:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Could not find text matching query: "{query}"',
            )

        # Highlight the matched words in the PDF
        highlight_words_in_pdf(paper_id, matched_words, rgb_color)

    # Also highlight requested figures
    highlight_figures_in_pdf(
        paper_id,
        request.image_ids,
        request.table_ids,
        rgb_color,
    )


@app.post('/papers/{paper_id}/grobid-annotation', response_model=list[GrobidAnnotation])
def grobid_annotation(
    paper_id: int,
    request: HighlightRequest,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> list[GrobidAnnotation]:
    """
    Find best text matches and return their coordinates in GROBID format.

    Args:
        paper_id: The ID of the paper
        request: JSON body with queries (list) and color fields

    Returns:
        List of GROBID-style coordinates for all matched text
    """
    # Verify paper exists
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    # Parse and validate color
    try:
        rgb_color = parse_hex_color(request.color)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Return early if no highlightable evidence (e.g., all from supplements)
    if not request.queries and not request.image_ids and not request.table_ids:
        return []

    # Load words from JSON file
    words_file = pdf_words_json_path(paper_id)
    with open(words_file, 'r') as f:
        words = json.load(f)
        words = [WordLoc(**word) for word in words]

    # Find matches for all queries and collect annotations
    all_annotations: list[GrobidAnnotation] = []
    for query in request.queries:
        matched_words = find_best_match(query, words)
        if not matched_words:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Could not find text matching query: "{query}"',
            )

        # Convert to GROBID annotations
        annotations = words_to_grobid_annotations(
            paper_id,
            matched_words,
            rgb_color,
        )
        all_annotations.extend(annotations)

    all_annotations.extend(
        figures_to_grobid_annotations(
            paper_id,
            request.image_ids,
            request.table_ids,
            rgb_color,
        )
    )

    return all_annotations


@app.post('/papers/{paper_id}/clear-highlights', status_code=status.HTTP_204_NO_CONTENT)
def clear_highlights(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: UserDB = Depends(get_current_user),
) -> None:
    """
    Clear all highlights from a paper by replacing the highlighted PDF with the raw PDF.

    Args:
        paper_id: The ID of the paper
    """
    # Verify paper exists
    paper_db = session.get(PaperDB, paper_id)
    if not paper_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Paper not found'
        )

    raw_path = pdf_raw_path(paper_id)
    highlighted_path = pdf_highlighted_path(paper_id)

    with open(raw_path, 'rb') as f:
        content = f.read()
    with open(highlighted_path, 'wb') as f:
        f.write(content)
