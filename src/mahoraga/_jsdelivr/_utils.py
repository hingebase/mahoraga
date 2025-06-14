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

__all__ = ["get_npm_file", "urls"]

import asyncio
import base64
import contextlib
import logging
import mimetypes
import pathlib
import posixpath
import shutil
import tarfile
from typing import Literal

import fastapi

from mahoraga import _core, _jsdelivr


async def get_npm_file(
    url: str,
    package: str,
    path: str,
    cache_location: pathlib.Path,
    stack: contextlib.AsyncExitStack,
) -> fastapi.Response:
    if package.startswith("pyodide@"):
        ctx = _core.context.get()
        locks = ctx["locks"]
        loop = asyncio.get_running_loop()
        for name in _pyodide_packages(path):
            tarball = pathlib.Path("pyodide", f"{name}-{package[8:]}.tar.bz2")
            async with locks[str(tarball)]:
                try:
                    f = await loop.run_in_executor(
                        None,
                        tarfile.TarFile.bz2open,
                        tarball,
                    )
                except OSError:
                    continue
            try:
                member = (
                    "xbuildenv/pyodide-root/dist/"
                    if name == "xbuildenv"
                    else "pyodide/"
                ) + path
                if response := await loop.run_in_executor(
                    None,
                    _get_npm_file,
                    cache_location,
                    tarball,
                    f,
                    member,
                ):
                    return response
            finally:
                await loop.run_in_executor(None, f.close)
    metadata = await _jsdelivr.Metadata.fetch(
        url,
        "npm",
        f"{package}.json",
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


def _get_npm_file(
    cache_location: pathlib.Path,
    tarball: pathlib.Path,
    f: tarfile.TarFile,
    member: str,
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
        return fastapi.responses.FileResponse(
            cache_location,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )
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
