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
from typing import Annotated

import fastapi

from mahoraga import _core

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/compressed_mapping.json")
async def get_compressed_mapping() -> fastapi.Response:
    ctx = contextvars.copy_context()
    lock = ctx[_core.context]["locks"]["compressed_mapping.json"]
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(lock)
        return await asyncio.create_task(
            _core.stream(
                "https://api.github.com/repos/prefix-dev/parselmouth/contents/files/compressed_mapping.json",
                headers={
                    "Accept": "application/vnd.github.raw+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                stack=stack,
            ),
            context=ctx,
        )


@router.get("/hash-v0/{sha256}")
async def get_hash_mapping(
    sha256: Annotated[str, fastapi.Path(pattern=r"^[0-9a-f]{64}$")],
) -> fastapi.Response:
    return fastapi.Response(status_code=404)
