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

__all__ = ["APIRoute", "Response", "StreamingResponse", "get", "stream"]

import asyncio
import contextlib
import hashlib
import http
import logging
import os
import pathlib
import shutil
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, TypedDict, Unpack, overload, override

import anyio
import fastapi.routing
import httpx
import pooch  # pyright: ignore[reportMissingTypeStubs]
import starlette.types
from starlette._exception_handler import (
    wrap_app_handling_exceptions,  # noqa: PLC2701
)

from mahoraga import _core

if TYPE_CHECKING:
    from _typeshed import StrPath


class APIRoute(fastapi.routing.APIRoute):
    @override
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(path, endpoint, **kwargs)
        func = self.get_route_handler()

        async def outer(
            scope: starlette.types.Scope,
            receive: starlette.types.Receive,
            send: starlette.types.Send,
        ) -> None:
            req = fastapi.Request(scope, receive, send)

            async def inner(
                scope: starlette.types.Scope,
                receive: starlette.types.Receive,
                send: starlette.types.Send,
            ) -> None:
                resp = await func(req)
                try:
                    await resp(scope, receive, send)
                except RuntimeError as e:  # https://github.com/encode/starlette/pull/2856
                    if (
                        isinstance(resp, fastapi.responses.FileResponse)
                        and isinstance(e.__context__, FileNotFoundError)
                    ):
                        raise fastapi.HTTPException(404) from e.__context__
                    raise
                finally:
                    if (
                        isinstance(resp, fastapi.responses.StreamingResponse)
                        and isinstance(resp.body_iterator, AsyncGenerator)
                    ):
                        await resp.body_iterator.aclose()  # pyright: ignore[reportUnknownMemberType]

            middleware = wrap_app_handling_exceptions(inner, req)
            await middleware(scope, receive, send)

        self.app = outer


class Response(fastapi.Response):
    @override
    def init_headers(self, headers: Mapping[str, str] | None = None) -> None:
        headers = httpx.Headers(headers)
        for key in "Content-Encoding", "Date", "Server":
            headers.pop(key, None)
        super().init_headers(headers)


class StreamingResponse(fastapi.responses.StreamingResponse, Response):
    media_type = "application/octet-stream"


async def get(urls: Iterable[str], **kwargs: object) -> bytes:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    response = None
    async with (
        contextlib.AsyncExitStack() as stack,
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
                _core.schedule_exit(stack)
                continue
            try:
                return await response.aread()
            except httpx.StreamError:
                _core.schedule_exit(stack)
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
    stack: contextlib.AsyncExitStack | None = None,
    cache_location: None = ...,
    sha256: None = ...,
    size: int | None = ...,
) -> fastapi.Response: ...

@overload
async def stream(
    urls: Iterable[str],
    *,
    headers: Mapping[str, str] | None = ...,
    media_type: str | None = ...,
    stack: contextlib.AsyncExitStack | None = None,
    cache_location: "StrPath",
    sha256: bytes,
    size: int | None = ...,
) -> fastapi.Response: ...


async def stream(
    urls: Iterable[str],
    *,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    stack: contextlib.AsyncExitStack | None = None,
    **kwargs: Unpack[_CacheOptions],
) -> fastapi.Response:
    if stack:
        return await _entered(
            stack,
            urls,
            headers=headers,
            media_type=media_type,
            **kwargs,
        )
    async with contextlib.AsyncExitStack() as new_stack:
        return await _entered(
            new_stack,
            urls,
            headers=headers,
            media_type=media_type,
            **kwargs,
        )
    return _core.unreachable()


async def _entered(
    stack: contextlib.AsyncExitStack,
    urls: Iterable[str],
    *,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    **kwargs: Unpack[_CacheOptions],
) -> fastapi.Response:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    inner_stack = contextlib.AsyncExitStack()
    await stack.enter_async_context(inner_stack)
    response = None
    async with contextlib.aclosing(_load_balance(urls)) as it:
        async for url in it:
            try:
                response = await inner_stack.enter_async_context(
                    client.stream("GET", url, headers=headers),
                )
            except httpx.HTTPError:
                continue
            if response.status_code == http.HTTPStatus.NOT_MODIFIED:
                break
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                _core.schedule_exit(inner_stack)
                continue
            if content_length := response.headers.get("Content-Length"):
                actual = int(content_length)
                expect = kwargs.setdefault("size", actual)
                if expect is None:
                    kwargs["size"] = actual
                elif expect != actual:
                    _core.schedule_exit(inner_stack)
                    _logger.warning(
                        "Content-Length mismatch: expect %d, got %d",
                        expect,
                        actual,
                    )
                    response = None
                    continue
            new_stack = stack.pop_all()
            content = _stream(response, new_stack, **kwargs)
            try:
                await anext(content)
            except:
                stack.push_async_exit(new_stack)
                raise
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
    stack: contextlib.AsyncExitStack,
    *,
    cache_location: "StrPath | None" = None,
    sha256: bytes | None = None,
    size: int | None = None,
) -> AsyncGenerator[bytes, None]:
    async with stack:
        yield b""
        if cache_location and sha256:
            dir_ = pathlib.Path(cache_location).parent
            h = hashlib.sha256()
            if size:
                def opener(path: str, flags: int) -> int:
                    fd = os.open(path, flags)
                    try:
                        os.truncate(fd, size)
                    except:
                        os.close(fd)
                        raise
                    return fd
                open_ = opener
            else:
                open_ = None
            pooch.utils.make_local_storage(dir_)  # pyright: ignore[reportUnknownMemberType]
            with pooch.utils.temporary_file(dir_) as tmp:  # pyright: ignore[reportUnknownMemberType]
                async with await anyio.open_file(tmp, "wb", opener=open_) as f:
                    async for chunk in response.aiter_bytes():
                        h.update(chunk)
                        task = asyncio.create_task(f.write(chunk))
                        yield chunk
                        await task
                if h.digest() == sha256 and (
                    size is None
                    or response.num_bytes_downloaded == size
                ):
                    shutil.move(tmp, cache_location)
        elif cache_location or sha256:
            _core.unreachable()
        else:
            async for chunk in response.aiter_bytes():
                yield chunk


_logger = logging.getLogger("mahoraga")
