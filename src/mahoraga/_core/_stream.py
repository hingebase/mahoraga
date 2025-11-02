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
    "APIRoute",
    "Response",
    "StreamingResponse",
    "get",
    "load_balance",
    "stream",
]

import asyncio
import contextlib
import hashlib
import http
import logging
import pathlib
import shutil
from collections.abc import (
    AsyncGenerator,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Mapping,
)
from typing import TYPE_CHECKING, Any, TypedDict, Unpack, overload, override

import anyio
import fastapi.responses
import fastapi.routing
import hishel.fastapi
import httpx
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]

from mahoraga import _core

if TYPE_CHECKING:
    from _hashlib import HASH
    from types import TracebackType

    from _typeshed import ReadableBuffer, StrPath

hourly = [
    hishel.fastapi.cache(max_age=3600),
]
immutable = [
    hishel.fastapi.cache(max_age=31536000, public=True, immutable=True),
]


class APIRoute(fastapi.routing.APIRoute):
    @override
    def get_route_handler(self) -> Callable[
        [fastapi.Request],
        Coroutine[Any, Any, fastapi.Response],
    ]:
        async def wrapper(request: fastapi.Request) -> fastapi.Response:
            match response := await wrapped(request):
                case fastapi.responses.FileResponse():
                    _get_stack(request).push(_wrap_file_not_found_error)
                case fastapi.responses.StreamingResponse(
                    body_iterator=AsyncGenerator() as agen,
                ):
                    _get_stack(request).push_async_callback(agen.aclose)
                case _:
                    pass
            return response
        wrapped = super().get_route_handler()
        return wrapper


class Response(fastapi.Response):
    @override
    def init_headers(self, headers: Mapping[str, str] | None = None) -> None:
        headers = httpx.Headers(headers)
        for key in "Content-Encoding", "Date", "Server", "Transfer-Encoding":
            headers.pop(key, None)
        if self.media_type != type(self).media_type:
            headers.pop("Content-Type", None)
        super().init_headers(headers)


class StreamingResponse(fastapi.responses.StreamingResponse, Response):
    media_type = "application/octet-stream"


async def get(urls: Iterable[str], **kwargs: object) -> bytes:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    response = None
    async with (
        contextlib.AsyncExitStack() as stack,
        contextlib.aclosing(load_balance(urls)) as it,
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
    cache_location: StrPath | None
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
    cache_location: StrPath,
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


class _ContentLengthError(Exception):
    pass


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
    inner_stack = await stack.enter_async_context(contextlib.AsyncExitStack())
    response = None
    async with contextlib.aclosing(load_balance(urls)) as it:
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
            try:
                headers = _unify_content_length(response.headers, kwargs)
            except _ContentLengthError:
                _core.schedule_exit(inner_stack)
                response = None
                continue
            new_stack = contextlib.AsyncExitStack()
            content = _stream(response, new_stack, **kwargs)
            try:
                if await anext(content):
                    _core.unreachable()
            except httpx.TransportError:
                _core.schedule_exit(inner_stack)
                response = None
                continue
            await new_stack.enter_async_context(stack.pop_all())
            return StreamingResponse(
                content,
                response.status_code,
                headers,
                media_type,
            )
    if response:
        return Response(
            status_code=response.status_code,
            headers=response.headers,
        )
    return fastapi.Response(status_code=http.HTTPStatus.GATEWAY_TIMEOUT)


async def load_balance(urls: Iterable[str]) -> AsyncGenerator[str]:
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


def _get_stack(request: fastapi.Request) -> contextlib.AsyncExitStack:
    stack: contextlib.AsyncExitStack
    match request.scope:
        case {"fastapi_inner_astack": contextlib.AsyncExitStack() as stack}:  # pyright: ignore[reportUnknownVariableType]
            return stack
        case _:
            return _core.unreachable()


async def _stream(
    response: httpx.Response,
    wrapped: contextlib.AsyncExitStack,
    *,
    cache_location: StrPath | None = None,
    sha256: bytes | None = None,
    size: int | None = None,
) -> AsyncGenerator[bytes]:
    last = b""
    scope = anyio.CancelScope(shield=True)
    async with contextlib.AsyncExitStack() as stack:
        outer = await stack.enter_async_context(contextlib.AsyncExitStack())
        await stack.enter_async_context(wrapped)
        if cache_location and sha256:
            h = hashlib.sha256()
            inner = contextlib.ExitStack()
            loop = asyncio.get_running_loop()

            @stack.callback
            def _() -> None:
                try:
                    outer.enter_context(scope)
                finally:
                    fut = loop.run_in_executor(None, inner.close)
                    outer.push_async_callback(lambda: fut)
            fwrite = await loop.run_in_executor(
                None,
                inner.enter_context,
                _tempfile(response, cache_location, sha256, size, h),
            )
            async for current in response.aiter_bytes():
                fut = loop.run_in_executor(None, fwrite, current)
                yield last
                last = current
                await fut
                h.update(current)
        else:
            stack.callback(outer.enter_context, scope)
            if cache_location or sha256:
                _core.unreachable()
            async for current in response.aiter_bytes():
                yield last
                last = current
        yield last


@contextlib.contextmanager
def _tempfile(
    response: httpx.Response,
    cache_location: StrPath,
    sha256: bytes,
    size: int | None,
    hash_: HASH,
) -> Generator[Callable[[ReadableBuffer], int]]:
    dir_ = pathlib.Path(cache_location).parent
    dir_.mkdir(parents=True, exist_ok=True)
    with (
        pooch.utils.temporary_file(dir_) as tmp,  # pyright: ignore[reportUnknownMemberType]
        contextlib.ExitStack() as stack,
        pathlib.Path(tmp).open("wb") as f,
    ):
        f.truncate(size)
        try:
            yield f.write
        finally:
            if hash_.digest() == sha256 and (
                size is None
                or size == (
                    f.tell()
                    if "Content-Encoding" in response.headers
                    else response.num_bytes_downloaded
                )
            ):
                stack.callback(shutil.move, tmp, cache_location)


def _unify_content_length(
    headers: httpx.Headers,
    kwargs: _CacheOptions,
) -> httpx.Headers:
    if "Content-Encoding" in headers:
        # Content-Length refer to the encoded data, see
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Encoding
        headers = headers.copy()
        if size := kwargs.get("size"):
            headers["Content-Length"] = str(size)
        else:
            headers.pop("Content-Length", None)
        # Content-Encoding will be removed in Response.init_headers
        return headers
    if content_length := headers.get("Content-Length"):
        actual = int(content_length)
        expect = kwargs.setdefault("size", actual)
        if expect is None:
            kwargs["size"] = actual
        elif expect != actual:
            _logger.warning(
                "Content-Length mismatch: expect %d, got %d",
                expect,
                actual,
            )
            raise _ContentLengthError
    return headers


def _wrap_file_not_found_error(
    _exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    _traceback: TracebackType | None,
) -> None:
    match exc_value:
        case RuntimeError(__context__=FileNotFoundError() as e):
            raise fastapi.HTTPException(404) from e
        case _:
            pass


_logger = logging.getLogger("mahoraga")
