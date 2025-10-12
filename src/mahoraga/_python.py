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

import asyncio
import contextlib
import http
import logging
import mimetypes
import os
import pathlib
import posixpath
import re
import urllib.parse
from typing import Annotated

import fastapi.responses
import packaging.version
import pooch  # pyright: ignore[reportMissingTypeStubs]
import pydantic
import pydantic_extra_types.semantic_version  # noqa: TC002
import requests

from . import _core

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/python/pymanager/{name}")
async def get_python_install_manager_for_windows(
    name: Annotated[
        str,
        fastapi.Path(pattern=r"^python-manager-.+\.msix?$"),
    ],
) -> fastapi.Response:
    if not re.fullmatch(
        packaging.version.VERSION_PATTERN,
        name[15 : name.endswith(".msi") - 5],
        re.VERBOSE | re.IGNORECASE,
    ):
        return fastapi.Response(status_code=404)
    ctx = _core.context.get()
    urls = [
        urllib.parse.unquote(str(url)).format(version="pymanager", name=name)
        for url in ctx["config"].upstream.python
    ]
    return await _core.stream(urls)


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
        escaped = name.replace("+", "%2B")  # Required by aliyun mirrors
        urls = [
            posixpath.join(str(url), tag, escaped)
            for url in ctx["config"].upstream.python_build_standalone
        ]
        sha256, size = await _get_standalone_python_sha256_and_size(tag, name)
        return await _core.stream(
            urls,
            media_type=media_type,
            stack=stack,
            cache_location=cache_location,
            sha256=sha256,
            size=size,
        )
    return _core.unreachable()


async def _get_standalone_python_github_release(
    tag: str,
    name: str,
) -> tuple[bytes, int | None]:
    release = await _core.GitHubRelease.fetch(
        f"python-build-standalone/{tag}.json",
        owner="astral-sh",
        repo="python-build-standalone",
        tag_name=tag,
    )
    for asset in release.assets:
        if asset.name == name:
            break
    else:
        raise requests.RequestException
    if digest := asset.digest:
        if digest.startswith("sha256:"):
            return bytes.fromhex(digest[7:]), asset.size
        _logger.warning("GitHub returning non-SHA256 digest: %r", digest)
    raise requests.RequestException


async def _get_standalone_python_sha256_and_size(
    tag: str,
    name: str,
) -> tuple[bytes, int | None]:
    try:
        return await _get_standalone_python_github_release(tag, name)
    except requests.RequestException:
        pass
    except (OSError, pydantic.ValidationError):
        _logger.exception("Failed to get GitHub release metadata")
    cache_location = pathlib.Path("python-build-standalone", tag, "SHA256SUMS")
    ctx = _core.context.get()
    loop = asyncio.get_running_loop()
    async with ctx["locks"][str(cache_location)]:
        if not cache_location.is_file():
            dir_, fname = os.path.split(cache_location)
            urls = [
                posixpath.join(str(url), tag, "SHA256SUMS")
                for url in ctx["config"].upstream.python_build_standalone
            ]
            async with contextlib.aclosing(_core.load_balance(urls)) as it:
                async for url in it:
                    with contextlib.suppress(Exception):
                        await loop.run_in_executor(
                            None,
                            pooch.retrieve,  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                            url,
                            None,
                            fname,
                            dir_,
                        )
                        break
                else:
                    status_code = http.HTTPStatus.GATEWAY_TIMEOUT
                    raise fastapi.HTTPException(status_code)
    return await loop.run_in_executor(
        None,
        _parse_standalone_python_sha256,
        cache_location,
        f"  {name}\n".encode("ascii"),
    )


def _parse_standalone_python_sha256(
    cache_location: pathlib.Path,
    name: bytes,
) -> tuple[bytes, None]:
    with cache_location.open("rb") as f:
        for line in f:
            if line.endswith(name):
                return bytes.fromhex(line[:64]), None  # pyright: ignore[reportArgumentType]
    raise fastapi.HTTPException(404)


_logger = logging.getLogger("mahoraga")
