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
import posixpath
import shutil
from typing import TYPE_CHECKING, Annotated, Any

import anyio
import fastapi.responses
import httpx2
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
    platform: rattler.platform.SubdirLiteral,
) -> fastapi.Response:
    return await _check_sharded_repodata_availability(channel, platform)


@router.head("/{channel}/label/{label}/{platform}/repodata_shards.msgpack.zst")
async def check_sharded_repodata_availability_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.SubdirLiteral,
) -> fastapi.Response:
    return await _check_sharded_repodata_availability(
        channel, "label", label, platform)


@router.get(
    "/{channel}/{platform}/repodata_shards.msgpack.zst",
    dependencies=_core.hourly,
)
async def get_sharded_repodata_index(
    channel: str,
    platform: rattler.platform.SubdirLiteral,
) -> fastapi.Response:
    return await _get_sharded_repodata_index(channel, platform)


@router.get(
    "/{channel}/label/{label}/{platform}/repodata_shards.msgpack.zst",
    dependencies=_core.hourly,
)
async def get_sharded_repodata_index_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.SubdirLiteral,
) -> fastapi.Response:
    return await _get_sharded_repodata_index(channel, "label", label, platform)


@router.get(
    "/{channel}/{platform}/shards/{name}",
    dependencies=_core.immutable,
)
async def get_individual_shard(
    channel: str,
    platform: rattler.platform.SubdirLiteral,
    name: Annotated[str, fastapi.Path(pattern=r"^[a-f\d]{64}\.msgpack\.zst$")],
) -> fastapi.Response:
    return await _get_individual_shard(channel, platform, "shards", name=name)


@router.get(
    "/{channel}/label/{label}/{platform}/shards/{name}",
    dependencies=_core.immutable,
)
async def get_individual_shard_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.SubdirLiteral,
    name: Annotated[str, fastapi.Path(pattern=r"^[a-f\d]{64}\.msgpack\.zst$")],
) -> fastapi.Response:
    return await _get_individual_shard(
        channel, "label", label, platform, "shards", name=name)


def split_repo(
    loop: asyncio.AbstractEventLoop,
    cfg: _core.Config,
    client: Client,
    futures: set[asyncio.Future[Any] | Future[Any]],
) -> None:
    loop.call_later(3600., split_repo, loop, cfg, client, futures)
    for channel, channel_config in cfg.shard.items():
        channel_relations: _models.ChannelRelations = {}
        if base := channel_config.base:
            channel_relations["base"] = base
        if overrides := channel_config.overrides:
            channel_relations["overrides"] = overrides
        for platform in channel_config.platforms:
            fut = client.submit(  # pyright: ignore[reportUnknownMemberType]
                _worker, cfg, channel, platform, channel_relations)
            futures.add(fut)
            fut.add_done_callback(futures.discard)  # pyright: ignore[reportUnknownMemberType]


def _cache_location(
    *segments: str,
    name: str = "repodata_shards.msgpack.zst",
) -> anyio.Path:
    return anyio.Path("channels", *segments, name)


async def _check_sharded_repodata_availability(
    channel: str,
    *segments: str,
) -> fastapi.Response:
    cache_location = _cache_location(channel, *segments)
    if await cache_location.is_file():
        return fastapi.Response()
    ctx = _core.context.get()
    client = ctx["httpx_client"]
    url = posixpath.join(
        _utils.prefix(channel, ctx["config"]),
        *segments,
        "repodata_shards.msgpack.zst",
    )
    try:
        response = await client.head(url, follow_redirects=True)
    except httpx2.HTTPError:
        return fastapi.Response()
    return _core.Response(
        response.content,
        response.status_code,
        response.headers,
    )


async def _get_individual_shard(
    channel: str,
    *segments: str,
    name: str,
) -> fastapi.Response:
    cache_location = _cache_location(channel, *segments, name=name)
    async with contextlib.AsyncExitStack() as stack:
        if await _core.cached_or_locked(cache_location, stack):
            return fastapi.responses.FileResponse(
                cache_location,
                media_type="binary/octet-stream",
            )
        url = posixpath.join(_utils.prefix(channel), *segments, name)
        return await _core.stream(
            url,
            stack=stack,
            cache_location=cache_location,
            sha256=bytes.fromhex(name[:-12]),
        )


async def _get_sharded_repodata_index(
    channel: str,
    *segments: str,
) -> fastapi.Response:
    cache_location = _cache_location(channel, *segments)
    if await cache_location.is_file():
        return fastapi.responses.FileResponse(
            cache_location,
            media_type="binary/octet-stream",
        )
    ctx = contextvars.copy_context()
    # Don't acquire the lock too early
    # A fetched shard index is never cached on disk
    lock = ctx[_core.context]["locks"][str(cache_location)]
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(lock)
        url = posixpath.join(
            _utils.prefix(channel),
            *segments,
            "repodata_shards.msgpack.zst",
        )
        return await asyncio.create_task(
            _core.stream(url, stack=stack),
            context=ctx,
        )


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
    platform: rattler.platform.SubdirLiteral,
    channel_relations: _models.ChannelRelations,
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
                "channel_relations": channel_relations,
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
    platform: rattler.platform.SubdirLiteral,
    channel_relations: _models.ChannelRelations,
) -> None:
    try:
        _split_repo(cfg, channel, platform, channel_relations)
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
