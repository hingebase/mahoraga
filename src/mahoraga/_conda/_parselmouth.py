# Copyright 2025-2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

__all__ = ["router"]

import asyncio
import contextlib
import contextvars
from typing import Annotated, Literal

import fastapi

from mahoraga import _core

router: fastapi.APIRouter = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/hash-v0/{sha256}")
async def get_hash_mapping(
    sha256: Annotated[str, fastapi.Path(pattern=r"^[0-9a-f]{64}$")],
    request: fastapi.Request,
) -> fastapi.Response:
    del sha256
    return await _proxy_cache(request)


@router.get("/hash-v0/{channel}/index.json")
async def get_channel_hash_index(
    channel: Literal["conda-forge", "bioconda", "pytorch", "tango-controls"],
    request: fastapi.Request,
) -> fastapi.Response:
    del channel
    return await _proxy_cache(request)


@router.get("/pypi-to-conda-v1/{channel}/{pypi_normalized_name}.json")
async def get_pypi_to_conda_mapping(
    channel: Literal["conda-forge", "bioconda", "pytorch", "tango-controls"],
    pypi_normalized_name: Annotated[
        str,
        # Taken from packaging.utils
        fastapi.Path(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    ],
    request: fastapi.Request,
) -> fastapi.Response:
    del channel, pypi_normalized_name
    return await _proxy_cache(request)


@router.get("/relations-v1/{channel}/relations.jsonl.gz")
async def get_relations_table(
    channel: Literal["conda-forge", "bioconda", "pytorch"],
    request: fastapi.Request,
) -> fastapi.Response:
    del channel
    return await _proxy_cache(request)


@router.get("/relations-v1/{channel}/metadata.json")
async def get_relations_metadata(
    channel: Literal["conda-forge", "bioconda", "pytorch"],
    request: fastapi.Request,
) -> fastapi.Response:
    del channel
    return await _proxy_cache(request)


@router.get("/compressed-v0/compressed_mapping.json")
async def get_legacy_compressed_mapping(
    request: fastapi.Request,
) -> fastapi.Response:
    return await _proxy_cache(request)


@router.get("/compressed-v0/{channel}/compressed_mapping.json")
async def get_legacy_compressed_mapping_per_channel(
    channel: Literal["conda-forge", "bioconda", "pytorch", "tango-controls"],
    request: fastapi.Request,
) -> fastapi.Response:
    del channel
    return await _proxy_cache(request)


async def _proxy_cache(request: fastapi.Request) -> fastapi.Response:
    path = request.url.path.removeprefix("/parselmouth/")
    ctx = contextvars.copy_context()
    lock = ctx[_core.context]["locks"][path]
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(lock)
        return await asyncio.create_task(
            _core.stream(
                f"https://conda-mapping.prefix.dev/{path}",
                stack=stack,
            ),
            context=ctx,
        )
