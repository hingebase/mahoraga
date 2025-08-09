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

__all__ = ["Metadata", "router"]

import contextlib
import logging
import pathlib
from typing import TYPE_CHECKING, Annotated, Literal, Self, TypedDict

import anyio
import fastapi
import pooch  # pyright: ignore[reportMissingTypeStubs]
import pydantic

from mahoraga import _core

from . import _utils

if TYPE_CHECKING:
    from _typeshed import StrPath

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/@bokeh/{package}/{path:path}")
@router.get("/@holoviz/{package}/{path:path}")
@router.get("/@pyscript/{package}/{path:path}")
@router.get("/@stlite/{package}/{path:path}")
# Must be the last
@router.get("/@material-design-icons/{package}/{path:path}")
async def get_scoped_npm_file(
    package: Annotated[str, fastapi.Path(pattern=r"^[^@]+@[^@]+$")],
    path: Annotated[str, fastapi.Path(pattern=r"^[^/]")],
    request: fastapi.Request,
) -> fastapi.Response:
    return await get_npm_file(package, path, request)


@router.get("/{package}/{path:path}")
async def get_npm_file(
    package: Annotated[str, fastapi.Path(pattern=r"^[^@]+@[^@]+$")],
    path: Annotated[str, fastapi.Path(pattern=r"^[^/]")],
    request: fastapi.Request,
) -> fastapi.Response:
    cache_location = pathlib.Path(request.url.path.lstrip("/"))
    ctx = _core.context.get()
    locks = ctx["locks"]
    lock = locks[str(cache_location)]
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(lock)
        if cache_location.is_file():
            return fastapi.responses.FileResponse(
                cache_location,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        prefix = request.url.path.removeprefix("/npm")
        if prefix.startswith("/@"):
            scope, _ = prefix[2:].split("/", 1)
        elif package.startswith(("pyodide@", "swagger-ui-dist@")):
            scope = None
        else:
            return fastapi.Response(status_code=404)
        package, version = package.split("@")
        if scope:
            package = f"@{scope}/{package}"
        resolved = await _Resolved.fetch(
            f"https://data.jsdelivr.com/v1/packages/npm/{package}/resolved",
            "npm",
            package,
            f"{version}.json",
            params={"specifier": version},
        )
        package = f"{package}@{resolved.version}"
        cache_location = pathlib.Path("npm", package, path)
        lock2 = locks[str(cache_location)]
        if lock2 is not lock:
            await stack.enter_async_context(lock2)
        if cache_location.is_file():
            return fastapi.responses.FileResponse(
                cache_location,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        return await _utils.get_npm_file(
            resolved.links["self"],
            package,
            path,
            cache_location,
            stack,
        )
    return _core.unreachable()


class _Base(pydantic.BaseModel):
    type: Literal["npm"]
    name: str
    version: str

    @classmethod
    async def fetch(cls, url: str, *args: "StrPath", **kwargs: object) -> Self:
        cache_location = anyio.Path(*args)
        ctx = _core.context.get()
        async with ctx["locks"][str(cache_location)]:
            try:
                return cls.model_validate_json(
                    await cache_location.read_text("utf-8"),
                )
            except (OSError, pydantic.ValidationError):
                raw = await _core.get(url, **kwargs)
                self = cls.model_validate_json(raw)
                try:
                    pooch.utils.make_local_storage(cache_location.parent)  # pyright: ignore[reportUnknownMemberType]
                    await cache_location.write_bytes(raw)
                except OSError:
                    _logger.warning("Failed to cache %s", url, exc_info=True)
                return self


class _File(TypedDict):
    name: str
    hash: str
    size: int


class _MetadataLinks(TypedDict):
    entrypoints: str
    stats: str


class Metadata(_Base):
    default: str | None
    files: list[_File]
    links: _MetadataLinks


class _ResolvedLinks(_MetadataLinks):
    self: str


class _Resolved(_Base):
    links: _ResolvedLinks


_logger = logging.getLogger("mahoraga")
