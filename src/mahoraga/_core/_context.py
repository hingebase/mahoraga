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

__all__ = [
    "AsyncClient",
    "Context",
    "Statistics",
    "WeakValueDictionary",
    "schedule_exit",
]

import asyncio
import collections
import concurrent.futures
import contextlib
import contextvars
import time
import weakref
from collections.abc import AsyncGenerator
from typing import Any, TypedDict, override

import anyio
import httpx
import pydantic_settings

from mahoraga import _core


class AsyncClient(httpx.AsyncClient):
    @override
    @contextlib.asynccontextmanager
    async def stream(
        self,
        method: str,
        url: httpx.URL | str,
        **kwargs: Any,
    ) -> AsyncGenerator[httpx.Response, None]:
        url = httpx.URL(url)
        h = url.host
        if h.endswith(("github.com", "prefix.dev", "pypi.org")):
            kwargs["follow_redirects"] = True
        cm = super().stream(method, url, **kwargs)
        ctx = _core.context.get()
        concurrent_requests = ctx["statistics_concurrent_requests"]
        concurrent_requests[h] += 1
        async with contextlib.AsyncExitStack() as stack:
            tic = time.monotonic()
            try:
                yield await stack.enter_async_context(cm)
            finally:
                toc = time.monotonic()
                if seconds := round(toc - tic):
                    concurrent_requests[h] -= 1
                    schedule_exit(stack)
                    async with ctx["locks"]["statistics.json"]:
                        s = Statistics()
                        s.total_seconds[h] += seconds
                        await _json.write_text(
                            s.model_dump_json(exclude=_exclude),
                            encoding="utf-8",
                        )


def schedule_exit(stack: contextlib.AsyncExitStack) -> None:
    task = asyncio.create_task(stack.pop_all().aclose())
    stack.push_async_callback(lambda: task)


class Statistics(pydantic_settings.BaseSettings, json_file_encoding="utf-8"):
    backup_servers: set[str] = set()
    concurrent_requests: collections.Counter[str] = collections.Counter()
    total_seconds: collections.Counter[str] = collections.Counter()

    def key(self, url: str) -> tuple[bool, int, int]:
        h = httpx.URL(url).host
        return (
            h in self.backup_servers,
            self.concurrent_requests[h],
            self.total_seconds[h],
        )

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        ctx = _core.context.get()
        json_settings = pydantic_settings.JsonConfigSettingsSource(
            settings_cls, "statistics.json")
        json_settings.init_kwargs.update(  # pyright: ignore[reportUnknownMemberType]
            backup_servers=ctx["config"].upstream.backup,
            concurrent_requests=ctx["statistics_concurrent_requests"],
        )
        return (json_settings,)


class WeakValueDictionary(weakref.WeakValueDictionary[str, asyncio.Lock]):
    @override
    def __getitem__(self, key: str) -> asyncio.Lock:
        try:
            return super().__getitem__(key)
        except KeyError:
            self[key] = value = asyncio.Lock()
            return value


class _Context(TypedDict):
    config: _core.Config
    httpx_client: AsyncClient
    locks: WeakValueDictionary
    process_pool: concurrent.futures.ProcessPoolExecutor
    statistics_concurrent_requests: collections.Counter[str]


Context = contextvars.ContextVar[_Context]
_exclude = {"backup_servers", "concurrent_requests"}
_json = anyio.Path("statistics.json")
