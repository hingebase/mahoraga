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
import collections
import concurrent.futures
import contextlib
import inspect
import io
import logging.config
import logging.handlers
import multiprocessing as mp
import pathlib
import sys
import types
import warnings
from typing import Any, cast, override

import anysqlite
import hishel._core._spec  # pyright: ignore[reportMissingTypeStubs]
import httpx
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]
import rich.console
import rich.logging
import uvicorn.config
import uvicorn.logging

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
        limit_concurrency=cfg.server.limit_concurrency,
        backlog=cfg.server.backlog,
        timeout_keep_alive=cfg.server.keep_alive,
        timeout_graceful_shutdown=cfg.server.timeout_graceful_shutdown or None,
        timeout_notify=3600,
        callback_notify=_conda.split_repo,
        factory=True,
    )
    server = uvicorn.Server(server_config)
    with server_config.listen:
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


def _initializer(cfg: dict[str, Any]) -> None:
    logging.config.dictConfig(cfg)
    logging.captureWarnings(capture=True)
    pooch.utils.LOGGER = logging.getLogger("pooch")


def _log_filter(rec: logging.LogRecord) -> bool:
    message: str = rec.msg
    if not message.startswith("Handling state: "):
        return True
    if (
        message == "Handling state: IdleClient"
        or (
            message != "Handling state: FromCache"
            and _core.cache_action.get() != "cache-or-fetch"
        )
    ):
        return False
    for frame in inspect.stack(0):
        match frame:
            case [
                types.FrameType(f_locals={"request": hishel.Request(url=url)}),
                rec.pathname,
                rec.lineno,
                rec.funcName,
                *_,
            ]:
                _logger.info("%s: %s", message[16:], url)
                return False
            case _:
                pass
    return _core.unreachable()


async def _main(
    cfg: _core.Config,
    server: uvicorn.Server,
) -> None:
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
                    limits=httpx.Limits(
                        max_connections=cfg.server.limit_concurrency,
                        keepalive_expiry=cfg.server.keep_alive,
                    ),
                    storage=hishel.AsyncSqliteStorage(
                        connection=await anysqlite.connect(":memory:"),
                        default_ttl=600.,
                    ),
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
        logging.getLogger("hishel").setLevel(logging.DEBUG)
        logging.getLogger("hishel.core.spec").addFilter(
            lambda rec: rec.msg != "Storing response in cache",
        )
        logging.getLogger("hishel.integrations.clients").addFilter(_log_filter)
        if self.access_log:
            logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        level = cast("int", self.log_level)
        if level <= logging.INFO:
            logger = logging.getLogger("uvicorn.error")
            logger.setLevel(uvicorn.logging.TRACE_LOG_LEVEL)
            logger.addFilter(
                lambda rec: rec.levelno >= level or rec.msg.endswith((
                    "HTTP connection made",
                    "HTTP connection lost",
                )),
            )
            if level <= logging.DEBUG:
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

        self.listen = logging.handlers.QueueListener(old.queue, *root.handlers)


hishel._core._spec.get_heuristic_freshness = lambda response: 600  # noqa: ARG005, SLF001  # ty: ignore[invalid-assignment]
_logger = logging.getLogger("mahoraga")
