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

__all__ = ["main"]

import argparse
import contextlib
import pathlib
import sys
import urllib.parse
from typing import Annotated

import click
import jinja2
import pydantic
import pydantic_settings

from mahoraga import __version__, _asgi, _core


def main() -> None:
    """CLI entry."""
    cli_settings_source = (
        pydantic_settings.CliSettingsSource[argparse.ArgumentParser](_Main)
    )
    cli_settings_source.root_parser.suggest_on_error = True
    pydantic_settings.CliApp.run(
        _Main,
        cli_args=["--help"] if len(sys.argv) <= 1 else None,
        cli_settings_source=cli_settings_source,
    )


class _Config(_core.Config, toml_file=None):
    pass


class _New(_core.Server, alias_generator=None):
    """Create a new directory structure for Mahoraga.

    The default configuration may not be suitable for you. A small subset of
    the options can be tuned via command line (see below), while the rest live
    in the `mahoraga.toml` file created by this command. Once you've done with
    that file, you don't need to run this command again to create another
    directory. For details, run `mahoraga import -h`.
    """

    root: Annotated[
        pydantic_settings.CliPositionalArg[pydantic.NewPath],
        pydantic.Field(description="Root path of the new directory"),
    ]

    def cli_cmd(self) -> None:
        cfg = _Config(server=self)
        cfg_file = _setup(cfg, self.root)
        click.echo(f"Done. Please edit {cfg_file} before starting the server.")


class _Import(_core.Address):
    """Create a new directory structure from existing configuration.

    Mahoraga directory structure is not relocatable. Use this command to move
    your configuration files to another location, either on the same machine or
    not.

    Mahoraga directory structure follows semantic versioning. Directory
    created by Mahoraga version X.Y.Z (X>=1) is guaranteed to work under
    any version >=X.Y.Z,<X+1. Once updated to an uncompatible version,
    you have to create a new directory via `mahoraga new` and migrate your data
    by hand.
    """

    source: Annotated[
        pydantic_settings.CliPositionalArg[pydantic.FilePath],
        pydantic.Field(description="An existing mahoraga.toml file"),
        _core.Predicate("input_value.name == 'mahoraga.toml'"),
    ]
    destination: Annotated[
        pydantic_settings.CliPositionalArg[pydantic.NewPath],
        pydantic.Field(description="Root path of the new directory"),
    ]

    def cli_cmd(self) -> None:
        with contextlib.chdir(self.source.parent):
            cfg = _core.Config()
        cfg.server.host = self.host
        cfg.server.port = self.port
        cfg_file = _setup(cfg, self.destination)
        click.echo(f"Mahoraga root directory created at {cfg_file.parent}")


class _Run(pydantic.BaseModel, validate_default=True):
    """Start Mahoraga server.

    Before starting, make sure you've had all options in `mahoraga.toml`
    set properly. When the server is already running, changes in
    `mahoraga.toml` won't take effect until a restart.
    """

    root: Annotated[
        pydantic.DirectoryPath,
        pydantic.Field(description="Root path of a directory containing "
                                   "mahoraga.toml"),
        _core.Predicate("(input_value / 'mahoraga.toml').is_file()"),
    ] = pathlib.Path()

    def cli_cmd(self) -> None:
        _asgi.run(self.root)


class _Version(pydantic.BaseModel):
    """Show Mahoraga version and exit."""

    def cli_cmd(self) -> None:
        del self
        click.echo(f"Mahoraga v{__version__}")


def _prog_name(arg0: str) -> str | None:
    return None if arg0.endswith("__main__.py") else arg0


def _setup(cfg: _core.Config, root: pathlib.Path) -> pathlib.Path:
    root.mkdir(parents=True)
    root = root.resolve(strict=True)
    for subdir in "channels", "log", "nginx", "repodata-cache":
        (root / subdir).mkdir()

    kwargs = cfg.model_dump()
    kwargs["server"]["root"] = root.as_posix()
    kwargs["unix"] = sys.platform.startswith(("darwin", "linux"))
    kwargs["upstream"]["python"] = [
        urllib.parse.unquote(str(url)) for url in kwargs["upstream"]["python"]
    ]

    env = jinja2.Environment(
        autoescape=True,
        loader=jinja2.PackageLoader(__name__, package_path=""),
    )
    cfg_file = root / "mahoraga.toml"
    for src, dst in [
        ("mahoraga.toml.jinja", cfg_file),
        ("mahoraga.conf.jinja", root / "nginx/mahoraga.conf"),
        ("nginx.conf.jinja", root / "nginx/nginx.conf"),
    ]:
        with dst.open("x", encoding="utf-8", newline="") as f:
            print(env.get_template(src).render(kwargs), file=f)
    return cfg_file


def _summary(docstring: str | None) -> str | None:
    return docstring.split(".", 1)[0] if docstring else None


class _Main(
    pydantic_settings.BaseSettings,
    cli_prog_name=_prog_name(sys.argv[0]),
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
    import_: Annotated[
        pydantic_settings.CliSubCommand[_Import],
        pydantic.Field(alias="import", description=_summary(_Import.__doc__)),
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
