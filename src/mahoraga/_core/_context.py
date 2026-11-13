# Copyright 2025-2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

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
import dataclasses
import inspect
import logging
import time
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    TypedDict,
    Unpack,
    cast,
    overload,
    override,
)

import aiohttp.typedefs
import anyio
import cyares.aiohttp
import hishel.httpx2
import httpx2
import httpx_aiohttp.httpx2
import pydantic_settings
import yarl
from httpx2._config import DEFAULT_LIMITS  # ruff: ignore[import-private-name]

from mahoraga import _core

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable
    from ssl import SSLContext
    from uuid import UUID

    from _typeshed import StrPath, Unused
    from aiohttp.client import _RequestContextManager, _RequestOptions  # pyright: ignore[reportPrivateUsage]
    from distributed import Client, Future
    from httpx2._types import CertTypes
    from pooch_rattler import Downloader
    from rattler.networking.fetch_repo_data import CacheAction

_SUFFIXES = ("anaconda.org", "github.com", "prefix.dev", "pypi.org")


class AsyncClient(hishel.httpx2.AsyncCacheClient):
    @override
    def _init_transport(
        self,
        verify: SSLContext | str | bool = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx2.Limits = DEFAULT_LIMITS,
        transport: httpx2.AsyncBaseTransport | None = None,
        **kwargs: Unused,
    ) -> httpx2.AsyncBaseTransport:
        if transport is not None:
            return transport
        return _AsyncCacheTransport(
            next_transport=_AiohttpTransport(
                verify=verify,
                cert=cert,
                trust_env=trust_env,
                http1=http1,
                http2=http2,
                limits=limits,
            ),
            storage=self.storage,
            rfc=self.rfc,
        )

    @override
    def _transport_for_url(self, url: httpx2.URL) -> httpx2.AsyncBaseTransport:
        t = super()._transport_for_url(url)
        if isinstance(t, hishel.httpx2.AsyncCacheTransport):
            match cache_action.get():
                case "no-cache":
                    return t.next_transport
                case "force-cache-only" | "use-cache-only":
                    config = t.config
                    return _AsyncCacheTransport(
                        _not_implemented,
                        config.get("storage"),
                        config.get("rfc", False),
                    )
                case "cache-or-fetch":
                    pass
        return t

    @override
    @contextlib.asynccontextmanager
    async def stream(
        self,
        method: str,
        url: httpx2.URL | str,
        **kwargs: Any,
    ) -> AsyncGenerator[httpx2.Response]:
        url = httpx2.URL(url)
        h = url.host
        if h.endswith(_SUFFIXES):
            kwargs["follow_redirects"] = True
        cm = super().stream(method, url, **kwargs)
        ctx = _core.context.get()
        s = ctx["statistics"]
        concurrent_requests = s.concurrent_requests
        concurrent_requests[h] += 1
        async with contextlib.AsyncExitStack() as stack:
            tic = time.monotonic()
            try:
                yield await stack.enter_async_context(cm)
            finally:
                toc = time.monotonic()
                concurrent_requests[h] -= 1
                if seconds := round(toc - tic):
                    s.total_seconds[h] += seconds
                    schedule_exit(stack)
                    async with ctx["locks"]["statistics.json"]:
                        await _json.write_text(
                            s.model_dump_json(exclude=_exclude),
                            encoding="utf-8",
                        )


def schedule_exit(stack: contextlib.AsyncExitStack) -> None:
    task = asyncio.create_task(stack.pop_all().aclose())
    stack.push_async_callback(lambda: task)


class Statistics(pydantic_settings.BaseSettings, json_file_encoding="utf-8"):
    backup_servers: dict[str, int]
    concurrent_requests: collections.Counter[str] = collections.Counter()
    total_seconds: collections.Counter[str] = collections.Counter()

    def key(self, url: str) -> tuple[bool, int, int]:
        h = httpx2.URL(url).host
        concurrency = self.concurrent_requests[h]
        try:
            limit = self.backup_servers[h]
        except KeyError:
            backup = False
        else:
            backup = concurrency >= limit
        return backup, concurrency, self.total_seconds[h]

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        json_settings = pydantic_settings.JsonConfigSettingsSource(
            settings_cls, "statistics.json")
        return (init_settings, json_settings)


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


class _AiohttpTransport(httpx_aiohttp.httpx2.AiohttpTransport):
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
        if _logger.isEnabledFor(logging.INFO):
            trace_config = aiohttp.TraceConfig()
            trace_config.on_connection_create_start.append(
                lambda _session, _context, _params: _on_signal("Creating"),
            )
            trace_config.on_connection_reuseconn.append(
                lambda _session, _context, _params: _on_signal("Reusing"),
            )
            trace_configs = [trace_config]
        else:
            trace_configs = None
        return _ClientSession(
            connector=connector,
            trace_configs=trace_configs,
        )


class _ClientSession(aiohttp.ClientSession):
    @override
    def request(
        self,
        method: str,
        url: aiohttp.typedefs.StrOrURL,
        **kwargs: Unpack[_RequestOptions],
    ) -> _RequestContextManager:
        if cache_action.get() == "cache-or-fetch":
            url = yarl.URL(url)
            if (h := url.host) and h.endswith(_SUFFIXES):
                headers = cast("httpx2.Headers", kwargs.get("headers")).copy()
                del headers["Host"]  # Added by httpx2, bad for redirection
                kwargs.update(allow_redirects=True, headers=headers)
        return super().request(method, url, **kwargs)


async def _on_signal(verb: str) -> None:  # ruff: ignore[unused-async]
    if frame := inspect.currentframe():
        while frame := frame.f_back:
            match frame.f_locals:
                case {"req": aiohttp.ClientRequest(url=url)}:
                    _logger.info("%s TCP connection: %s", verb, url)
                    return
                case _:
                    pass
    _core.unreachable()


class _AsyncStorageProxy(hishel.AsyncBaseStorage):
    def __init__(
        self,
        storage: hishel.AsyncBaseStorage,
        url: httpx2.URL,
    ) -> None:
        super().__init__(
            default_ttl=storage.default_ttl,
            default_tti=storage.default_tti,
            max_stream_size=storage.max_stream_size,
        )
        self.storage = storage
        self.url = url

    @override
    async def create_entry(
        self,
        request: hishel.Request,
        response: hishel.Response,
        key: str,
        *,
        ttl: float | None = None,
        tti: float | None = None,
    ) -> hishel.Entry:
        return await self.storage.create_entry(
            request,
            response,
            key,
            ttl=ttl,
            tti=tti,
        )

    @override
    async def get_entries(self, key: str) -> list[hishel.Entry]:
        return [
            dataclasses.replace(
                pair,
                request=dataclasses.replace(pair.request, url=self.url),
            )
            for pair in await self.storage.get_entries(key)
        ]

    @override
    async def update_headers(self, id: UUID, headers: hishel.Headers) -> None:
        return await self.storage.update_headers(id, headers)

    @override
    async def remove_entry(self, id: UUID) -> None:
        return await self.storage.remove_entry(id)


class _AsyncCacheTransport(hishel.httpx2.AsyncCacheTransport):
    @override
    async def handle_async_request(
        self,
        request: httpx2.Request,
    ) -> httpx2.Response:
        if storage := self.config.get("storage"):
            caching = request.extensions.setdefault("caching", {})
            caching["storage"] = _AsyncStorageProxy(storage, request.url)
        return await super().handle_async_request(request)


class Context(TypedDict):
    config: _core.Config
    dask_client: Client
    downloader: Downloader
    futures: set[asyncio.Future[Any] | Future[Any]]
    httpx_client: AsyncClient
    locks: WeakValueDictionary
    statistics: Statistics


cache_action: contextvars.ContextVar[CacheAction] = contextvars.ContextVar(
    "cache_action",
    default="no-cache",
)
_exclude = {"backup_servers", "concurrent_requests"}
_json = anyio.Path("statistics.json")
_logger = logging.getLogger("mahoraga")
_not_implemented = httpx2.AsyncBaseTransport()
