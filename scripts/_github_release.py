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

import os
import pathlib

import packaging.version
import pygit2
import requests

_TEMPLATE = """\
User-facing changes: https://hingebase.github.io/mahoraga/changelog.html#{current}

Full changelog: https://github.com/hingebase/mahoraga/compare/v{previous}...{tag_name}
"""


def main() -> None:
    repo = pygit2.Repository(".git")
    versions = sorted(
        packaging.version.parse(ref.name.removeprefix("refs/tags/v"))
        for ref in repo.references.iterator(pygit2.enums.ReferenceFilter.TAGS)
    )

    if os.getenv("GITHUB_REF_TYPE") == "tag":
        tag_name = os.environ["GITHUB_REF_NAME"]
        current = packaging.version.parse(tag_name.removeprefix("v"))
        del versions[versions.index(current):]
    else:
        current = versions.pop()
        tag_name = f"v{current}"

    if current.is_prerelease:
        previous = versions.pop()
    else:
        while True:
            previous = versions.pop()
            if not previous.is_prerelease:
                break

    body = _TEMPLATE.format_map(locals())
    if gh_token := os.getenv("GH_TOKEN"):
        with requests.post(
            "https://api.github.com/repos/hingebase/mahoraga/releases",
            json={
                "tag_name": tag_name,
                "name": f"{current}",
                "body": body,
                "prerelease": current.is_prerelease,
                "make_latest": "false" if current.is_prerelease else "true",
            },
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {gh_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            # https://requests.readthedocs.io/en/latest/user/advanced/#timeouts
            timeout=(3.05, 27),
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
    else:
        preview = pathlib.Path("scripts", "github-release-preview.md")
        preview.write_text(body, encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
