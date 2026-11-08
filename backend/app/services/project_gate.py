"""单实例部署的跨进程项目锁；进程退出时由操作系统释放。"""
from contextlib import contextmanager
import fcntl
import hashlib
from .. import config


@contextmanager
def project_gate(project_id: str):
    directory = config.DATA_DIR / ".project-locks"
    directory.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(project_id.encode()).hexdigest()
    with (directory / name).open("a") as handle:
        acquired = False
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
            yield acquired
        finally:
            if acquired:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
