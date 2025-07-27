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

import io
import os
import pathlib
import subprocess  # noqa: S404
import time
from typing import TYPE_CHECKING, Any, cast

import csscompressor  # pyright: ignore[reportMissingTypeStubs]
import jsmin  # pyright: ignore[reportMissingTypeStubs]
import mkdocs_macros.plugin
import pooch  # pyright: ignore[reportMissingTypeStubs]
import pydantic
import pydantic_settings
import requests
from typing_extensions import override  # noqa: UP035

if TYPE_CHECKING:
    from material.plugins.privacy.plugin import (  # pyright: ignore[reportMissingTypeStubs]
        PrivacyPlugin,
    )


def define_env(env: mkdocs_macros.plugin.MacrosPlugin) -> None:
    release = _Release()
    for asset in release.assets:
        name = asset.name
        if name.startswith("cpython-3.13."):
            python_version = name[8 : name.index("+")]
            break
    else:
        raise RuntimeError
    with _open(pathlib.Path("docs", "requirements.txt")) as f:
        for line in f:
            k, v = line.split("==")
            env.variables[f"{k}_version".replace("-", "_")] = v.rstrip()
    env.variables.update({  # pyright: ignore[reportUnknownMemberType]
        "mahoraga_version": _Project().version,
        "pymanager_version": _Tag().name,
        "python_build_standalone_tag": release.tag_name,
        "python_version": python_version,
        "python_version_short": "".join(python_version.split(".")[:2]),
        "readme": pathlib.Path("README.md")
                         .read_text("utf-8")
                         .partition(" [Docs]")[0],
    })
    if not os.getenv("GH_TOKEN"):
        privacy = cast("PrivacyPlugin", env.conf.plugins["material/privacy"])
        privacy.config.assets = True
        requests.get = _get


def on_post_build(env: mkdocs_macros.plugin.MacrosPlugin) -> None:
    site_dir = pathlib.Path(env.conf.site_dir)
    for css in site_dir.glob("assets/external/fonts.googleapis.com/*.css"):
        with css.open("r+", encoding="utf-8") as f:
            s = csscompressor.compress(f.read())  # pyright: ignore[reportUnknownMemberType]
            f.seek(0)
            f.write(s)
            f.truncate()
    for js in site_dir.glob("assets/javascripts/lunr/*.js"):
        with js.open("r+", encoding="utf-8") as f, io.StringIO(f.read()) as g:
            f.seek(0)
            jsmin.JavascriptMinify(g, f).minify()  # pyright: ignore[reportUnknownMemberType]
            f.truncate()
    if os.getenv("GH_TOKEN"):
        (site_dir / ".nojekyll").touch()
        subprocess.run(  # noqa: S603
            ["/usr/bin/chmod", "-R", "a=r,u+w,a+X", site_dir],
            check=True,
        )


class _Asset(pydantic.BaseModel, extra="ignore"):
    name: str


class _JsonConfigSettingsSource(pydantic_settings.JsonConfigSettingsSource):
    @override
    def _read_file(self, file_path: pathlib.Path) -> dict[str, Any]:
        [obj] = cast("list[dict[str, Any]]", super()._read_file(file_path))
        return obj


class _Project(
    pydantic_settings.BaseSettings,
    extra="ignore",
    pyproject_toml_table_header=("project",),
):
    version: str = ""

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        return (
            pydantic_settings.PyprojectTomlConfigSettingsSource(settings_cls),
        )


class _Release(
    pydantic_settings.BaseSettings,
    extra="ignore",
    json_file_encoding="utf-8",
):
    assets: list[_Asset] = []
    tag_name: str = ""

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        j = _retrieve(
            "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest",
        )
        return (pydantic_settings.JsonConfigSettingsSource(settings_cls, j),)


class _Tag(
    pydantic_settings.BaseSettings,
    extra="ignore",
    json_file_encoding="utf-8",
):
    name: str = ""

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        j = _retrieve(
            "https://api.github.com/repos/python/pymanager/tags",
            params={"per_page": "1"},
        )
        return (_JsonConfigSettingsSource(settings_cls, j),)


def _get(
    url: str | bytes,
    params: "requests.sessions._Params | None" = None,  # pyright: ignore[reportPrivateUsage]
    **kwargs: Any,  # noqa: ANN401
) -> requests.Response:
    req = requests.PreparedRequest()
    req.prepare_url(url, params)  # pyright: ignore[reportUnknownMemberType]
    new_url = req.url
    if not new_url:
        raise AssertionError
    if base_url := os.getenv("MAHORAGA_BASE_URL"):
        req.prepare_url(base_url, None)  # pyright: ignore[reportUnknownMemberType]
        if base_url := req.url:
            base_url = base_url.rstrip("/")
            if new_url.startswith("https://cdn.jsdelivr.net/gh/"):
                new_url = f"{base_url}/{new_url[24:]}"
            elif new_url.startswith("https://cdnjs.cloudflare.com/ajax/libs/emojione/"):
                new_url = f"{base_url}/cdnjs{new_url[28:]}"
    with requests.Session() as session:
        return session.get(new_url, **kwargs)


def _open(requirements: pathlib.Path) -> io.TextIOWrapper:
    try:
        return requirements.open(encoding="utf-8")
    except OSError:
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "uv", "pip", "compile",
                "--no-annotate",
                "--no-deps",
                "--no-header",
                "-o", requirements,
                requirements.with_suffix(".in"),
            ],
            check=True,
        )
        return requirements.open(encoding="utf-8")


def _retrieve(url: str, params: object = None) -> str:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if gh_token := os.getenv("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {gh_token}"
    return pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
        url,
        known_hash=None,
        path=pooch.os_cache("pooch") / time.strftime("%Y.%m.%d"),  # pyright: ignore[reportUnknownMemberType]
        downloader=pooch.HTTPDownloader(headers=headers, params=params),
    )
