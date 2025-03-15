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

__all__ = ["make_app"]

import importlib.metadata
from typing import cast

import fastapi.openapi.docs
import fastapi.templating
import jinja2
import pooch  # pyright: ignore[reportMissingTypeStubs]
import starlette.staticfiles

from mahoraga import _conda, _core, _pypi, _python

_DOCS_URL = "/docs"
_URL_FOR = "{{ url_for('swagger_ui_dist', path=%r) }}"


def make_app() -> fastapi.FastAPI:
    ctx = _core.context.get()
    cfg = ctx["config"]
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
        default_response_class=_JSONResponse,
        docs_url=None if cfg.swagger_ui_version else _DOCS_URL,
        redoc_url=None,
        contact=contact,
        license_info={
            "name": "License",
            "identifier": meta["License-Expression"],
        },
    )
    app.include_router(_conda.router, prefix="/conda", tags=["conda"])
    app.include_router(_pypi.router, prefix="/pypi", tags=["pypi"])
    app.include_router(_python.router, tags=["python"])

    if cfg.swagger_ui_version:
        processor = pooch.Untar()
        pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
            f"https://registry.npmmirror.com/swagger-ui-dist/-/swagger-ui-dist-{cfg.swagger_ui_version}.tgz",
            known_hash=None,
            path="swagger-ui-dist",
            processor=processor,
        )
        app.mount(
            "/swagger-ui-dist",
            starlette.staticfiles.StaticFiles(directory=processor.extract_dir),  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            name="swagger_ui_dist",
        )
        res = fastapi.openapi.docs.get_swagger_ui_html(
            openapi_url="{{ url_for('openapi') }}",
            title=app.title + " - Swagger UI",
            swagger_js_url=_URL_FOR % "/package/swagger-ui-bundle.js",
            swagger_css_url=_URL_FOR % "/package/swagger-ui.css",
            swagger_favicon_url=_URL_FOR % "/package/favicon-32x32.png",
            oauth2_redirect_url=_URL_FOR % "/package/oauth2-redirect.html",
            init_oauth=app.swagger_ui_init_oauth,
            swagger_ui_parameters=app.swagger_ui_parameters,
        )
        env = jinja2.Environment(autoescape=True)
        template = env.from_string(str(res.body, res.charset))
        name = cast("str", template)
        templates = fastapi.templating.Jinja2Templates(env=env)

        @app.get(_DOCS_URL, include_in_schema=False)
        async def swagger_ui_html(
            request: fastapi.Request,
        ) -> fastapi.responses.HTMLResponse:
            return templates.TemplateResponse(request, name)

        del swagger_ui_html
    return app


class _JSONResponse(fastapi.responses.JSONResponse):
    media_type = None
