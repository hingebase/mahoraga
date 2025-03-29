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

import collections
import http
import posixpath
from typing import Annotated, Literal

import fastapi
import kiss_headers

from mahoraga import _core

router = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/{project}/")
async def get_pypi_project(
    project: str,
    accept: Annotated[
        str | None,
        fastapi.Header(
            description="See [PEP 691](https://peps.python.org/pep-0691/)",
        ),
    ] = None,
) -> fastapi.Response:
    ctx = _core.context.get()
    media_type = _decide_content_type(accept)
    if media_type == "application/vnd.pypi.simple.v1+json":
        urls = [
            posixpath.join(str(url), "simple", project) + "/"
            for url in ctx["config"].upstream.pypi.json_
        ]
    else:
        urls = [
            posixpath.join(str(url), "simple", project) + "/"
            for url in ctx["config"].upstream.pypi.all()
        ]
    return await _core.stream(
        urls,
        headers={"Accept": media_type},
        media_type=media_type,
    )


def _decide_content_type(accept: str | None) -> Literal[
    "application/vnd.pypi.simple.v1+json",
    "application/vnd.pypi.simple.v1+html",
    "text/html",
]:
    if not accept:
        return "application/vnd.pypi.simple.v1+html"
    g: collections.defaultdict[float | None, set[str | None]]
    g = collections.defaultdict(set)
    match kiss_headers.get_polymorphic(
        kiss_headers.parse_it("Accept: " + accept),
        kiss_headers.Accept,
    ):
        case list(headers):
            for h in headers:
                g[h.get_qualifier()].add(h.get_mime())
        case None:
            _core.unreachable()
        case h:
            g[h.get_qualifier()].add(h.get_mime())
    for _, v in sorted(g.items(), reverse=True):
        if (
            "application/vnd.pypi.simple.v1+json" in v
            or "application/vnd.pypi.simple.latest+json" in v
        ):
            return "application/vnd.pypi.simple.v1+json"
        if (
            "application/vnd.pypi.simple.v1+html" in v
            or "application/vnd.pypi.simple.latest+html" in v
            or "application/*" in v
            or "*/*" in v
        ):
            return "application/vnd.pypi.simple.v1+html"
        if "text/html" in v or "text/*" in v:
            return "text/html"
    raise fastapi.HTTPException(http.HTTPStatus.NOT_ACCEPTABLE)
