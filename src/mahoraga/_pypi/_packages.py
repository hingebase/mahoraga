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

__all__ = ["router"]

import contextlib
import http
import mimetypes
import posixpath
from collections.abc import AsyncGenerator
from typing import Annotated

import fastapi
import httpx

from mahoraga import _core

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


@router.get("/{tag}/{prefix}/{project}/{filename}")
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
    ctx = _core.context.get()
    async with contextlib.AsyncExitStack() as stack:
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
                except httpx.HTTPError:
                    return fastapi.Response(
                        status_code=http.HTTPStatus.GATEWAY_TIMEOUT,
                    )
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
                return fastapi.Response(status_code=404)
        if filename.endswith(".whl"):
            media_type = "application/x-zip-compressed"
        else:
            media_type, _ = mimetypes.guess_type(filename)
        return await _core.stream(
            urls,
            media_type=media_type,
            stack=stack,
        )
    return _core.unreachable()


async def _stream(
    response: httpx.Response,
    stack: contextlib.AsyncExitStack,
) -> AsyncGenerator[bytes, None]:
    async with stack:
        yield b""
        async for chunk in response.aiter_bytes():
            yield chunk
