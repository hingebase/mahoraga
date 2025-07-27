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

import mimetypes
from typing import Literal

import fastapi

from mahoraga import _core

from . import _utils

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/squidfunk/{version}/material/templates/.icons/material/{name}")
async def material_icons(version: str, name: str) -> fastapi.Response:
    if not version.startswith("mkdocs-material@"):
        return fastapi.Response(status_code=404)
    urls = _utils.urls(
        "gh/squidfunk",
        version,
        "material/templates/.icons/material",
        name,
    )
    return await _core.stream(urls, media_type="image/svg+xml")


@router.get("/pyodide/{version}/docs/_static/img/pyodide-logo-readme.png")
async def pyodide_logo(version: str) -> fastapi.Response:
    if not version.startswith("pyodide@"):
        return fastapi.Response(status_code=404)
    urls = _utils.urls(
        "gh/pyodide",
        version,
        "docs/_static/img/pyodide-logo-readme.png",
    )
    return await _core.stream(urls, media_type="image/png")


@router.get("/jdecked/{version}/assets/{fmt}/{name}")
async def twemoji(
    version: str,
    fmt: Literal["svg", "72x72"],
    name: str,
) -> fastapi.Response:
    if not version.startswith("twemoji@"):
        return fastapi.Response(status_code=404)
    urls = _utils.urls("gh/jdecked", version, "assets", fmt, name)
    media_type, _ = mimetypes.guess_type(name)
    return await _core.stream(urls, media_type=media_type)
