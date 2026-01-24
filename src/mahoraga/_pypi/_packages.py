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

__all__ = ["router"]

import asyncio
import contextlib
import contextvars
import http
import mimetypes
import pathlib
import posixpath
from typing import TYPE_CHECKING, Annotated

import fastapi.responses
import httpx
import packaging.utils

from mahoraga import _core

from . import _models

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.head("/{tag}/{prefix}/{project}/{filename}")
async def check_pypi_package_availability(
    tag: str,
    prefix: Annotated[str, fastapi.Path(min_length=1, max_length=2)],
    project: str,
    filename: str,
) -> fastapi.Response:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    try:
        response = await client.head(
            f"https://files.pythonhosted.org/packages/{tag}/{prefix}/{project}/{filename}",
        )
    except httpx.HTTPError:
        return fastapi.Response()
    if response.has_redirect_location:
        return fastapi.Response()
    return _core.Response(
        response.content,
        response.status_code,
        response.headers,
    )


@router.get(
    "/{tag}/{prefix}/{project}/{filename}",
    dependencies=_core.immutable,
)
async def get_pypi_package(
    tag: str,
    prefix: Annotated[str, fastapi.Path(min_length=1, max_length=2)],
    project: str,
    filename: str,
) -> fastapi.Response:
    if filename.endswith(".metadata"):
        return await _core.stream(
            f"https://files.pythonhosted.org/packages/{tag}/{prefix}/{project}/{filename}",
        )
    if filename.endswith(".whl"):
        normalized_name = packaging.utils.parse_wheel_filename(filename)[0]
        media_type = "application/zip"
    else:
        normalized_name, _ = packaging.utils.parse_sdist_filename(filename)
        media_type, _ = mimetypes.guess_type(filename)
    cache_location = pathlib.Path("packages", tag, prefix, project, filename)
    async with contextlib.AsyncExitStack() as stack:
        if await _core.cached_or_locked(cache_location, stack):
            return fastapi.responses.FileResponse(
                cache_location,
                media_type=media_type,
            )
        ctx = _core.context.get()
        match len(tag), len(prefix), len(project):
            case (2, 2, 60):
                urls = [
                    posixpath.join(str(url), "packages", tag, prefix,
                                   project, filename)
                    for url in ctx["config"].upstream.pypi.all()
                ]
            case (_, 1, _) if project.startswith(prefix):
                client = ctx["httpx_client"]
                try:
                    response = await stack.enter_async_context(
                        client.stream(
                            "GET",
                            f"https://files.pythonhosted.org/packages/{tag}/{prefix}/{project}/{filename}",
                        ),
                    )
                except httpx.HTTPError as e:
                    raise fastapi.HTTPException(
                        http.HTTPStatus.GATEWAY_TIMEOUT,
                    ) from e
                if not response.has_redirect_location:
                    new_stack = stack.pop_all()
                    content = _stream(response, new_stack)
                    try:
                        await anext(content)
                    except:
                        stack.push_async_exit(new_stack)
                        raise
                    return _core.StreamingResponse(
                        content,
                        response.status_code,
                        response.headers,
                    )
                _core.schedule_exit(stack)
                p = httpx.URL(response.headers["Location"]).path.lstrip("/")
                urls = [
                    posixpath.join(str(url), p)
                    for url in ctx["config"].upstream.pypi.all()
                ]
            case _:
                raise fastapi.HTTPException(404)
        sha256, size = await _sha256(filename, normalized_name)
        if sha256:
            return await _core.stream(
                urls,
                media_type=media_type,
                stack=stack,
                cache_location=cache_location,
                sha256=sha256,
                size=size,
            )
        return await _core.stream(
            urls,
            media_type=media_type,
            stack=stack,
        )
    return _core.unreachable()


async def _sha256(filename: str, project: str) -> tuple[bytes, int | None]:
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    match ctx[_core.context]:
        case {"config": config, "locks": locks}:
            pass
        case _:
            _core.unreachable()
    urls = [
        posixpath.join(str(url), "simple", project) + "/"
        for url in config.upstream.pypi.json_
    ]
    ctx.run(_core.cache_action.set, "force-cache-only")
    lock = locks[f"{project}|application/vnd.pypi.simple.v1+html"]
    try:
        async with lock:
            raw = await loop.create_task(
                _core.get(
                    urls,
                    headers={"Accept": "application/vnd.pypi.simple.v1+html"},
                ),
                context=ctx,
            )
    except (NotImplementedError, fastapi.HTTPException):
        pass
    else:
        return (
            await loop.run_in_executor(None, _sha256_from_html, raw, filename),
            None,
        )
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    try:
        async with locks[f"{project}|application/vnd.pypi.simple.v1+json"]:
            raw = await loop.create_task(
                _core.get(
                    urls,
                    headers={"Accept": "application/vnd.pypi.simple.v1+json"},
                ),
                context=ctx,
            )
    except fastapi.HTTPException:
        pass
    else:
        return await loop.run_in_executor(
            None,
            _sha256_and_size_from_json,
            raw,
            project,
            filename,
        )
    urls += [
        posixpath.join(str(url), "simple", project) + "/"
        for url in config.upstream.pypi.html
    ]
    try:
        async with lock:
            raw = await loop.create_task(
                _core.get(
                    urls,
                    headers={"Accept": "application/vnd.pypi.simple.v1+html"},
                ),
                context=ctx,
            )
    except fastapi.HTTPException:
        return b"", None
    return (
        await loop.run_in_executor(None, _sha256_from_html, raw, filename),
        None,
    )


def _sha256_from_html(raw: bytes, filename: str) -> bytes:
    pattern = b"/%b#sha256=" % filename.encode("ascii")
    try:
        i = raw.index(pattern)
    except ValueError:
        return b""
    i += len(pattern)
    return bytes.fromhex(raw[i : i+64])  # noqa: E226


def _sha256_and_size_from_json(
    raw: bytes,
    project: str,
    filename: str,
) -> tuple[bytes, int | None]:
    simple = _models.Simple.model_validate_json(raw)
    if simple.name != project:
        _core.unreachable()
    for entry in simple.files:
        if entry.filename == filename:
            return bytes.fromhex(entry.hashes.sha256), entry.size
    return b"", None


async def _stream(
    response: httpx.Response,
    stack: contextlib.AsyncExitStack,
) -> AsyncGenerator[bytes]:
    async with stack:
        yield b""
        async for chunk in response.aiter_bytes():
            yield chunk
