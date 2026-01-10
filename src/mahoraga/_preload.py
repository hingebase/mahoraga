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

__all__ = ["HTTPHandler", "configure_logging_extra"]

import copy
import dataclasses
import http
import inspect
import logging.handlers
import pathlib
import types
import warnings
from typing import TYPE_CHECKING, Any, cast, override

import hishel
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]

from . import _core

if TYPE_CHECKING:
    from io import TextIOWrapper


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


class UvicornAccess:
    @staticmethod
    def filter(record: logging.LogRecord) -> bool:
        match record.args:
            case [
                _,
                _,
                str() as path_with_query_string,
                _,
                int() as status_code,
            ] if (
                path_with_query_string.startswith("/log?")
                and status_code == http.HTTPStatus.OK
            ):
                return False
            case _:
                return True


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
