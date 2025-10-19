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
    "cache_action",
    "cached_or_locked",
    "schedule_exit",
]

import asyncio
import collections
import contextlib
import contextvars
import time
import weakref
from typing import TYPE_CHECKING, Any, TypedDict, overload, override

import aiohttp
import anyio
import cyares.aiohttp
import hishel
import httpx
import httpx_aiohttp
import pydantic_settings
from httpx._config import DEFAULT_LIMITS  # noqa: PLC2701
from rattler.networking.fetch_repo_data import CacheAction

from mahoraga import _core

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable
    from concurrent.futures import ProcessPoolExecutor
    from ssl import SSLContext

    from _typeshed import StrPath
    from httpx._types import CertTypes


class _HttpxAiohttpClient(httpx.AsyncClient):
    @override
    def _init_transport(
        self,
        verify: SSLContext | str | bool = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits = DEFAULT_LIMITS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> httpx.AsyncBaseTransport:
        if transport is not None:
            return transport
        return _AiohttpTransport(
            verify=verify,
            cert=cert,
            trust_env=trust_env,
            http1=http1,
            http2=http2,
            limits=limits,
        )


class AsyncClient(hishel.AsyncCacheClient, _HttpxAiohttpClient):
    @override
    def _transport_for_url(self, url: httpx.URL) -> httpx.AsyncBaseTransport:
        t = super()._transport_for_url(url)
        if isinstance(t, hishel.AsyncCacheTransport):
            match cache_action.get():
                case "no-cache":
                    return t._transport  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                case "force-cache-only" | "use-cache-only":
                    return hishel.AsyncCacheTransport(
                        _not_implemented, t._storage, t._controller)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                case "cache-or-fetch":
                    pass
        return t

    @override
    @contextlib.asynccontextmanager
    async def stream(
        self,
        method: str,
        url: httpx.URL | str,
        **kwargs: Any,
    ) -> AsyncGenerator[httpx.Response]:
        url = httpx.URL(url)
        h = url.host
        if h.endswith((
            "anaconda.org",
            "github.com",
            "prefix.dev",
            "pypi.org",
        )):
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
                concurrent_requests[h] -= 1
                if seconds := round(toc - tic):
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


@overload
def cached_or_locked(
    cache_location: StrPath,
    stack: None = ...,
) -> contextlib.AbstractAsyncContextManager[bool]: ...

@overload
async def cached_or_locked(
    cache_location: StrPath,
    stack: contextlib.AsyncExitStack,
) -> bool: ...


def cached_or_locked(
    cache_location: StrPath,
    stack: contextlib.AsyncExitStack | None = None,
) -> Awaitable[bool] | contextlib.AbstractAsyncContextManager[bool]:
    cm = _cached_or_locked(cache_location)
    return stack.enter_async_context(cm) if stack else cm


@contextlib.asynccontextmanager
async def _cached_or_locked(cache_location: StrPath) -> AsyncGenerator[bool]:
    ctx = _core.context.get()
    async with ctx["locks"][str(cache_location)]:
        if not await anyio.Path(cache_location).is_file():
            yield False
            return
    yield True


class _AiohttpTransport(httpx_aiohttp.AiohttpTransport):
    @override
    def get_client(self) -> aiohttp.ClientSession:
        if (
            callable(self.client)
            or isinstance(self.client, aiohttp.ClientSession)
            or self.uds
            or not self.limits.max_connections
        ):
            return super().get_client()
        connector = aiohttp.TCPConnector(
            limit=self.limits.max_connections,
            keepalive_timeout=self.limits.keepalive_expiry,
            ssl=self.ssl_context,
            local_addr=(self.local_address, 0) if self.local_address else None,
            resolver=cyares.aiohttp.CyAresResolver(
                loop=asyncio.get_running_loop(),
            ),
        )
        return aiohttp.ClientSession(connector=connector)


class _Context(TypedDict):
    config: _core.Config
    httpx_client: AsyncClient
    locks: WeakValueDictionary
    process_pool: ProcessPoolExecutor
    statistics_concurrent_requests: collections.Counter[str]


Context = contextvars.ContextVar[_Context]
cache_action = contextvars.ContextVar[CacheAction](
    "cache_action",
    default="no-cache",
)
_exclude = {"backup_servers", "concurrent_requests"}
_json = anyio.Path("statistics.json")
_not_implemented = httpx.AsyncBaseTransport()
