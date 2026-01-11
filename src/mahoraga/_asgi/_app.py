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

import importlib.metadata
import logging
from typing import Annotated, Any, cast

import fastapi.openapi.docs
import fastapi.responses
import fastapi.templating
import jinja2
import pydantic
import starlette.middleware.cors
import starlette.staticfiles

from mahoraga import _conda, _core, _jsdelivr, _pypi, _python, _uv

URL_FOR = "{{ url_for('get_npm_file', package='swagger-ui-dist@5', path=%r) }}"


def make_app(cfg: _core.Config) -> fastapi.FastAPI:
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
        lifespan=cfg.lifespan,
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
    app.add_api_route(
        "/log",
        _log,
        include_in_schema=False,
        response_class=fastapi.responses.JSONResponse,
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


class _LogRecord(pydantic.BaseModel, logging.LogRecord):
    args: Any
    asctime: str = ""
    created: float
    exc_info: Any
    exc_text: str | None
    filename: str
    funcName: str  # noqa: N815
    levelname: str
    levelno: int
    lineno: int
    module: str
    msecs: float
    message: str
    msg: str
    name: str
    pathname: str
    process: int | None
    processName: str | None  # noqa: N815
    relativeCreated: float  # noqa: N815
    stack_info: str | None
    thread: int | None
    threadName: str | None  # noqa: N815
    taskName: str | None  # noqa: N815

    @pydantic.field_validator(
        "args",
        "exc_info",
        "exc_text",
        "process",
        "processName",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        mode="before",
    )
    @classmethod
    def parse_none_str(cls, value: str) -> str | None:
        return None if value == "None" else value


async def _context(request: fastapi.Request) -> None:  # noqa: RUF029
    _core.context.set(cast("_core.Context", request.scope["state"]))


def _log(record: Annotated[_LogRecord, fastapi.Query()]) -> None:
    for handler in _root.handlers:
        handler.handle(record)


_root = logging.getLogger()
