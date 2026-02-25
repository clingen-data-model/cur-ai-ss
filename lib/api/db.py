from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from lib.evagg.utils.environment import env

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = (
    None  # a Session factory that is local to this application/process
)


def get_engine() -> Engine:
    """Return a singleton Engine."""
    global _engine
    if _engine is None:
        Path(env.sqlite_dir).mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f'sqlite:///{env.sqlite_dir}/app.db',
            connect_args={'check_same_thread': False, 'timeout': 30},
            pool_pre_ping=True,
        )
        event.listen(_engine, 'connect', _sqlite_set_pragmas)
    return _engine


def _sqlite_set_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA foreign_keys=ON')
    finally:
        cursor.close()


def get_sessionmaker() -> sessionmaker:
    """Return a singleton SQLAlchemy sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _session_factory


# Note: A generator, and not a context manager is required here.
# Adding @contextmanager here, for use in non-FastAPI code, breaks the path functions.
def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session. Use as a context manager with FastAPI dependencies."""
    session_local = get_sessionmaker()
    session: Session = session_local()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session_local = get_sessionmaker()
    session: Session = session_local()
    try:
        yield session
        session.commit()  # commit after normal exit
    except:
        session.rollback()
        raise
    finally:
        session.close()
