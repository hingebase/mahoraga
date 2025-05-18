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

__all__ = ["get_npm_file", "urls"]

import base64
import contextlib
import mimetypes
import posixpath
from typing import TYPE_CHECKING

import fastapi

from mahoraga import _core, _jsdelivr

if TYPE_CHECKING:
    from _typeshed import StrPath


async def get_npm_file(
    url: str,
    package: str,
    path: str,
    cache_location: "StrPath",
    stack: contextlib.AsyncExitStack,
) -> fastapi.Response:
    metadata = await _jsdelivr.Metadata.fetch(
        url,
        "npm",
        f"{package}.json",
        params={"structure": "flat"},
    )
    for file in metadata.files:
        if file["name"].lstrip("/") == path:
            break
    else:
        return fastapi.Response(status_code=404)
    media_type, _ = mimetypes.guess_type(path)
    return await _core.stream(
        urls("npm", package, path),
        media_type=media_type,
        stack=stack,
        cache_location=cache_location,
        sha256=base64.b64decode(file["hash"]),
        size=file["size"],
    )


def urls(*paths: str) -> list[str]:
    return [
        posixpath.join(str(url), *paths)
        for url in _core.context.get()["config"].upstream.pyodide
    ]
