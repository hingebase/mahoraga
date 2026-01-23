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

__all__ = ["configure_logging_extra"]

import copy
import dataclasses
import inspect
import logging.handlers
import pathlib
import types
import warnings
from typing import TYPE_CHECKING, Any, cast, override

import click
import hishel
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]
import pydantic
import tornado.web
import uvicorn.config

from . import _core

if TYPE_CHECKING:
    from io import TextIOWrapper

    from distributed import Worker
    from tornado.routing import (
        _RuleList,  # pyright: ignore[reportPrivateUsage]
    )


# https://github.com/dask/distributed/issues/8136
class DistributedScheduler:
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args != ("dashboard", "http://127.0.0.1:8787/status"):
            return True
        logging.getLogger("distributed.scheduler").removeFilter(self)
        return False


class DistributedWorker:
    def filter(self, rec: logging.LogRecord) -> bool:
        if rec.msg.startswith("         dashboard at:            127.0.0.1:"):
            logging.getLogger("distributed.worker").removeFilter(self)
            return False
        return True


class GranianAccess:
    @staticmethod
    def filter(record: logging.LogRecord) -> bool | logging.LogRecord:
        match record.args:
            case {
                "path": path,
                "query_string": bytes() as query_string,
            } as args if query_string:
                path = f"{path}?{query_string.decode('ascii')}"
                record = copy.copy(record)
                record.args = dict(args, path=path)
                return record
            case _:
                return True


# Cannot inherit from `logging.handlers.QueueHandler`,
# otherwise `logging.config.dictConfig` will fail
class HTTPHandler(logging.handlers.HTTPHandler):
    @override
    def mapLogRecord(self, record: logging.LogRecord) -> dict[str, Any]:
        return logging.handlers.QueueHandler.prepare(
            cast("logging.handlers.QueueHandler", self),
            record,
        ).__dict__


class HishelCoreSpec:
    @staticmethod
    def filter(record: logging.LogRecord) -> bool:
        return record.msg != "Storing response in cache"


class HishelIntegrationsClients:
    @staticmethod
    def filter(record: logging.LogRecord) -> bool | logging.LogRecord:
        message: str = record.msg
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
                    types.FrameType(
                        f_locals={"request": hishel.Request(url=url)},
                    ),
                    record.pathname,
                    record.lineno,
                    record.funcName,
                    *_,
                ]:
                    record = copy.copy(record)
                    record.msg = "%s: %s"
                    record.args = message[16:], url
                    return record
                case _:
                    pass
        return _core.unreachable()


class RotatingFileHandler(logging.handlers.RotatingFileHandler):
    @override
    def _open(self) -> TextIOWrapper:
        if self.mode != "a":
            _core.unreachable()
        filename = pathlib.Path(self.baseFilename)
        filename.parent.mkdir(exist_ok=True)
        return filename.open(
            mode="a",
            encoding=self.encoding,
            errors=self.errors,
            newline="",
        )


@dataclasses.dataclass
class UvicornError:
    level: int

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.level or record.msg.endswith((
            "HTTP connection made",
            "HTTP connection lost",
        ))


def configure_logging_extra(log_level: int) -> None:
    logging.captureWarnings(capture=True)
    pooch.utils.LOGGER = logging.getLogger("pooch")
    if log_level <= logging.DEBUG:
        warnings.simplefilter("always", ResourceWarning)


@click.command(
    params=[p for p in uvicorn.main.params if p.name == "log_level"],
)
def dask_setup(_: Worker, log_level: str) -> None:
    configure_logging_extra(uvicorn.config.LOG_LEVELS[log_level])


class _LogRecord(pydantic.BaseModel, logging.LogRecord):
    args: Any
    asctime: str = ""
    created: float
    exc_info: Any
    exc_text: str | None
    filename: str
    funcName: str  # noqa: N815
    levelname: str
    levelno: int
    lineno: int
    module: str
    msecs: float
    message: str
    msg: str
    name: str
    pathname: str
    process: int | None
    processName: str | None  # noqa: N815
    relativeCreated: float  # noqa: N815
    stack_info: str | None
    thread: int | None
    threadName: str | None  # noqa: N815
    taskName: str | None  # noqa: N815

    @pydantic.field_validator(
        "args",
        "exc_info",
        "exc_text",
        "process",
        "processName",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        mode="before",
    )
    @classmethod
    def parse_none_str(cls, value: str) -> str | None:
        return None if value == "None" else value


class _WorkerLogHandler(tornado.web.RequestHandler):
    def get(self) -> None:
        record = _LogRecord.model_validate({
            name: self.get_query_argument(name)
            for name in _LogRecord.__pydantic_fields__
            if name != "asctime"
        })
        for handler in _root.handlers:
            handler.handle(record)


routes: _RuleList = [("/log", _WorkerLogHandler, {})]
_root = logging.getLogger()
