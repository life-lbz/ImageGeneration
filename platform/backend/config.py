from dataclasses import dataclass, field
from pathlib import Path
import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, '') or default)
    except ValueError:
        return default


@dataclass
class Settings:
    root: Path = Path(__file__).resolve().parents[2]
    data_dir: Path | None = None
    # 引擎地址：本机为 http://127.0.0.1:8188；autoDL 远程时可指向隧道或公网地址
    engine_url: str = field(default_factory=lambda: os.getenv('MOSS_ENGINE_URL', 'http://127.0.0.1:8188'))
    # 自启推理进程时使用的解释器；留空则使用当前运行后端的解释器
    inference_python: str | None = field(default_factory=lambda: os.getenv('MOSS_INFERENCE_PYTHON') or None)
    worker_enabled: bool = True
    engine_autostart: bool = False
    bootstrap_default_admin: bool = False
    task_timeout: int = 1800
    engine_timeout: int = field(default_factory=lambda: _env_int('MOSS_ENGINE_TIMEOUT', 30))
    session_seconds: int = 43200
    secure_cookie: bool = False
    allowed_origins: tuple = ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000')

    def __post_init__(self):
        self.root = Path(self.root).resolve()
        self.data_dir = Path(self.data_dir or os.getenv('MOSS_DATA_DIR') or self.root / 'platform/data').resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / 'images').mkdir(exist_ok=True)
        self.db_path = self.data_dir / 'moss.sqlite3'
