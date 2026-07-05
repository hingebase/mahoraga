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

__all__ = ["router", "split_repo"]

import asyncio
import compression.zstd
import contextlib
import contextvars
import hashlib
import logging
import pathlib
import shutil
from typing import TYPE_CHECKING, Any

import anyio
import fastapi.responses
import httpx
import msgpack
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]
import rattler.platform

from mahoraga import _core

from . import _models, _utils

if TYPE_CHECKING:
    from distributed import Client, Future

router: fastapi.APIRouter = fastapi.APIRouter(route_class=_core.APIRoute)


@router.head("/{channel}/{platform}/repodata_shards.msgpack.zst")
async def check_sharded_repodata_availability(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
) -> fastapi.Response:
    cache_location = _cache_location(channel, platform)
    if await cache_location.is_file():
        return fastapi.Response()
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    prefix = _utils.prefix(channel, ctx["config"])
    try:
        response = await client.head(
            f"{prefix}/{platform}/repodata_shards.msgpack.zst",
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return fastapi.Response()
    return _core.Response(
        response.content,
        response.status_code,
        response.headers,
    )


@router.head("/{channel}/label/{label}/{platform}/repodata_shards.msgpack.zst")
async def check_sharded_repodata_availability_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
) -> fastapi.Response:
    cache_location = _cache_location(channel, "label", label, platform)
    status_code = 200 if await cache_location.is_file() else 404
    return fastapi.Response(status_code=status_code)


@router.get(
    "/{channel}/{platform}/repodata_shards.msgpack.zst",
    dependencies=_core.hourly,
)
async def get_sharded_repodata_index(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
) -> fastapi.Response:
    cache_location = _cache_location(channel, platform)
    if await cache_location.is_file():
        return fastapi.responses.FileResponse(cache_location)
    ctx = contextvars.copy_context()
    lock = ctx[_core.context]["locks"][str(cache_location)]
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(lock)
        return await asyncio.create_task(
            _core.stream(
                f"{_utils.prefix(channel)}/{platform}/repodata_shards.msgpack.zst",
                stack=stack,
            ),
            context=ctx,
        )


@router.get(
    "/{channel}/label/{label}/{platform}/repodata_shards.msgpack.zst",
    dependencies=_core.hourly,
)
async def get_sharded_repodata_index_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
) -> fastapi.Response:
    return fastapi.responses.FileResponse(
        f"channels/{channel}/label/{label}/{platform}/repodata_shards.msgpack.zst",
    )


def split_repo(
    loop: asyncio.AbstractEventLoop,
    cfg: _core.Config,
    client: Client,
    futures: set[asyncio.Future[Any] | Future[Any]],
) -> None:
    loop.call_later(3600., split_repo, loop, cfg, client, futures)
    for channel, platforms in cfg.shard.items():
        for platform in platforms:
            fut = client.submit(_worker, cfg, channel, platform)  # pyright: ignore[reportUnknownMemberType]
            futures.add(fut)
            fut.add_done_callback(futures.discard)  # pyright: ignore[reportUnknownMemberType]


def _cache_location(*segments: str) -> anyio.Path:
    return anyio.Path("channels", *segments, "repodata_shards.msgpack.zst")


def _packages(
    package_name: rattler.PackageName,
    package_format_selection: rattler.PackageFormatSelection,
    repodata: rattler.SparseRepoData,
) -> dict[str, dict[str, Any]]:
    shards: list[tuple[str, dict[str, Any]]] = []
    for record in repodata.load_records(
        package_name,
        package_format_selection,
    ):
        old = _models.PackageRecord.model_validate_json(record.to_json())
        if new := old.__pydantic_extra__:
            if old.md5:
                new["md5"] = bytes.fromhex(old.md5)
            if old.sha256:
                new["sha256"] = bytes.fromhex(old.sha256)
            shards.append((record.file_name, new))
    shards.sort()  # https://github.com/conda/rattler/pull/2553
    return dict(shards)


def _sha256(
    name: str,
    repodata: rattler.SparseRepoData,
    root: pathlib.Path,
) -> bytes:
    package_name = rattler.PackageName(name)
    shard: _models.Shard = {
        "packages": _packages(
            package_name,
            rattler.PackageFormatSelection.ONLY_TAR_BZ2,
            repodata,
        ),
        "packages.conda": _packages(
            package_name,
            rattler.PackageFormatSelection.ONLY_CONDA,
            repodata,
        ),
        "removed": [],
    }
    with pooch.utils.temporary_file(root) as tmp:  # pyright: ignore[reportUnknownMemberType]
        with pathlib.Path(tmp).open("w+b") as f:
            with compression.zstd.ZstdFile(f, "w") as g:
                msgpack.dump(shard, g)
            f.seek(0)
            h = hashlib.file_digest(f, "sha256")
        dst = root / f"{h.hexdigest()}.msgpack.zst"
        dst.unlink(missing_ok=True)
        shutil.move(tmp, dst)
    return h.digest()


def _split_repo(
    cfg: _core.Config,
    channel: str,
    platform: rattler.platform.PlatformLiteral,
) -> None:
    root = pathlib.Path("channels", channel, platform)
    root.mkdir(parents=True, exist_ok=True)
    with asyncio.run(
        _utils.fetch_repo_data(channel, platform, cfg),
        debug=cfg.log.level == "debug",
        loop_factory=cfg.loop_factory,
    ) as repodata:
        sharded_repodata: _models.ShardedRepodata = {
            "info": {
                "base_url": ".",
                "shards_base_url": "./",
                "subdir": platform,
            },
            "shards": {
                name: _sha256(name, repodata, root)
                for name in repodata.package_names()
            },
        }
    dst = root / "repodata_shards.msgpack.zst"
    with pooch.utils.temporary_file(root) as tmp:  # pyright: ignore[reportUnknownMemberType]
        with compression.zstd.ZstdFile(tmp, "w") as f:
            msgpack.dump(sharded_repodata, f)
        dst.unlink(missing_ok=True)
        shutil.move(tmp, dst)


def _worker(
    cfg: _core.Config,
    channel: str,
    platform: rattler.platform.PlatformLiteral,
) -> None:
    try:
        _split_repo(cfg, channel, platform)
    except Exception:
        _logger.exception(
            "Failed to update %s/%s/repodata_shards.msgpack.zst",
            channel,
            platform,
        )
    else:
        _logger.info(
            "Successfully updated %s/%s/repodata_shards.msgpack.zst",
            channel,
            platform,
        )


_logger = logging.getLogger("mahoraga")
