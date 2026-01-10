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

__all__ = ["run"]

import asyncio
import functools
import io
import logging
import sys
from typing import TYPE_CHECKING, cast

import hishel._core._spec  # pyright: ignore[reportMissingTypeStubs]
import rich.console
import uvicorn.logging

from mahoraga import _core, _preload

from . import _app

if TYPE_CHECKING:
    from logging.config import (
        _DictConfigArgs,  # pyright: ignore[reportPrivateUsage]
    )


def run() -> None:
    cfg = _core.Config()
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
    if not cfg.log.access:
        del log_config["loggers"]["uvicorn.access"]
    if log_level > logging.INFO:
        del log_config["loggers"]["uvicorn.error"]

    server_config = uvicorn.Config(
        app=functools.partial(_app.make_app, cfg),
        host=str(cfg.server.host),
        port=cfg.server.port,
        loop="none",
        log_config=cast("dict[str, object]", log_config),
        access_log=cfg.log.access,
        forwarded_allow_ips="127.0.0.1",
        limit_concurrency=cfg.server.limit_concurrency,
        backlog=cfg.server.backlog,
        timeout_keep_alive=cfg.server.keep_alive,
        timeout_graceful_shutdown=cfg.server.timeout_graceful_shutdown or None,
        factory=True,
    )
    _preload.configure_logging_extra(log_level)
    server = uvicorn.Server(server_config)
    try:
        asyncio.run(
            server.serve(),
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
        logging.getLogger("mahoraga").critical("ERROR", exc_info=e)
        raise SystemExit(server.started or 3) from e


def _root_handlers() -> list[str]:
    handlers = ["filesystem"]
    if isinstance(sys.stdout, io.TextIOBase) and sys.stdout.isatty():
        if rich.console.detect_legacy_windows():
            handlers.append("console_legacy")
        else:
            handlers.append("console_rich")
    return handlers


hishel._core._spec.get_heuristic_freshness = lambda response: 600  # noqa: ARG005, SLF001  # ty: ignore[invalid-assignment]
