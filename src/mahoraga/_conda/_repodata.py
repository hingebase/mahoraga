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
import posixpath
from typing import Annotated

import fastapi
import httpx
import pydantic
import rattler.platform

from mahoraga import _core

from . import _models, _utils

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.head("/{channel}/{platform}/repodata.json.bz2")
@router.head("/{channel}/{platform}/repodata.json.zst")
@router.head("/{channel}/{platform}/repodata.jlap")
async def check_repodata_availability(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    request: fastapi.Request,
) -> fastapi.Response:
    return await _check_repodata_availability(channel, platform, request)


@router.head("/{channel}/label/{label}/{platform}/repodata.json.bz2")
@router.head("/{channel}/label/{label}/{platform}/repodata.json.zst")
@router.head("/{channel}/label/{label}/{platform}/repodata.jlap")
async def check_repodata_availability_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
    request: fastapi.Request,
) -> fastapi.Response:
    channel = f"{channel}/label/{label}"
    return await _check_repodata_availability(channel, platform, request)


@router.get("/{channel}/{platform}/repodata.json")
@router.get("/{channel}/{platform}/repodata.json.bz2")
@router.get("/{channel}/{platform}/repodata.json.zst")
async def get_repodata(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    request: fastapi.Request,
    headers: Annotated[_models.RepodataHeaders, fastapi.Header()],
) -> fastapi.Response:
    return await _get_repodata(channel, platform, request, headers)


@router.get("/{channel}/label/{label}/{platform}/repodata.json")
@router.get("/{channel}/label/{label}/{platform}/repodata.json.bz2")
@router.get("/{channel}/label/{label}/{platform}/repodata.json.zst")
async def get_repodata_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
    request: fastapi.Request,
    headers: Annotated[_models.RepodataHeaders, fastapi.Header()],
) -> fastapi.Response:
    return await _get_repodata(channel, platform, request, headers, label)


@router.get("/{channel}/{platform}/repodata.jlap")
async def get_differential_repodata(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    headers: Annotated[_models.JLAPHeaders, fastapi.Header()],
) -> fastapi.Response:
    return await _core.stream(
        f"https://conda.anaconda.org/{channel}/{platform}/repodata.jlap",
        headers=_to_dict(headers),
    )


@router.get("/{channel}/label/{label}/{platform}/repodata.jlap")
async def get_differential_repodata_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
    headers: Annotated[_models.JLAPHeaders, fastapi.Header()],
) -> fastapi.Response:
    return await _core.stream(
        f"https://conda.anaconda.org/{channel}/label/{label}/{platform}/repodata.jlap",
        headers=_to_dict(headers),
    )


async def _check_repodata_availability(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    request: fastapi.Request,
) -> fastapi.Response:
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    name = posixpath.basename(request.url.path)
    try:
        response = await client.head(
            f"https://conda.anaconda.org/{channel}/{platform}/{name}",
        )
    except httpx.HTTPError:
        return fastapi.Response()
    return _core.Response(
        response.content,
        response.status_code,
        response.headers,
    )


async def _get_repodata(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    request: fastapi.Request,
    headers: _models.RepodataHeaders,
    label: str | None = None,
) -> fastapi.Response:
    name = posixpath.basename(request.url.path)
    urls = _utils.urls(channel, platform, name, label)
    media_type, _ = mimetypes.guess_type(name)
    return await _core.stream(
        urls,
        headers=_to_dict(headers),
        media_type=media_type,
    )


def _to_dict(obj: pydantic.BaseModel) -> dict[str, str]:
    return {
        k.replace("_", "-"): v
        for k, v in obj.model_dump(exclude_none=True).items()
    }
