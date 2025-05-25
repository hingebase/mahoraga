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
from typing import Annotated

import fastapi
import rattler.exceptions
import rattler.platform

from mahoraga import _core

from . import _utils

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/{channel}/{platform}/{name}")
async def get_conda_package(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    name: Annotated[str, fastapi.Path(pattern=r"\.(?:conda|tar\.bz2)$")],
) -> fastapi.Response:
    return await _proxy_cache(channel, platform, name)


@router.get("/{channel}/label/{label}/{platform}/{name}")
async def get_conda_package_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
    name: Annotated[str, fastapi.Path(pattern=r"\.(?:conda|tar\.bz2)$")],
) -> fastapi.Response:
    return await _proxy_cache(channel, platform, name, label)


async def _proxy_cache(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    name: str,
    label: str | None = None,
) -> fastapi.Response:
    if name.endswith(".conda"):
        media_type = "application/x-zip-compressed"
        package_format_selection = rattler.PackageFormatSelection.ONLY_CONDA
        suffix = ".conda"
    else:
        media_type, _ = mimetypes.guess_type(name)
        package_format_selection = rattler.PackageFormatSelection.ONLY_TAR_BZ2
        suffix = ".tar.bz2"
    if label:
        cache_location = pathlib.Path(
            "channels", channel, "label", label, platform, name)
    else:
        cache_location = pathlib.Path("channels", channel, platform, name)
    ctx = _core.context.get()
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
        pkg_name, version, build = name.removesuffix(suffix).rsplit("-", 2)
        spec = f"{pkg_name} =={version} {build}"
        try:
            with await _utils.fetch_repo_data(
                channel,
                platform,
                label=label,
            ) as repodata:
                records = repodata.load_matching_records(
                    [rattler.MatchSpec(spec, strict=True)],
                    package_format_selection,
                )
        except rattler.exceptions.FetchRepoDataError:
            return fastapi.Response(status_code=404)
        for record in records:
            if record.file_name == name:
                break
        else:
            return fastapi.Response(status_code=404)
        urls = _utils.urls(channel, platform, name, label)
        if record.sha256:
            return await _core.stream(
                urls,
                media_type=media_type,
                stack=stack,
                cache_location=cache_location,
                sha256=record.sha256,
                size=record.size,
            )
        return await _core.stream(
            urls,
            media_type=media_type,
            stack=stack,
        )
    return _core.unreachable()
