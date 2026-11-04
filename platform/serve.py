"""Run exactly one backend/worker process; never use uvicorn --reload or --workers."""
import argparse
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import uvicorn
from backend.app import create_app
from backend.config import Settings


def _setup_logging(data_dir: Path, verbose: bool):
    """Single initializer — import-time calls from submodules all funnel here."""
    if logging.getLogger().handlers:
        return
    level = logging.DEBUG if verbose else logging.INFO
    fmt = '%(asctime)s %(levelname)-5s %(name)s: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    root = logging.getLogger()
    root.setLevel(level)
    # Stderr stays (piped or redirected by process supervisor in prod).
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(stderr)
    # Rotating file keeps recent history for incident triage.
    try:
        log_path = Path(data_dir) / 'platform.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8',
        )
        file_handler.setFormatter(logging.Formatter(fmt, datefmt))
        root.addHandler(file_handler)
    except OSError as exc:
        logging.warning('Could not open log file %s: %s', data_dir / 'platform.log', exc)
    # Silence noisy third-party loggers.
    for name in ('uvicorn.access', 'starlette.middleware.cors', 'PIL.Image'):
        logging.getLogger(name).setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--external-engine', action='store_true', help='Do not start/restart an owned ComfyUI child')
    parser.add_argument('--engine-url', default=os.getenv('MOSS_ENGINE_URL', 'http://127.0.0.1:8188'),
                        help='ComfyUI endpoint, e.g. http://127.0.0.1:8188 or a remote GPU host')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    settings = Settings(engine_url=args.engine_url, engine_autostart=not args.external_engine,
                        bootstrap_default_admin=os.getenv('MOSS_BOOTSTRAP_ADMIN', '1') == '1',
                        secure_cookie=os.getenv('MOSS_SECURE_COOKIE', '0') == '1')
    _setup_logging(settings.data_dir, args.verbose)
    log = logging.getLogger('serve')
    log.info('Starting MOSS Studio backend on %s:%s (engine=%s, worker_enabled=%s)',
             args.host, args.port, settings.engine_url, settings.worker_enabled)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, workers=1, proxy_headers=False,
                log_config=None, access_log=False)  # we own request logging


if __name__ == '__main__':
    main()
