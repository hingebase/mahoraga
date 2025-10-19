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

__all__ = ["Metadata", "router"]

import contextlib
import logging
import pathlib
from typing import Annotated, TypedDict

import fastapi.responses

from mahoraga import _core

from . import _utils

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/@bokeh/{package}/{path:path}")
@router.get("/@holoviz/{package}/{path:path}")
@router.get("/@pyscript/{package}/{path:path}")
@router.get("/@stlite/{package}/{path:path}")
# Must be the last
@router.get("/@material-design-icons/{package}/{path:path}")
async def get_scoped_npm_file(
    package: Annotated[str, fastapi.Path(pattern=r"^[^@]+@[^@]+$")],
    path: Annotated[str, fastapi.Path(pattern=r"^[^/]")],
    request: fastapi.Request,
) -> fastapi.Response:
    return await get_npm_file(package, path, request)


@router.get("/{package}/{path:path}")
async def get_npm_file(
    package: Annotated[str, fastapi.Path(pattern=r"^[^@]+@[^@]+$")],
    path: Annotated[str, fastapi.Path(pattern=r"^[^/]")],
    request: fastapi.Request,
) -> fastapi.Response:
    cache_location = pathlib.Path(request.url.path.lstrip("/"))
    async with contextlib.AsyncExitStack() as stack:
        if await _core.cached_or_locked(cache_location, stack):
            return fastapi.responses.FileResponse(
                cache_location,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        prefix = request.url.path.removeprefix("/npm")
        if prefix.startswith("/@"):
            scope, _ = prefix[2:].split("/", 1)
        elif package.startswith(("pyodide@", "swagger-ui-dist@")):
            scope = None
        else:
            return fastapi.Response(status_code=404)
        package, version = package.split("@")
        if scope:
            package = f"@{scope}/{package}"
        resolved = await _Resolved.fetch(
            "npm", package, f"{version}.json",
            url=f"https://data.jsdelivr.com/v1/packages/npm/{package}/resolved",
            params={"specifier": version},
        )
        package = f"{package}@{resolved.version}"
        if resolved.version != version:
            cache_location = pathlib.Path("npm", package, path)
            if await _core.cached_or_locked(cache_location, stack):
                return fastapi.responses.FileResponse(
                    cache_location,
                    headers={
                        "Cache-Control": "public, max-age=31536000, immutable",
                    },
                )
        return await _utils.get_npm_file(
            resolved.links["self"],
            package,
            path,
            cache_location,
            stack,
        )
    return _core.unreachable()


class _File(TypedDict):
    name: str
    hash: str
    size: int


class _MetadataLinks(TypedDict):
    entrypoints: str
    stats: str


class Metadata(_core.NPMBase):
    default: str | None
    files: list[_File]
    links: _MetadataLinks


class _ResolvedLinks(_MetadataLinks):
    self: str


class _Resolved(_core.NPMBase):
    links: _ResolvedLinks


_logger = logging.getLogger("mahoraga")
