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

import argparse
import os
import shutil
import subprocess  # noqa: S404
import sys
from typing import Annotated, Literal

import pydantic
import pydantic_settings


def main() -> None:
    cli_settings_source = (
        pydantic_settings.CliSettingsSource[argparse.ArgumentParser](_Main)
    )
    cli_settings_source.root_parser.suggest_on_error = True
    pydantic_settings.CliApp.run(
        _Main,
        cli_args=["--help"] if len(sys.argv) <= 1 else None,
        cli_settings_source=cli_settings_source,
    )


class _Main(
    pydantic_settings.BaseSettings,
    nested_model_default_partial_update=True,
    case_sensitive=True,
    cli_hide_none_type=True,
    cli_avoid_json=True,
    cli_enforce_required=True,
    cli_implicit_flags=True,
    cli_kebab_case=True,
):
    """Update project version."""

    bump: Annotated[
        pydantic_settings.CliPositionalArg[Literal["major", "minor", "patch"]],
        pydantic.Field(
            description="Update the project version using the given semantics",
        ),
    ]

    def cli_cmd(self) -> None:
        version = subprocess.run(  # noqa: S603
            [
                os.getenv("UV", "uv"),
                "version",
                "--bump", self.bump,
                "--no-sync",
                "--short",
            ],
            capture_output=True,
            check=True,
            encoding="ascii",
        ).stdout.strip()
        if git := shutil.which("git"):
            # https://git-scm.com/book/en/v2/Git-Tools-Signing-Your-Work
            subprocess.run(  # noqa: S603
                [
                    git,
                    "commit",
                    "-a",
                    "-S",
                    "-m", f"\U0001f516 Mahoraga v{version}",
                ],
                check=True,
            )
            tag = f"v{version}"
            subprocess.run([git, "tag", "-s", tag, "-m", tag], check=True)  # noqa: S603
            subprocess.run([git, "log", "--show-signature", "-1"], check=True)  # noqa: S603
            subprocess.run([git, "tag", "-v", tag], check=True)  # noqa: S603


if __name__ == "__main__":
    main()
