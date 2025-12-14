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
import contextvars
import logging
import mimetypes
import pathlib
import posixpath

import fastapi
import httpx
import pydantic

from mahoraga import _core

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/{name}")
async def get_uv_github_release(name: str) -> fastapi.Response:
    ctx = _core.context.get()
    media_type, _ = mimetypes.guess_type(name)
    tag, sha256, size = await _get_distribution_metadata(name)
    if tag and sha256:
        cache_location = pathlib.Path("uv", tag, name)
        headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        async with contextlib.AsyncExitStack() as stack:
            if await _core.cached_or_locked(cache_location, stack):
                return fastapi.responses.FileResponse(
                    cache_location,
                    headers=headers,
                    media_type=media_type,
                )
            urls = [
                posixpath.join(str(url), tag, name)
                for url in ctx["config"].upstream.uv.tag
            ]
            response = await _core.stream(
                urls,
                headers=headers,
                media_type=media_type,
                stack=stack,
                cache_location=cache_location,
                sha256=sha256,
                size=size,
            )
            if not httpx.codes.is_error(response.status_code):
                return response
    urls = [
        posixpath.join(str(url), name)
        for url in ctx["config"].upstream.uv.latest
    ]
    return await _core.stream(urls, media_type=media_type)


async def _get_distribution_metadata(
    name: str,
) -> tuple[str | None, bytes | None, int | None]:
    ctx = contextvars.copy_context()
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    try:
        async with ctx[_core.context]["locks"]["uv/latest.json"]:
            raw = await asyncio.create_task(
                _core.get(
                    "https://api.github.com/repos/astral-sh/uv/releases/latest",
                    headers=_core.headers,
                ),
                context=ctx,
            )
    except fastapi.HTTPException:
        pass
    else:
        try:
            rel = _core.GitHubRelease.model_validate_json(raw)
        except pydantic.ValidationError:
            _logger.exception("Failed to get GitHub release metadata")
        else:
            for asset in rel.assets:
                if asset.name == name:
                    return rel.tag_name, asset.sha256(), asset.size
            raise fastapi.HTTPException(404)
    if name == "dist-manifest.json":
        return None, None, None
    return await _get_distribution_metadata_from_manifest(name)


async def _get_distribution_metadata_from_manifest(
    name: str,
) -> tuple[str | None, bytes | None, int | None]:
    ctx = _core.context.get()
    urls = [
        posixpath.join(str(url), "dist-manifest.json")
        for url in ctx["config"].upstream.uv.latest
    ]
    try:
        raw = await _core.get(urls)
    except fastapi.HTTPException:
        return None, None, None
    try:
        manifest = _DistributionManifest.model_validate_json(raw)
    except pydantic.ValidationError:
        _logger.exception("Failed to get uv distribution manifest")
        return None, None, None
    try:
        artifact = manifest.artifacts[name]
    except KeyError as e:
        raise fastapi.HTTPException(404) from e
    tag = manifest.announcement_tag
    if hexdigest := artifact.checksums.sha256:
        return tag, bytes.fromhex(hexdigest), None
    sha256 = f"{name}.sha256"
    if sha256 not in manifest.artifacts:
        return tag, None, None
    urls = [
        posixpath.join(str(url), tag, sha256)
        for url in ctx["config"].upstream.uv.tag
    ]
    try:
        raw = await _core.get(urls)
    except fastapi.HTTPException:
        return tag, None, None
    return tag, bytes.fromhex(raw[:64]), None  # pyright: ignore[reportArgumentType]


class _Checksums(pydantic.BaseModel, extra="ignore"):
    sha256: str | None = None


class _Artifact(pydantic.BaseModel, extra="ignore"):
    checksums: _Checksums = _Checksums()


class _DistributionManifest(pydantic.BaseModel, extra="ignore"):
    announcement_tag: str
    artifacts: dict[str, _Artifact]


_logger = logging.getLogger("mahoraga")
