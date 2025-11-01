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

__all__ = ["extract_from_tarball", "get_npm_file", "urls"]

import asyncio
import base64
import logging
import mimetypes
import pathlib
import posixpath
import shutil
import tarfile
from typing import TYPE_CHECKING, Literal

import fastapi.responses

from mahoraga import _core, _jsdelivr

if TYPE_CHECKING:
    from contextlib import AsyncExitStack


async def extract_from_tarball(
    tarball: pathlib.Path,
    member: str,
    cache_location: pathlib.Path,
) -> fastapi.Response | None:
    ctx = _core.context.get()
    loop = asyncio.get_running_loop()
    async with ctx["locks"][str(tarball)]:
        try:
            f = await loop.run_in_executor(
                None,
                tarfile.TarFile.bz2open,
                tarball,
            )
        except OSError:
            return None
    try:
        member = (
            "xbuildenv/pyodide-root/dist/"
            if tarball.name.startswith("xbuildenv")
            else "pyodide/"
        ) + member
        return await loop.run_in_executor(
            None,
            _extract_from_tarball,
            tarball,
            member,
            cache_location,
            f,
        )
    finally:
        await loop.run_in_executor(None, f.close)


async def get_npm_file(
    url: str,
    package: str,
    path: str,
    cache_location: pathlib.Path,
    stack: AsyncExitStack,
) -> fastapi.Response:
    if package.startswith("pyodide@"):
        for name in _pyodide_packages(path):
            tarball = pathlib.Path("pyodide", f"{name}-{package[8:]}.tar.bz2")
            if response := await extract_from_tarball(
                tarball,
                path,
                cache_location,
            ):
                return response
    metadata = await _jsdelivr.Metadata.fetch(
        f"npm/{package}.json",
        url=url,
        params={"structure": "flat"},
    )
    for file in metadata.files:
        if file["name"].lstrip("/") == path:
            break
    else:
        return fastapi.Response(status_code=404)
    media_type, _ = mimetypes.guess_type(path)
    return await _core.stream(
        urls("npm", package, path),
        media_type=media_type,
        stack=stack,
        cache_location=cache_location,
        sha256=base64.b64decode(file["hash"]),
        size=file["size"],
    )


def urls(*paths: str) -> list[str]:
    return [
        posixpath.join(str(url), *paths)
        for url in _core.context.get()["config"].upstream.pyodide
    ]


def _extract_from_tarball(
    tarball: pathlib.Path,
    member: str,
    cache_location: pathlib.Path,
    f: tarfile.TarFile,
) -> fastapi.Response | None:
    try:
        info = f.getmember(member)
    except KeyError:
        _logger.warning("Invalid tarball %s", tarball, exc_info=True)
        return None
    if f2 := f.extractfile(info):
        with f2:
            cache_location.parent.mkdir(parents=True, exist_ok=True)
            with cache_location.open("xb") as f3:
                f3.truncate(info.size)
                shutil.copyfileobj(f2, f3)
        return fastapi.responses.FileResponse(cache_location)
    _logger.warning("Invalid tarball %s", tarball)
    return None


def _pyodide_packages(
    path: str,
) -> tuple[Literal["pyodide", "pyodide-core", "xbuildenv"], ...]:
    match path:
        case (
            "pyodide.asm.js"
            | "pyodide.asm.wasm"
            | "pyodide.d.ts"
            | "pyodide.js"
            | "pyodide.mjs"
            | "pyodide-lock.json"
            | "python_stdlib.zip"
        ):
            return ("pyodide-core", "xbuildenv", "pyodide")
        case "ffi.d.ts" | "package.json":
            return ("pyodide-core", "pyodide")
        case "pyodide.js.map" | "pyodide.mjs.map":
            return ("xbuildenv", "pyodide")
        case "console.html":
            return ("pyodide",)
        case _:
            return ()


_logger = logging.getLogger("mahoraga")
