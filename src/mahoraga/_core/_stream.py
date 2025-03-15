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

__all__ = ["Response", "StreamingResponse", "get", "stream"]

import asyncio
import contextlib
import hashlib
import http
import pathlib
import shutil
from collections.abc import AsyncGenerator, Iterable, Mapping
from typing import TYPE_CHECKING, TypedDict, Unpack, overload, override

import anyio
import fastapi
import httpx
import pooch  # pyright: ignore[reportMissingTypeStubs]
import starlette.types

from mahoraga import _core

if TYPE_CHECKING:
    from _typeshed import StrPath


class Response(fastapi.Response):
    @override
    def init_headers(self, headers: Mapping[str, str] | None = None) -> None:
        headers = httpx.Headers(headers)
        for key in "Content-Encoding", "Date", "Server":
            headers.pop(key, None)
        super().init_headers(headers)


class StreamingResponse(fastapi.responses.StreamingResponse, Response):
    media_type = "application/octet-stream"

    @override
    async def stream_response(self, send: starlette.types.Send) -> None:
        if isinstance(self.body_iterator, AsyncGenerator):
            async with contextlib.aclosing(self.body_iterator):  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                await super().stream_response(send)
        else:
            await super().stream_response(send)


async def get(urls: Iterable[str], **kwargs: object) -> bytes:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    response = None
    async with (
        _core.AsyncExitStack() as stack,
        contextlib.aclosing(_load_balance(urls)) as it,
    ):
        async for url in it:
            try:
                response = await stack.enter_async_context(
                    client.stream("GET", url, **kwargs),
                )
            except httpx.HTTPError:
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                stack.schedule_exit()
                continue
            try:
                return await response.aread()
            except httpx.StreamError:
                stack.schedule_exit()
    if not response:
        raise fastapi.HTTPException(http.HTTPStatus.GATEWAY_TIMEOUT)
    headers = response.headers
    for key in "Date", "Server":
        headers.pop(key, None)
    raise fastapi.HTTPException(response.status_code, headers=dict(headers))


class _CacheOptions(TypedDict, total=False):
    cache_location: "StrPath | None"
    sha256: bytes | None
    size: int | None


@overload
async def stream(
    urls: Iterable[str],
    *,
    headers: Mapping[str, str] | None = ...,
    media_type: str | None = ...,
    stack: _core.AsyncExitStack | None = None,
    cache_location: None = ...,
    sha256: None = ...,
    size: None = ...,
) -> fastapi.Response: ...

@overload
async def stream(
    urls: Iterable[str],
    *,
    headers: Mapping[str, str] | None = ...,
    media_type: str | None = ...,
    stack: _core.AsyncExitStack | None = None,
    cache_location: "StrPath",
    sha256: bytes,
    size: int | None = ...,
) -> fastapi.Response: ...


async def stream(
    urls: Iterable[str],
    *,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    stack: _core.AsyncExitStack | None = None,
    **kwargs: Unpack[_CacheOptions],
) -> fastapi.Response:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    response = None
    if stack is None:
        stack = _core.AsyncExitStack()
    async with stack, contextlib.aclosing(_load_balance(urls)) as it:
        async for url in it:
            try:
                response = await stack.enter_async_context(
                    client.stream("GET", url, headers=headers),
                )
            except httpx.HTTPError:
                continue
            if response.status_code == http.HTTPStatus.NOT_MODIFIED:
                break
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                stack.schedule_exit()
                continue
            content = _stream(response, stack.pop_all(), **kwargs)
            return StreamingResponse(
                content,
                response.status_code,
                response.headers,
                media_type,
            )
    if response:
        return Response(
            status_code=response.status_code,
            headers=response.headers,
        )
    return fastapi.Response(status_code=http.HTTPStatus.GATEWAY_TIMEOUT)


async def _load_balance(urls: Iterable[str]) -> AsyncGenerator[str, None]:
    if isinstance(urls, str):
        urls = {urls}
    else:
        ctx = _core.context.get()
        lock = ctx["locks"]["statistics.json"]
        urls = set(urls)
        while len(urls) > 1:
            async with lock:
                url = min(urls, key=_core.Statistics().key)
            urls.remove(url)
            yield url
    for url in urls:
        yield url


async def _stream(
    response: httpx.Response,
    stack: _core.AsyncExitStack,
    *,
    cache_location: "StrPath | None" = None,
    sha256: bytes | None = None,
    size: int | None = None,
) -> AsyncGenerator[bytes, None]:
    async with stack:
        if cache_location and sha256:
            dir_ = pathlib.Path(cache_location).parent
            h = hashlib.sha256()
            n = 0
            pooch.utils.make_local_storage(dir_)  # pyright: ignore[reportUnknownMemberType]
            with pooch.utils.temporary_file(dir_) as tmp:  # pyright: ignore[reportUnknownMemberType]
                async with await anyio.open_file(tmp, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        h.update(chunk)
                        n += len(chunk)
                        task = asyncio.create_task(f.write(chunk))
                        yield chunk
                        await task
                    stack.schedule_exit()
                if h.digest() == sha256 and (size is None or n == size):
                    shutil.move(tmp, cache_location)
        elif cache_location or sha256:
            _core.unreachable()
        else:
            async for chunk in response.aiter_bytes():
                yield chunk
