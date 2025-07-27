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

import mimetypes
from typing import Literal

import fastapi
import pydantic_extra_types.semantic_version

from . import _core

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/ajax/libs/emojione/{version}/assets/{fmt}/{name}")
async def emojione(
    version: pydantic_extra_types.semantic_version.SemanticVersion,
    fmt: Literal["svg", "png"],
    name: str,
) -> fastapi.Response:
    urls = [
        f"https://{prefix}/ajax/libs/emojione/{version}/assets/{fmt}/{name}"
        for prefix in ("mirrors.sustech.edu.cn/cdnjs", "cdnjs.cloudflare.com")
    ]
    media_type, _ = mimetypes.guess_type(name)
    return await _core.stream(urls, media_type=media_type)
