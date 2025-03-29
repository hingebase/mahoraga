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

__all__ = ["fetch_repo_data", "urls"]

import itertools
import posixpath
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

import rattler.exceptions
import rattler.networking
import rattler.platform
import rattler.rattler

from mahoraga import _core

if TYPE_CHECKING:
    from _typeshed import StrPath


async def fetch_repo_data(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    *,
    client: rattler.Client | None = None,
    label: str | None = None,
) -> rattler.SparseRepoData:
    if not client:
        ctx = _core.context.get()
        client = ctx["config"].server.rattler_client()
    if label:
        channel = f"{channel}/label/{label}"
    channels = [rattler.Channel(channel)]
    platforms = [rattler.Platform(platform)]
    try:
        [repodata] = await _fetch_repo_data(
            channels=channels,
            platforms=platforms,
            cache_path="repodata-cache",
            callback=None,
            client=client,
        )
    except rattler.exceptions.FetchRepoDataError:
        [repodata] = await rattler.fetch_repo_data(
            channels=channels,
            platforms=platforms,
            cache_path="repodata-cache",
            callback=None,
            fetch_options=_fetch_options,
        )
    return repodata


def urls(
    channel: str,
    platform: rattler.platform.PlatformLiteral,
    name: str,
    label: str | None = None,
) -> list[str]:
    ctx = _core.context.get()
    cfg = ctx["config"].upstream.conda
    if label:
        return [
            posixpath.join(str(url), channel, "label", label, platform, name)
            for url in itertools.chain(
                cfg.default,
                _getitem(cfg.with_label, channel),
            )
        ]
    return [
        posixpath.join(str(url), channel, platform, name)
        for url in itertools.chain(
            cfg.default,
            _getitem(cfg.with_label, channel),
            _getitem(cfg.without_label, channel),
        )
    ]


async def _fetch_repo_data(  # noqa: PLR0913
    *,
    channels: list[rattler.Channel],
    platforms: list[rattler.Platform],
    cache_path: "StrPath",
    callback: Callable[[int, int], None] | None,
    client: rattler.Client | None = None,
    fetch_options: rattler.networking.FetchRepoDataOptions | None = None,
) -> list[rattler.SparseRepoData]:
    fetch_options = fetch_options or rattler.networking.FetchRepoDataOptions()
    repo_data_list = await rattler.rattler.py_fetch_repo_data(  # pyright: ignore[]
        [channel._channel for channel in channels],  # noqa: SLF001  # pyright: ignore[]
        [platform._inner for platform in platforms],  # noqa: SLF001  # pyright: ignore[]
        cache_path,
        callback,
        client._client if client else None,  # noqa: SLF001  # pyright: ignore[]
        fetch_options._into_py(),  # noqa: SLF001  # pyright: ignore[]
    )
    return [
        rattler.SparseRepoData._from_py_sparse_repo_data(repo_data)  # noqa: SLF001  # pyright: ignore[]
        for repo_data in repo_data_list  # pyright: ignore[reportUnknownVariableType]
    ]


def _getitem[T](mapping: Mapping[str, str | list[T]], key: str) -> Sequence[T]:
    seen = {key}
    value = mapping.get(key, ())
    while isinstance(value, str):
        if value in seen:
            raise RecursionError
        seen.add(value)
        value = mapping.get(value, ())
    return value


_fetch_options = rattler.networking.FetchRepoDataOptions(
    cache_action="force-cache-only",
)
