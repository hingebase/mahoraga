# Copyright 2025-2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__all__ = ["Config", "run"]

import asyncio
import functools
import io
import logging
import os
import pathlib
import sys
from typing import TYPE_CHECKING, cast, override

import fastapi.staticfiles
import hishel._core._spec  # pyright: ignore[reportMissingTypeStubs]
import rich.console
import uvicorn.logging

from mahoraga import _conda, _core, _preload

from . import _app

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import ProcessPoolExecutor
    from logging.config import (
        _DictConfigArgs,  # pyright: ignore[reportPrivateUsage]
    )

    from starlette.types import ASGIApp

try:
    import granian.constants
    import granian.http
    import granian.log
    import granian.server.embed
    import granian.utils.proxies
except ImportError:
    granian = None


def run() -> None:
    cfg = Config()
    log_level = cfg.log.levelno()
    log_config: _DictConfigArgs = {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[{asctime}] {levelname:8} {message}",
                "datefmt": "%Y-%m-%d %X",
                "style": "{",
            },
        },
        "filters": {
            "granian_access": {
                "()": "mahoraga._preload.GranianAccess",
            },
            "hishel_core_spec": {
                "()": "mahoraga._preload.HishelCoreSpec",
            },
            "hishel_integrations_clients": {
                "()": "mahoraga._preload.HishelIntegrationsClients",
            },
            "uvicorn_access": {
                "()": "mahoraga._preload.UvicornAccess",
            },
            "uvicorn_error": {
                "()": "mahoraga._preload.UvicornError",
                "level": log_level,
            },
        },
        "handlers": {
            "console_legacy": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "console_rich": {
                "class": "rich.logging.RichHandler",
                "log_time_format": "[%Y-%m-%d %X]",
            },
            "filesystem": {
                "class": "mahoraga._preload.RotatingFileHandler",
                "formatter": "default",
                "filename": "log/mahoraga.log",
                "maxBytes": 20000 * 81,  # lines * chars
                "backupCount": 10,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "granian.access": {
                "filters": ["granian_access"],
            },
            "hishel": {
                "level": "DEBUG",
            },
            "hishel.core.spec": {
                "filters": ["hishel_core_spec"],
            },
            "hishel.integrations.clients": {
                "filters": ["hishel_integrations_clients"],
            },
            "uvicorn.access": {
                "level": "INFO",
                "filters": ["uvicorn_access"],
            },
            "uvicorn.error": {
                "level": uvicorn.logging.TRACE_LOG_LEVEL,
                "filters": ["uvicorn_error"],
            },
        },
        "root": {
            "handlers": _root_handlers(),
            "level": log_level,
        },
        "disable_existing_loggers": False,
    }
    if cfg.server.is_uvicorn() or not cfg.log.access:
        del log_config["loggers"]["granian.access"]
    if cfg.server.is_granian() or not cfg.log.access:
        del log_config["loggers"]["uvicorn.access"]
    if cfg.server.is_granian() or log_level > logging.INFO:
        del log_config["loggers"]["uvicorn.error"]
    cfg.run(cast("dict[str, object]", log_config))


class Config(_core.Config, toml_file="mahoraga.toml"):
    @override
    def model_post_init(self, context: object) -> None:
        self._started = False

    @override
    def on_startup(self, executor: ProcessPoolExecutor) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(self._on_startup, executor, loop)

    def run(self, log_config: dict[str, object]) -> None:
        static_files = fastapi.staticfiles.StaticFiles(
            packages=[("mahoraga", "_static")],
        )
        if self.server.is_uvicorn():
            cfg = uvicorn.Config(
                app=functools.partial(_app.make_app, self, static_files),
                host=str(self.server.host),
                port=self.server.port,
                loop="none",
                log_config=log_config,
                access_log=self.log.access,
                forwarded_allow_ips="127.0.0.1",
                limit_concurrency=self.server.limit_concurrency,
                backlog=self.server.backlog,
                timeout_keep_alive=self.server.keep_alive,
                timeout_graceful_shutdown=self.server.workers_kill_timeout(),
                factory=True,
            )
            server = uvicorn.Server(cfg)
        elif not granian:
            message = (
                "server.implementation == 'granian' in mahoraga.toml, "
                "but granian was not installed"
            )
            raise ValueError(message)
        else:
            middleware = cast(
                "Callable[[ASGIApp], ASGIApp]",
                granian.utils.proxies.wrap_asgi_with_proxy_headers,
            )
            server = granian.server.embed.Server(
                target=lambda: middleware(_app.make_app(self)),
                address=str(self.server.host),
                port=self.server.port,
                interface=granian.constants.Interfaces.ASGI,
                runtime_threads=os.process_cpu_count() or 1,
                http=granian.constants.HTTPModes.http1,
                backlog=self.server.backlog,
                backpressure=self.server.limit_concurrency,
                http1_settings=granian.http.HTTP1Settings(
                    header_read_timeout=60000,
                ),
                log_level=granian.log.LogLevels.notset,
                log_dictconfig=log_config,
                log_access=self.log.access,
                log_access_format=(
                    '%(addr)s - "%(method)s %(path)s %(protocol)s" %(status)d'
                ),
                factory=True,
                static_path_mount=pathlib.Path(static_files.all_directories[0]),
            )
            server.workers_kill_timeout = self.server.workers_kill_timeout()
        _preload.configure_logging_extra(self.log.levelno())
        try:
            asyncio.run(
                server.serve(),
                debug=self.log.level == "debug",
                loop_factory=self.loop_factory,
            )
        except KeyboardInterrupt:
            pass
        except SystemExit:
            if getattr(server, "started", self._started):
                raise
            sys.exit(3)
        except BaseException as e:
            logging.getLogger("mahoraga").critical("ERROR", exc_info=e)
            started = getattr(server, "started", self._started)
            raise SystemExit(started) from e

    def _on_startup(
        self,
        executor: ProcessPoolExecutor,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._started = True
        if any(self.shard.values()):
            _conda.split_repo(loop, self, executor)


def _root_handlers() -> list[str]:
    handlers = ["filesystem"]
    if isinstance(sys.stdout, io.TextIOBase) and sys.stdout.isatty():
        if rich.console.detect_legacy_windows():
            handlers.append("console_legacy")
        else:
            handlers.append("console_rich")
    return handlers


hishel._core._spec.get_heuristic_freshness = lambda response: 600  # noqa: ARG005, SLF001  # ty: ignore[invalid-assignment]
