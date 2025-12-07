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
import base64
import contextlib
import http
import logging
import mimetypes
import os
import pathlib
import posixpath
from typing import Annotated, Literal

import fastapi.responses
import packaging.version
import pooch  # pyright: ignore[reportMissingTypeStubs]
import pyodide_lock

from mahoraga import _core, _jsdelivr

from . import _utils

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/{name}", dependencies=_core.immutable)
async def get_pyodide_package(
    name: Annotated[
        str,
        fastapi.Path(
            pattern=r"^(pyodide|pyodide-core|static-libraries|xbuildenv)-.+\.tar\.bz2$",
        ),
    ],
) -> fastapi.Response:
    version = name[:-8].rsplit("-", 1)[1]
    try:
        packaging.version.parse(version)
    except packaging.version.InvalidVersion:
        return fastapi.Response(status_code=404)
    cache_location = pathlib.Path("pyodide", name)
    media_type, _ = mimetypes.guess_type(name)
    async with contextlib.AsyncExitStack() as stack:
        if await _core.cached_or_locked(cache_location, stack):
            return fastapi.responses.FileResponse(
                cache_location,
                media_type=media_type,
            )
        release = await _core.GitHubRelease.fetch(
            f"pyodide/{version}.json",
            owner="pyodide",
            repo="pyodide",
            tag_name=version,
        )
        for asset in release.assets:
            if asset.name == name:
                break
        else:
            return fastapi.Response(status_code=404)
        headers = {
            "Accept": "application/octet-stream",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if digest := asset.digest:
            if digest.startswith("sha256:"):
                return await _core.stream(
                    asset.url,
                    headers=headers,
                    media_type=media_type,
                    stack=stack,
                    cache_location=cache_location,
                    sha256=bytes.fromhex(digest[7:]),
                    size=asset.size,
                )
            _logger.warning("GitHub returning non-SHA256 digest: %r", digest)
        return await _core.stream(asset.url, headers=headers, stack=stack)
    return _core.unreachable()


@router.get("/dev/{build}/{path:path}")
async def get_pyodide_dev_file(
    build: Literal["full", "debug"],
    path: Annotated[str, fastapi.Path(pattern=r"^[^/]")],
) -> fastapi.Response:
    urls = _utils.urls("pyodide", "dev", build, path)
    media_type, _ = mimetypes.guess_type(path)
    # Never cached
    return await _core.stream(urls, media_type=media_type)


@router.get("/{version}/full/package.json", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide.asm.js", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide.asm.wasm", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide.js", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide.js.map", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide.mjs", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide.mjs.map", dependencies=_core.immutable)
@router.get("/{version}/full/pyodide-lock.json", dependencies=_core.immutable)
@router.get("/{version}/full/python_stdlib.zip", dependencies=_core.immutable)
@router.get("/{version}/debug/package.json", dependencies=_core.immutable)
@router.get("/{version}/debug/pyodide.js.map", dependencies=_core.immutable)
@router.get("/{version}/debug/pyodide.mjs", dependencies=_core.immutable)
@router.get("/{version}/debug/pyodide.mjs.map", dependencies=_core.immutable)
@router.get("/{version}/debug/pyodide-lock.json", dependencies=_core.immutable)
@router.get("/{version}/debug/python_stdlib.zip", dependencies=_core.immutable)
async def get_pyodide_core_file(
    version: Annotated[str, fastapi.Path(pattern=r"^v")],
    request: fastapi.Request,
) -> fastapi.Response:
    version = version.lstrip("v")
    package = f"pyodide@{version}"
    name = posixpath.basename(request.url.path)
    cache_location = pathlib.Path("npm", package, name)
    async with contextlib.AsyncExitStack() as stack:
        if await _core.cached_or_locked(cache_location, stack):
            return fastapi.responses.FileResponse(cache_location)
        return await _utils.get_npm_file(
            f"https://data.jsdelivr.com/v1/packages/npm/{package}",
            package,
            name,
            cache_location,
            stack,
        )
    return _core.unreachable()


@router.get(
    "/{version}/full/python_cli_entry.mjs",
    dependencies=_core.immutable,
)
@router.get(
    "/{version}/debug/python_cli_entry.mjs",
    dependencies=_core.immutable,
)
async def get_python_cli_entry(
    version: Annotated[str, fastapi.Path(pattern=r"^v")],
) -> fastapi.Response:
    member = "python_cli_entry.mjs"
    cache_location = pathlib.Path("pyodide", version, "full", member)
    async with _core.cached_or_locked(cache_location) as cached:
        if cached:
            return fastapi.responses.FileResponse(cache_location)
        for name in "pyodide-core", "xbuildenv", "pyodide":
            tarball = pathlib.Path("pyodide", f"{name}-{version[1:]}.tar.bz2")
            if response := await _utils.extract_from_tarball(
                tarball,
                member,
                cache_location,
            ):
                return response
    urls = _utils.urls("pyodide", version, "full", member)
    return await _core.stream(urls, media_type="text/javascript")


@router.get("/{version}/{build}/{path:path}", dependencies=_core.immutable)
async def get_pyodide_file(
    version: Annotated[str, fastapi.Path(pattern=r"^v")],
    build: Literal["full", "debug"],
    path: Annotated[str, fastapi.Path(pattern=r"^[^/]")],
) -> fastapi.Response:
    urls = _utils.urls("pyodide", version, build, path)
    media_type, _ = mimetypes.guess_type(path)
    if "/" in path or not path.endswith((".whl", ".zip", "-tests.tar")):
        # No way to find the checksums
        return await _core.stream(urls, media_type=media_type)
    cache_location = pathlib.Path("pyodide", version, "full", path)
    async with contextlib.AsyncExitStack() as stack:
        if await _core.cached_or_locked(cache_location, stack):
            return fastapi.responses.FileResponse(cache_location)
        version = version.lstrip("v")
        tarball = pathlib.Path("pyodide", f"pyodide-{version}.tar.bz2")
        if response := await _utils.extract_from_tarball(
            tarball,
            path,
            cache_location,
        ):
            return response
        package = f"pyodide@{version}"
        json_file = pathlib.Path("npm", package, "pyodide-lock.json")
        await _get_pyodide_lock(json_file, package)
        for spec in (
            pyodide_lock.PyodideLockSpec.from_json(json_file).packages.values()
        ):
            if spec.file_name == path:
                break
        else:
            return fastapi.Response(status_code=404)
        if path.endswith(".whl"):
            media_type = "application/zip"
            urls.append(
                f"https://anaconda.org/pyodide/{spec.name}/{spec.version}/download/{path}",
            )
        return await _core.stream(
            urls,
            media_type=media_type,
            stack=stack,
            cache_location=cache_location,
            sha256=bytes.fromhex(spec.sha256),
        )
    return _core.unreachable()


async def _get_pyodide_lock(
    cache_location: pathlib.Path,
    package: str,
) -> None:
    async with _core.cached_or_locked(cache_location) as cached:
        if not cached:
            for name in "pyodide-core", "xbuildenv":
                tarball = pathlib.Path(
                    "pyodide",
                    f"{name}-{package[8:]}.tar.bz2",
                )
                if await _utils.extract_from_tarball(
                    tarball,
                    "pyodide-lock.json",
                    cache_location,
                ):
                    return
            metadata = await _jsdelivr.Metadata.fetch(
                f"npm/{package}.json",
                url=f"https://data.jsdelivr.com/v1/packages/npm/{package}",
                params={"structure": "flat"},
            )
            for file in metadata.files:
                if file["name"] == "/pyodide-lock.json":
                    break
            else:
                raise fastapi.HTTPException(404)
            known_hash = base64.b64decode(file["hash"]).hex()
            dir_, fname = os.path.split(cache_location)
            loop = asyncio.get_running_loop()
            urls = _utils.urls("npm", package, "pyodide-lock.json")
            for url in _core.load_balance(urls):
                with contextlib.suppress(Exception):
                    await loop.run_in_executor(
                        None,
                        pooch.retrieve,  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                        url,
                        known_hash,
                        fname,
                        dir_,
                    )
                    break
            else:
                status_code = http.HTTPStatus.GATEWAY_TIMEOUT
                raise fastapi.HTTPException(status_code)


_logger = logging.getLogger("mahoraga")
