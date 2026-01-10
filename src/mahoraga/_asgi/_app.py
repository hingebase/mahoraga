# Copyright 2025-2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__all__ = ["make_app"]

import asyncio
import concurrent.futures
import contextlib
import importlib.metadata
import logging.config
from typing import TYPE_CHECKING, Any, cast

import anysqlite
import fastapi.openapi.docs
import fastapi.responses
import fastapi.templating
import hishel
import httpx
import jinja2
import pooch.utils  # pyright: ignore[reportMissingTypeStubs]
import starlette.middleware.cors
import starlette.staticfiles

from mahoraga import __version__, _conda, _core, _jsdelivr, _pypi, _python, _uv

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

URL_FOR = "{{ url_for('get_npm_file', package='swagger-ui-dist@5', path=%r) }}"


def make_app(cfg: _core.Config, log_config: dict[str, Any]) -> fastapi.FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: fastapi.FastAPI) -> AsyncIterator[_core.Context]:
        async with _core.AsyncClient(
            headers={"User-Agent": f"mahoraga/{__version__}"},
            timeout=httpx.Timeout(15, read=60),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=cfg.server.limit_concurrency,
                keepalive_expiry=cfg.server.keep_alive,
            ),
            storage=hishel.AsyncSqliteStorage(
                connection=await anysqlite.connect(":memory:"),
                default_ttl=600.,
            ),
        ) as client:
            with concurrent.futures.ProcessPoolExecutor(
                initializer=_initializer,
                initargs=(log_config,),
                max_tasks_per_child=1000,
            ) as process_pool:
                if any(cfg.shard.values()):
                    loop = asyncio.get_running_loop()
                    loop.call_soon(_conda.split_repo, loop, cfg, process_pool)
                yield {
                    "config": cfg,
                    "httpx_client": client,
                    "locks": _core.WeakValueDictionary(),
                    "process_pool": process_pool,
                    "statistics": _core.Statistics(
                        backup_servers=cfg.upstream.backup,
                    ),
                }
    meta = importlib.metadata.metadata("mahoraga")
    contact = None
    if urls := meta.get_all("Project-URL"):
        for value in cast("list[str]", urls):
            if value.startswith("Issue Tracker, "):
                name, url = value.split(", ")
                contact = {"name": name, "url": url}
    app = fastapi.FastAPI(
        debug=cfg.log.level == "debug",
        title="Mahoraga",
        summary=meta["Summary"],
        version=meta["Version"],
        dependencies=[fastapi.Depends(_context)],
        default_response_class=_JSONResponse,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        contact=contact,
        license_info={
            "name": "License",
            "identifier": meta["License-Expression"],
        },
    )
    app.add_middleware(
        starlette.middleware.cors.CORSMiddleware,
        allow_origins=cfg.cors.allow_origins,
        allow_methods=cfg.cors.allow_methods,
        allow_headers=cfg.cors.allow_headers,
        allow_credentials=cfg.cors.allow_credentials,
        allow_origin_regex=cfg.cors.allow_origin_regex,
        expose_headers=cfg.cors.expose_headers,
        max_age=cfg.cors.max_age,
    )
    app.include_router(_conda.router, prefix="/conda", tags=["conda"])
    app.include_router(
        _conda.parselmouth,
        prefix="/parselmouth",
        tags=["conda"],
    )
    app.include_router(_jsdelivr.npm, prefix="/npm", tags=["pyodide"])
    app.include_router(_jsdelivr.pyodide, prefix="/pyodide", tags=["pyodide"])
    app.include_router(_pypi.router, prefix="/pypi", tags=["pypi"])
    app.include_router(_python.router, tags=["python"])
    app.include_router(
        _uv.router,  # Must be included after python
        prefix="/uv",
        tags=["uv"],
    )
    app.mount(
        "/static",
        starlette.staticfiles.StaticFiles(packages=[("mahoraga", "_static")]),
        name="static",
    )

    # Private, only for building docs
    app.include_router(_jsdelivr.gh, prefix="/gh", include_in_schema=False)

    res = fastapi.openapi.docs.get_swagger_ui_html(
        openapi_url="{{ url_for('openapi') }}",
        title=app.title,
        swagger_js_url=URL_FOR % "swagger-ui-bundle.js",
        swagger_css_url=URL_FOR % "swagger-ui.css",
        swagger_favicon_url="https://hingebase.github.io/mahoraga/favicon.svg",
        oauth2_redirect_url=URL_FOR % "oauth2-redirect.html",
        init_oauth=app.swagger_ui_init_oauth,
        swagger_ui_parameters=app.swagger_ui_parameters,
    )
    env = jinja2.Environment(autoescape=True)
    template = env.from_string(str(res.body, res.charset))
    name = cast("str", template)
    templates = fastapi.templating.Jinja2Templates(env=env)

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui_html(
        request: fastapi.Request,
    ) -> fastapi.responses.HTMLResponse:
        return templates.TemplateResponse(request, name)

    del swagger_ui_html
    return app


class _JSONResponse(fastapi.responses.JSONResponse):
    media_type = None


async def _context(request: fastapi.Request) -> None:  # noqa: RUF029
    _core.context.set(cast("_core.Context", request.scope["state"]))


def _initializer(cfg: dict[str, Any]) -> None:
    logging.config.dictConfig(cfg)
    logging.captureWarnings(capture=True)
    pooch.utils.LOGGER = logging.getLogger("pooch")
