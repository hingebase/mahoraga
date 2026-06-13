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

import abc
import collections
import dataclasses
import datetime
import os
import pathlib
import re
import subprocess  # noqa: S404
import time
from typing import TYPE_CHECKING, ClassVar, override

import pooch.typing  # pyright: ignore[reportMissingTypeStubs]
import pydantic
import pydantic_settings
import pygit2
import ziafont

if TYPE_CHECKING:
    from zensical.extensions.macros import MacroEnv


def define_env(env: MacroEnv) -> None:
    release = _PythonBuildStandalone()
    for asset in release.assets:
        name = asset.name
        if name.startswith("cpython-3.14."):
            python_version = name[8 : name.index("+")]
            break
    else:
        raise RuntimeError
    for line in subprocess.check_output(  # noqa: S603
        [
            os.getenv("UV", "uv"),
            "pip", "compile",
            "--group", "docs",
            "--no-annotate",
            "--no-deps",
            "--no-header",
        ],
        encoding="ascii",
    ).splitlines():
        k, v = line.split("==")
        env.variables[f"{k}_version".replace("-", "_")] = v.rstrip()
    mahoraga_base_url = os.getenv("MAHORAGA_BASE_URL", "").rstrip("/")
    env.variables.update({
        "changelog": _changelog(),
        "mahoraga_base_url": mahoraga_base_url or "http://127.0.0.1:3450",
        "mahoraga_version": _Mahoraga().version,
        "pymanager_version": _PyManager().tag_name,
        "python_build_standalone_tag": release.tag_name,
        "python_version": python_version,
        "python_version_short": "".join(python_version.split(".")[:2]),
        "readme": pathlib.Path("README.md")
                         .read_text("utf-8")
                         .partition(" [Docs]")[0],
    })
    images = pathlib.Path(env.conf["site_dir"], "assets", "images")

    # These URLs point to the main branch and the hashes will expire on
    # each commit. Replace them once there is a new GitHub Release.
    pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
        "https://notofonts.github.io/devanagari/fonts/NotoSansDevanagariUI/hinted/ttf/NotoSansDevanagariUI-ExtraCondensed.ttf",
        known_hash="2bb9d27504211ed8ff73ed5287d8eb4ed109d9b91eccec820f8805a4cd3563d7",
        processor=_Renderer(images / "favicon.svg", size=8, color="#6b8e7b"),
    )
    pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
        "https://notofonts.github.io/devanagari/fonts/NotoSansDevanagariUI/hinted/ttf/NotoSansDevanagariUI-ExtraCondensedThin.ttf",
        known_hash="2df029a23387909bf16d684b3089af0e8835ed74d11346cff0aadabbdca0603b",
        processor=_Renderer(images / "logo.svg", size=24, color="white"),
    )


class _Asset(pydantic.BaseModel, extra="ignore"):
    name: str


class _BaseSettings(pydantic_settings.BaseSettings, extra="ignore"):
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
        return (cls.settings_source(),)

    @classmethod
    @abc.abstractmethod
    def settings_source(cls) -> pydantic_settings.PydanticBaseSettingsSource:
        raise NotImplementedError


class _Mahoraga(_BaseSettings, pyproject_toml_table_header=("project",)):
    version: str = ""

    @override
    @classmethod
    def settings_source(cls) -> pydantic_settings.PydanticBaseSettingsSource:
        return pydantic_settings.PyprojectTomlConfigSettingsSource(cls)


class _PyManager(_BaseSettings, json_file_encoding="utf-8"):
    github_repo: ClassVar[str] = "python/pymanager"
    tag_name: str = ""

    @override
    @classmethod
    def settings_source(cls) -> pydantic_settings.PydanticBaseSettingsSource:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if gh_token := os.getenv("GH_TOKEN"):
            headers["Authorization"] = f"Bearer {gh_token}"
        json_file = pooch.retrieve(  # pyright: ignore[reportUnknownMemberType]
            f"https://api.github.com/repos/{cls.github_repo}/releases/latest",
            path=pooch.os_cache("pooch") / time.strftime("%Y.%m.%d"),
            downloader=pooch.HTTPDownloader(headers=headers),  # pyright: ignore[reportArgumentType]
        )
        return pydantic_settings.JsonConfigSettingsSource(cls, json_file)


class _PythonBuildStandalone(_PyManager):
    assets: list[_Asset] = []
    github_repo: ClassVar[str] = "astral-sh/python-build-standalone"


@dataclasses.dataclass
class _Renderer(pooch.typing.Processor):  # pyright: ignore[reportGeneralTypeIssues, reportUntypedBaseClass]
    svg: pathlib.Path
    size: float
    color: str

    def __call__(
        self,
        fname: str,
        action: pooch.typing.Action,
        pooch: pooch.Pooch | None,
    ) -> None:
        if self.svg.is_file():
            del action, pooch
            return
        self.svg.parent.mkdir(parents=True, exist_ok=True)
        text = ziafont.font.Text(
            "\u092e\u0939\u094b\u0930\u0917",
            font=fname,
            size=self.size,
            color=self.color,
        )
        self.svg.write_text(text.svg(), encoding="utf-8")


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
            title = f"{tag} ({commit_time:%Y-%m-%d}) {{#{tag}}}"
            section = collections.defaultdict(list)
            sections.append((title, section))
            if tag == "0.4.0":
                break
    if not sections[0][1]:
        sections.pop(0)
    return sections
