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

__all__ = ["router", "split_repo"]

import asyncio
import compression.zstd
import hashlib
import json
import logging
import pathlib
import shutil
from typing import Annotated, Any

import fastapi.responses
import msgpack
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]
import rattler.platform

from mahoraga import _core

from . import _models, _utils

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get(
    "/{channel}/{platform}/repodata_shards.msgpack.zst",
    dependencies=_core.hourly,
)
async def get_sharded_repodata_index(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
) -> fastapi.Response:
    return fastapi.responses.FileResponse(
        f"channels/{channel}/{platform}/repodata_shards.msgpack.zst",
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


@router.get(
    "/{channel}/{platform}/shards/{name}",
    dependencies=_core.immutable,
)
async def get_sharded_repodata(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    name: Annotated[str, fastapi.Path(pattern=r"\.msgpack\.zst$")],
) -> fastapi.Response:
    return fastapi.responses.FileResponse(
        f"channels/{channel}/{platform}/shards/{name}",
    )


@router.get(
    "/{channel}/label/{label}/{platform}/shards/{name}",
    dependencies=_core.immutable,
)
async def get_sharded_repodata_with_label(
    channel: str,
    label: str,
    platform: rattler.platform.PlatformLiteral,
    name: Annotated[str, fastapi.Path(pattern=r"\.msgpack\.zst$")],
) -> fastapi.Response:
    return fastapi.responses.FileResponse(
        f"channels/{channel}/label/{label}/{platform}/shards/{name}",
    )


async def split_repo() -> None:  # noqa: RUF029
    ctx = _core.context.get()
    cfg = ctx["config"]
    if any(cfg.shard.values()):
        executor = ctx["process_pool"]
        for channel, platforms in cfg.shard.items():
            for platform in platforms:
                executor.submit(_worker, cfg, channel, platform)


def _packages(
    package_name: rattler.PackageName,
    package_format_selection: rattler.PackageFormatSelection,
    repodata: rattler.SparseRepoData,
    run_exports: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    shards: dict[str, dict[str, Any]] = {}
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
            filename = record.file_name
            if entry := run_exports.get(filename):
                new["run_exports"] = entry["run_exports"]
            shards[filename] = new
    return shards


def _sha256(
    name: str,
    repodata: rattler.SparseRepoData,
    root: pathlib.Path,
    run_exports: _models.RunExports,
) -> bytes:
    package_name = rattler.PackageName(name)
    shard: _models.Shard = {
        "packages": _packages(
            package_name,
            rattler.PackageFormatSelection.ONLY_TAR_BZ2,
            repodata,
            run_exports["packages"],
        ),
        "packages.conda": _packages(
            package_name,
            rattler.PackageFormatSelection.ONLY_CONDA,
            repodata,
            run_exports["packages.conda"],
        ),
        "removed": [],
    }
    with pooch.utils.temporary_file(root) as tmp:  # pyright: ignore[reportUnknownMemberType]
        with pathlib.Path(tmp).open("w+b") as f:
            # https://github.com/conda/rattler/blob/py-rattler-v0.18.0/crates/rattler_index/src/lib.rs#L826
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
    root = pathlib.Path("channels", channel, platform, "shards")
    root.mkdir(parents=True, exist_ok=True)
    json_file = root.with_name("run_exports.json.zst")
    try:
        new = pooch.retrieve(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            f"https://{_utils.prefix(channel)}/{platform}/run_exports.json.zst",
            known_hash=None,
            path=root.parent,
        )
    except OSError:
        pass
    else:
        json_file.unlink(missing_ok=True)
        shutil.move(new, json_file)
    try:
        f = compression.zstd.ZstdFile(json_file)
    except OSError:
        run_exports: _models.RunExports = {
            "packages": {},
            "packages.conda": {},
        }
    else:
        with f:
            run_exports = json.load(f)
    with asyncio.run(
        _utils.fetch_repo_data(
            channel,
            platform,
            client=cfg.server.rattler_client(),
        ),
        debug=cfg.log.level == "debug",
        loop_factory=cfg.loop_factory,
    ) as repodata:
        sharded_repodata: _models.ShardedRepodata = {
            "info": {
                "base_url": ".",
                "shards_base_url": "./shards/",
                "subdir": platform,
            },
            "shards": {
                name: _sha256(name, repodata, root, run_exports)
                for name in repodata.package_names()
            },
        }
    dst = root.with_name("repodata_shards.msgpack.zst")
    with pooch.utils.temporary_file(root.parent) as tmp:  # pyright: ignore[reportUnknownMemberType]
        with compression.zstd.ZstdFile(tmp, "w", level=19) as f:
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
