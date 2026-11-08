from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

_connect_args = (
    {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(config.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns():
    """轻量补列：create_all 不会给已有表加字段，这里做幂等的 ALTER。

    Alembic 属暂缓项，表结构稳定后再引入正式迁移。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    def _add(table: str, column: str, ddl: str) -> None:
        if table not in tables:
            return
        cols = {c["name"] for c in inspector.get_columns(table)}
        if column not in cols:
            with engine.begin() as conn:
                conn.execute(text(ddl))

    _add("projects", "cover_asset_id", "ALTER TABLE projects ADD COLUMN cover_asset_id VARCHAR(36)")
    _add("projects", "background_color", "ALTER TABLE projects ADD COLUMN background_color VARCHAR(7) NOT NULL DEFAULT '#FFFFFF'")
    _add("tasks", "params", "ALTER TABLE tasks ADD COLUMN params JSON DEFAULT '{}'")
    _add("sale_scripts", "style", "ALTER TABLE sale_scripts ADD COLUMN style VARCHAR(16) DEFAULT '种草式'")
    _add("sale_scripts", "platform", "ALTER TABLE sale_scripts ADD COLUMN platform VARCHAR(16) DEFAULT '其他'")
    _add("sale_shots", "video_asset_id", "ALTER TABLE sale_shots ADD COLUMN video_asset_id VARCHAR(36)")
    _add("sale_scripts", "product_asset_id", "ALTER TABLE sale_scripts ADD COLUMN product_asset_id VARCHAR(36)")
    _add("sale_scripts", "final_asset_id", "ALTER TABLE sale_scripts ADD COLUMN final_asset_id VARCHAR(36)")


def init_db():
    from . import models  # noqa: F401  确保表模型已注册

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
