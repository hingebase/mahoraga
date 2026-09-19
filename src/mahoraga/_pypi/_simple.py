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

__all__ = ["router"]

import asyncio
import contextlib
import contextvars
import http
import posixpath
from typing import Annotated, Literal

import fastapi
import werkzeug.datastructures as ds
import werkzeug.http

from mahoraga import _core

from . import _models  # ruff: ignore[typing-only-first-party-import]

router: fastapi.APIRouter = fastapi.APIRouter(route_class=_core.APIRoute)


@router.get("/{project}/")
async def get_pypi_project(
    project: _models.NormalizedName,
    accept: Annotated[
        str | None,
        fastapi.Header(
            description="See [PEP 691](https://peps.python.org/pep-0691/)",
        ),
    ] = None,
    *,
    micropip: Annotated[bool, fastapi.Query()] = False,
) -> fastapi.Response:
    ctx = contextvars.copy_context()
    match ctx[_core.context]:
        case {"config": config, "locks": locks}:
            pass
        case _:
            _core.unreachable()
    if micropip or not config.upstream.pypi.json_:
        media_type = "application/vnd.pypi.simple.v1+html"
    else:
        media_type = _decide_content_type(accept)
    if media_type == "application/vnd.pypi.simple.v1+json":
        urls = [
            posixpath.join(str(url), "simple", project) + "/"
            for url in config.upstream.pypi.json_
        ]
    else:
        urls = [
            posixpath.join(str(url), "simple", project) + "/"
            for url in config.upstream.pypi.all()
        ]
    ctx.run(_core.cache_action.set, "cache-or-fetch")
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(locks[f"{project}|{media_type}"])
        return await asyncio.create_task(
            _core.stream(
                urls,
                headers={"Accept": media_type},
                media_type=media_type,
                stack=stack,
            ),
            context=ctx,
        )


def _decide_content_type(accept: str | None) -> Literal[
    "application/vnd.pypi.simple.v1+json",
    "application/vnd.pypi.simple.v1+html",
    "text/html",
]:
    if not accept:
        return "application/vnd.pypi.simple.v1+html"
    mime_accept = werkzeug.http.parse_accept_header(accept, ds.MIMEAccept)
    while True:
        match mime_accept.best_match((
            "application/vnd.pypi.simple.v1+json",
            "application/vnd.pypi.simple.latest+json",
            "application/vnd.pypi.simple.v1+html",
            "application/vnd.pypi.simple.latest+html",
            "text/html",
        )):
            case (
                "application/vnd.pypi.simple.v1+json"
                | "application/vnd.pypi.simple.latest+json"
            ):
                it = iter(mime_accept)
                for i, (item, q) in enumerate(it):
                    if not ("application/*" != item != "*/*"):
                        vals = mime_accept[:i]
                        vals.append(("application/vnd.pypi.simple.v1+html", q))
                        break
                else:
                    return "application/vnd.pypi.simple.v1+json"
                for item, q in it:
                    if "application/*" != item != "*/*":
                        vals.append((item, q))
                    else:
                        vals.append(("application/vnd.pypi.simple.v1+html", q))
                mime_accept = ds.MIMEAccept(vals)
            case (
                "application/vnd.pypi.simple.v1+html"
                | "application/vnd.pypi.simple.latest+html"
            ):
                return "application/vnd.pypi.simple.v1+html"
            case "text/html":
                return "text/html"
            case _:
                raise fastapi.HTTPException(http.HTTPStatus.NOT_ACCEPTABLE)
