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

import os
import pathlib
import re
import subprocess
import time

import mkdocs_macros.plugin
import pooch  # pyright: ignore[reportMissingTypeStubs]
import pydantic
import pydantic_settings
from typing_extensions import override  # noqa: UP035


def define_env(env: mkdocs_macros.plugin.MacrosPlugin) -> None:
    release = _Release()
    for asset in release.assets:
        name = asset.name
        if name.startswith("cpython-3.12."):
            python_version = name[8 : name.index("+")]
            break
    else:
        raise RuntimeError
    env.variables.update({  # pyright: ignore[reportUnknownMemberType]
        "mahoraga_version": _Project().version,
        "python_build_standalone_tag": release.tag_name,
        "python_version": python_version,
        "python_version_short": "".join(python_version.split(".")[:2]),
        "readme": re.sub(
            r"## Usage[^#]+",
            "",
            pathlib.Path("README.md").read_text("utf-8"),
        ),
    })


def on_post_build(env: mkdocs_macros.plugin.MacrosPlugin) -> None:
    if os.getenv("GH_TOKEN"):
        site_dir = env.conf["site_dir"]
        pathlib.Path(site_dir, ".nojekyll").touch()
        subprocess.run(["chmod", "-R", "a=r,u+w,a+X", site_dir])


class _Asset(pydantic.BaseModel, extra="ignore"):
    name: str


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
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if gh_token := os.getenv("GH_TOKEN"):
            headers["Authorization"] = f"Bearer {gh_token}"
        return (
            pydantic_settings.JsonConfigSettingsSource(
                settings_cls,
                pooch.retrieve(  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                    "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest",
                    known_hash=None,
                    path=pooch.os_cache("pooch") / time.strftime("%Y.%m.%d"),  # pyright: ignore[reportUnknownMemberType]
                    downloader=pooch.HTTPDownloader(headers=headers),
                ),
            ),
        )
