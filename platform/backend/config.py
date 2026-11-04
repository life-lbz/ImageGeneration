from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, '') or default)
    except ValueError:
        return default


def _validate_engine_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/'):
        raise ValueError(f'MOSS_ENGINE_URL 必须是 http(s)://<host>:<port> 的裸 origin（无账号密码、无路径），实际收到: {url}')
    return url.rstrip('/')


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
    # 登录限流：窗口秒数 / 最大尝试次数
    login_rate_window: int = field(default_factory=lambda: _env_int('MOSS_LOGIN_RATE_WINDOW', 600))
    login_rate_max: int = field(default_factory=lambda: _env_int('MOSS_LOGIN_RATE_MAX', 20))
    allowed_origins: tuple = ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000')

    def __post_init__(self):
        self.root = Path(self.root).resolve()
        self.engine_url = _validate_engine_url(self.engine_url)
        if self.engine_timeout <= 0:
            raise ValueError(f'MOSS_ENGINE_TIMEOUT 必须为正整数，实际收到: {self.engine_timeout}')
        if self.task_timeout <= 0:
            raise ValueError(f'task_timeout 必须为正整数，实际收到: {self.task_timeout}')
        if self.session_seconds < 60:
            raise ValueError(f'session_seconds 不能小于 60，实际收到: {self.session_seconds}')
        if self.login_rate_window <= 0 or self.login_rate_max <= 0:
            raise ValueError('MOSS_LOGIN_RATE_WINDOW / MOSS_LOGIN_RATE_MAX 必须为正整数')
        origins_env = os.getenv('MOSS_ALLOWED_ORIGINS')
        if origins_env:
            self.allowed_origins = tuple(x.strip() for x in origins_env.split(',') if x.strip())
        self.data_dir = Path(self.data_dir or os.getenv('MOSS_DATA_DIR') or self.root / 'platform/data').resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / 'images').mkdir(exist_ok=True)
        self.db_path = self.data_dir / 'moss.sqlite3'
