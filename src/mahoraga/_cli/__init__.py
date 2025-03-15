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

__all__ = ["main"]

import pathlib
import sys
import urllib.parse
from typing import Annotated

import click
import jinja2
import pydantic
import pydantic_settings
import rich.console
import rich_argparse

from mahoraga import __version__, _asgi, _core


def main() -> None:
    """CLI entry."""
    pydantic_settings.CliApp.run(
        _Main,
        cli_args=["--help"] if len(sys.argv) <= 1 else None,
        cli_settings_source=(
            None if rich.console.detect_legacy_windows()
            else pydantic_settings.CliSettingsSource(  # pyright: ignore[reportUnknownArgumentType]
                _Main,
                formatter_class=rich_argparse.RawDescriptionRichHelpFormatter,
            )
        ),
    )


class _Config(_core.Config, toml_file=None):
    pass


class _New(_core.Server, alias_generator=None):
    """Create a new directory structure for Mahoraga.

    Mahoraga directory structure is relocatable. It's safe to copy the
    whole directory to a different path or machine. Once you've done
    with the `mahoraga.toml` file inside, you don't need to run this
    command again to create another directory.

    Mahoraga directory structure follows semantic versioning. Directory
    created by Mahoraga version X.Y.Z (X>=1) is guaranteed to work under
    any version >=X.Y.Z,<X+1. Once updated to an uncompatible version,
    you have to create a new directory and migrate your settings and
    data by hand.
    """

    root: Annotated[
        pydantic_settings.CliPositionalArg[pydantic.NewPath],
        _core.Doc("Root path of the new directory"),
    ]

    def cli_cmd(self) -> None:
        self.root.mkdir(parents=True)
        root = self.root.resolve(strict=True)
        for subdir in "channels", "log", "repodata-cache":
            (root / subdir).mkdir()

        cfg = _Config().model_dump()
        cfg["server"] = {
            "host": self.host,
            "port": self.port,
            "keep_alive": self.keep_alive,
        }
        cfg["upstream"]["python"] = [
            urllib.parse.unquote(str(url)) for url in cfg["upstream"]["python"]
        ]

        env = jinja2.Environment(
            autoescape=True,
            loader=jinja2.PackageLoader(__name__, package_path=""),
        )
        cfg_file = root / "mahoraga.toml"
        with cfg_file.open("x", encoding="utf-8", newline="") as f:
            print(env.get_template("mahoraga.toml.jinja").render(cfg), file=f)
        click.echo(f"Done. Please edit {cfg_file} before starting the server.")


class _Run(pydantic.BaseModel, validate_default=True):
    """Start Mahoraga server.

    Before starting, make sure you've had all options in `mahoraga.toml`
    set properly. When the server is already running, changes in
    `mahoraga.toml` won't take effect until a restart.
    """

    root: Annotated[
        pydantic.DirectoryPath,
        _core.Doc("Root path of a directory containing mahoraga.toml"),
        _core.Predicate("(input_value / 'mahoraga.toml').is_file()"),
    ] = pathlib.Path()

    def cli_cmd(self) -> None:
        _asgi.run(self.root)


class _Version(pydantic.BaseModel):
    """Show Mahoraga version and exit."""

    def cli_cmd(self) -> None:  # noqa: PLR6301
        click.echo(f"Mahoraga v{__version__}")


def _summary(docstring: str | None) -> str | None:
    return docstring.split(".", 1)[0] if docstring else None


class _Main(
    pydantic_settings.BaseSettings,
    cli_prog_name="mahoraga",
    nested_model_default_partial_update=True,
    case_sensitive=True,
    cli_hide_none_type=True,
    cli_avoid_json=True,
    cli_enforce_required=True,
    cli_implicit_flags=True,
    cli_kebab_case=True,
):
    """Reverse proxy for Python mirrors."""

    new: Annotated[
        pydantic_settings.CliSubCommand[_New],
        pydantic.Field(description=_summary(_New.__doc__)),
    ]
    run: Annotated[
        pydantic_settings.CliSubCommand[_Run],
        pydantic.Field(description=_summary(_Run.__doc__)),
    ]
    version: Annotated[
        pydantic_settings.CliSubCommand[_Version],
        pydantic.Field(description=_summary(_Version.__doc__)),
    ]

    def cli_cmd(self) -> None:
        pydantic_settings.CliApp.run_subcommand(self)
