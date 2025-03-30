# Copyright 2025 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__all__ = ["run"]

import asyncio
import atexit
import collections
import concurrent.futures
import contextlib
import io
import logging.config
import logging.handlers
import multiprocessing as mp
import pathlib
import sys
import warnings
from typing import Any, override

import httpx
import pooch  # pyright: ignore[reportMissingTypeStubs]
import rich.logging
import uvicorn.config

from mahoraga import __version__, _conda, _core

from . import _app


def run() -> None:
    cfg = _core.Config()
    log_level = uvicorn.config.LOG_LEVELS[cfg.log.level]
    server_config = _ServerConfig(
        app=_app.make_app,
        host=str(cfg.server.host),
        port=cfg.server.port,
        loop="none",
        log_config={
            "version": 1,
            "handlers": {
                "default": {
                    "class": "logging.handlers.QueueHandler",
                    "queue": mp.get_context("spawn").Queue(),
                },
            },
            "root": {
                "handlers": ["default"],
                "level": log_level,
            },
            "disable_existing_loggers": False,
        },
        log_level=log_level,
        access_log=cfg.log.access,
        timeout_keep_alive=cfg.server.keep_alive,
        timeout_notify=3600,
        callback_notify=_conda.split_repo,
        factory=True,
    )
    server = uvicorn.Server(server_config)
    try:
        asyncio.run(
            _main(cfg, server),
            debug=cfg.log.level == "debug",
            loop_factory=cfg.loop_factory,
        )
    except KeyboardInterrupt:
        pass
    except SystemExit:
        if server.started:
            raise
        sys.exit(3)
    except BaseException as e:
        _logger.critical("ERROR", exc_info=e)
        raise SystemExit(server.started or 3) from e


async def _event_hook(request: httpx.Request) -> None:  # noqa: RUF029
    async def trace(event_name: str, _info: dict[str, Any]) -> None:  # noqa: RUF029
        _logger.debug("%s: %s", event_name, request.url)
    request.extensions["trace"] = trace


def _initializer(cfg: dict[str, Any]) -> None:
    logging.config.dictConfig(cfg)
    logging.captureWarnings(capture=True)
    pooch.utils.LOGGER = logging.getLogger("pooch")


async def _main(
    cfg: _core.Config,
    server: uvicorn.Server,
) -> None:
    if cfg.log.level == "debug":
        event_hooks = {"request": [_event_hook]}
    else:
        event_hooks = None

    log_config = server.config.log_config
    if not isinstance(log_config, dict):
        _core.unreachable()

    async with contextlib.AsyncExitStack() as stack:
        _core.context.set({
            "config": cfg,
            "httpx_client": await stack.enter_async_context(
                _core.AsyncClient(
                    headers={"User-Agent": f"mahoraga/{__version__}"},
                    timeout=httpx.Timeout(15, read=60, write=60),
                    follow_redirects=False,
                    limits=httpx.Limits(keepalive_expiry=cfg.server.keep_alive),
                    event_hooks=event_hooks,
                ),
            ),
            "locks": _core.WeakValueDictionary(),
            "process_pool": stack.enter_context(
                concurrent.futures.ProcessPoolExecutor(
                    initializer=_initializer,
                    initargs=(log_config,),
                    max_tasks_per_child=1000,
                ),
            ),
            "statistics_concurrent_requests": collections.Counter(),
        })
        await server.serve()


class _RotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self) -> io.TextIOWrapper:
        if self.mode != "a":
            _core.unreachable()
        return pathlib.Path(self.baseFilename).open(
            mode="a",
            encoding=self.encoding,
            errors=self.errors,
            newline="",
        )


class _ServerConfig(uvicorn.Config):
    @override
    def configure_logging(self) -> None:
        super().configure_logging()
        if self.access_log:
            logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        if self.log_level == logging.DEBUG:
            warnings.simplefilter("always", ResourceWarning)
        logging.captureWarnings(capture=True)
        pooch.utils.LOGGER = logging.getLogger("pooch")

        root = logging.getLogger()
        [old] = root.handlers
        if not isinstance(old, logging.handlers.QueueHandler):
            _core.unreachable()
        root.removeHandler(old)

        log_dir = pathlib.Path("log")
        log_dir.mkdir(exist_ok=True)
        log_dir = log_dir.resolve(strict=True)
        new = _RotatingFileHandler(
            log_dir / "mahoraga.log",
            maxBytes=20000 * 81,  # lines * chars
            backupCount=10,
            encoding="utf-8",
        )
        fmt = logging.Formatter(
            "[{asctime}] {levelname:8} {message}",
            datefmt="%Y-%m-%d %X",
            style="{",
        )
        new.setFormatter(fmt)
        root.addHandler(new)

        if isinstance(sys.stdout, io.TextIOBase) and sys.stdout.isatty():
            if rich.console.detect_legacy_windows():
                new = logging.StreamHandler(sys.stdout)
                new.setFormatter(fmt)
            else:
                new = rich.logging.RichHandler(log_time_format="[%Y-%m-%d %X]")
            root.addHandler(new)

        listen = logging.handlers.QueueListener(old.queue, *root.handlers)
        listen.start()
        atexit.register(listen.stop)


_logger = logging.getLogger("mahoraga")
