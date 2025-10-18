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

__all__ = ["GitHubRelease", "NPMBase"]

import asyncio
import os
import pathlib
from typing import TYPE_CHECKING, Any, Literal, Self

import pooch  # pyright: ignore[reportMissingTypeStubs]
import pydantic

from mahoraga import _core

if TYPE_CHECKING:
    from _typeshed import StrPath


class _ReleaseAsset(pydantic.BaseModel, extra="ignore"):
    url: str
    name: str
    size: int
    digest: str | None


class GitHubRelease(pydantic.BaseModel, extra="ignore"):
    assets: list[_ReleaseAsset]

    @classmethod
    async def fetch(
        cls,
        *args: StrPath,
        owner: str,
        repo: str,
        tag_name: str,
    ) -> Self:
        if not args:
            _core.unreachable()
        cache_location = pathlib.Path(*args)
        ctx = _core.context.get()
        async with ctx["locks"][str(cache_location)]:
            return await asyncio.to_thread(
                _fetch,
                cls,
                f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag_name}",
                cache_location,
                headers=_headers,
            )


class NPMBase(pydantic.BaseModel):
    type: Literal["npm"]
    name: str
    version: str

    @classmethod
    async def fetch(cls, *args: StrPath, url: str, **kwargs: object) -> Self:
        if not args:
            _core.unreachable()
        cache_location = pathlib.Path(*args)
        ctx = _core.context.get()
        async with ctx["locks"][str(cache_location)]:
            return await asyncio.to_thread(
                _fetch, cls, url, cache_location, **kwargs)


def _fetch[T: pydantic.BaseModel](
    klass: type[T],
    url: str,
    cache_location: pathlib.Path,
    **kwargs: Any,  # noqa: ANN401
) -> T:
    path, fname = os.path.split(cache_location)
    pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
        url,
        known_hash=None,
        fname=fname,
        path=path,
        downloader=pooch.HTTPDownloader(**kwargs),
    )
    json_data = cache_location.read_text(encoding="utf-8")
    try:
        return klass.model_validate_json(json_data)
    except pydantic.ValidationError:
        cache_location.unlink()
        raise


_headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
