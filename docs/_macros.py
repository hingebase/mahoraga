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

import collections
import datetime
import io
import os
import pathlib
import re
import subprocess  # noqa: S404
import time
from typing import TYPE_CHECKING, Any, cast, override

import csscompressor  # pyright: ignore[reportMissingTypeStubs]
import jsmin  # pyright: ignore[reportMissingTypeStubs]
import pooch  # pyright: ignore[reportMissingTypeStubs]
import pydantic
import pydantic_settings
import pygit2
import pyodide_lock
import requests

if TYPE_CHECKING:
    from _typeshed import Incomplete
    from material.plugins.privacy.plugin import (  # pyright: ignore[reportMissingTypeStubs]
        PrivacyPlugin,
    )
    from mkdocs_macros.plugin import MacrosPlugin
    from requests.sessions import (
        _Params,  # pyright: ignore[reportPrivateUsage]
    )


def define_env(env: MacrosPlugin) -> None:
    release = _Release()
    for asset in release.assets:
        name = asset.name
        if name.startswith("cpython-3.14."):
            python_version = name[8 : name.index("+")]
            break
    else:
        raise RuntimeError
    with _open(pathlib.Path("docs", "requirements.txt")) as f:
        for line in f:
            k, v = line.split("==")
            env.variables[f"{k}_version".replace("-", "_")] = v.rstrip()
    env.variables.update({  # pyright: ignore[reportUnknownMemberType]
        "changelog": _changelog(),
        "mahoraga_base_url": os.getenv(
            "MAHORAGA_BASE_URL",
            default="http://127.0.0.1:3450",
        ).rstrip("/"),
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
        requests.get = _get  # ty: ignore[invalid-assignment]
    lock_file = pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
        f"https://cdn.jsdelivr.net/pyodide/v{env.variables['pyodide_py_version']}/full/pyodide-lock.json",
        known_hash=None,
    )
    lock_spec = pyodide_lock.PyodideLockSpec.from_json(pathlib.Path(lock_file))
    env.variables["bokeh_version"] = lock_spec.packages["bokeh"].version


def on_post_build(env: MacrosPlugin) -> None:
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


def _changelog() -> list[tuple[str, collections.defaultdict[str, list[str]]]]:
    repo = pygit2.Repository(".git")
    tags = {
        ref.peel(pygit2.Tag).target: ref.name.removeprefix("refs/tags/v")
        for ref in repo.references.iterator(pygit2.enums.ReferenceFilter.TAGS)
    }
    groups = {
        "\u2728": "\0\u2728 New features",
        "\u26a1": "\1\u26a1 Performance",
        "\U0001f41b": "\2\U0001f41b Bug fixes",
        "\U0001f4dd": "\3\U0001f4dd Documentation",
    }
    pattern = re.compile(r" \(#([1-9]\d*)\)$")
    section: collections.defaultdict[str, list[str]]
    section = collections.defaultdict(list)
    sections = [("Unreleased", section)]
    for commit in repo.walk(repo.head.target):
        try:
            tag = tags[commit.id]
        except KeyError:
            try:
                group = groups[commit.message[0]]
            except KeyError:
                continue
            message = pattern.sub(
                r" ([#\1](https://github.com/hingebase/mahoraga/pull/\1))",
                commit.message[1:].splitlines()[0].strip(),
            )
            section[group].append(message)
        else:
            commit_time = datetime.datetime.fromtimestamp(
                commit.commit_time,
                datetime.UTC,
            )
            title = f"{tag} ({commit_time:%Y-%m-%d})"
            section = collections.defaultdict(list)
            sections.append((title, section))
            if tag == "0.4.0":
                break
    if not sections[0][1]:
        sections.pop(0)
    return sections


def _get(
    url: str | bytes,
    params: _Params | None = None,
    **kwargs: Incomplete,
) -> requests.Response:
    req = requests.PreparedRequest()
    req.prepare_url(url, params)  # pyright: ignore[reportUnknownMemberType]
    if (
        (prepared := req.url)
        and prepared.startswith("https://cdn.jsdelivr.net/")
        and (base_url := os.getenv("MAHORAGA_BASE_URL"))
    ):
        req.prepare_url(base_url, None)  # pyright: ignore[reportUnknownMemberType]
        if prepared_base_url := req.url:
            url = f"{prepared_base_url.rstrip("/")}{prepared[24:]}"
    with requests.Session() as session:
        return session.get(url, **kwargs)


def _open(requirements: pathlib.Path) -> io.TextIOWrapper:
    try:
        return requirements.open(encoding="utf-8")
    except OSError:
        subprocess.run(  # noqa: S603
            [
                os.getenv("UV", "uv"),
                "pip", "compile",
                "--no-annotate",
                "--no-deps",
                "--no-header",
                "-o", requirements,
                requirements.with_suffix(".in"),
            ],
            check=True,
        )
        return requirements.open(encoding="utf-8")


def _retrieve(url: str, params: _Params | None = None) -> str:
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
