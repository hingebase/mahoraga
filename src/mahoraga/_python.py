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
import mimetypes
import pathlib
import posixpath
import urllib.parse
from typing import Annotated

import fastapi
import pydantic_extra_types.semantic_version

from . import _core

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/python/{version}/{name}")
async def get_embedded_python(
    version: pydantic_extra_types.semantic_version.SemanticVersion,
    name: str,
) -> fastapi.Response:
    if (
        version < "3.5.0"
        or version.prerelease is not None
        or version.build is not None
        or name not in {
            f"python-{version}-embed-amd64.zip",
            f"python-{version}-embed-arm64.zip",
            f"python-{version}-embed-win32.zip",
        }
    ):
        return fastapi.Response(status_code=404)
    ctx = _core.context.get()
    urls = [
        urllib.parse.unquote(str(url)).format(version=version, name=name)
        for url in ctx["config"].upstream.python
    ]
    media_type, _ = mimetypes.guess_type(name)
    return await _core.stream(urls, media_type=media_type)


@router.get("/python-build-standalone/{tag}/{name}")
async def get_standalone_python(
    tag: Annotated[
        str,
        fastapi.Path(min_length=8, max_length=8, pattern=r"^\d+$"),
    ],
    name: str,
) -> fastapi.Response:
    ctx = _core.context.get()
    media_type, _ = mimetypes.guess_type(name)
    cache_location = pathlib.Path("python-build-standalone", tag, name)
    lock = ctx["locks"][str(cache_location)]
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(lock)
        if cache_location.is_file():
            return fastapi.responses.FileResponse(
                cache_location,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
                media_type=media_type,
            )
        urls = [
            posixpath.join(str(url), tag, name)
            for url in ctx["config"].upstream.python_build_standalone
        ]
        content = await _core.get([url + ".sha256" for url in urls])
        sha256 = bytes.fromhex(str(content, "ascii"))
        return await _core.stream(
            urls,
            media_type=media_type,
            stack=stack,
            cache_location=cache_location,
            sha256=sha256,
        )
    return _core.unreachable()
