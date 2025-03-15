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

__all__ = [
    "JLAPHeaders",
    "PackageRecord",
    "RepodataHeaders",
    "RunExports",
    "Shard",
    "ShardedRepodata",
]

from typing import Any, TypedDict

import pydantic
import rattler.platform


class _RepodataHeaders(pydantic.BaseModel, extra="ignore"):
    if_none_match: str | None = None


class JLAPHeaders(_RepodataHeaders):
    range: str | None = None


class PackageRecord(pydantic.BaseModel, extra="allow"):
    md5: str | None = None
    sha256: str | None = None


class RepodataHeaders(_RepodataHeaders):
    accept_encoding: str | None = None
    if_modified_since: str | None = None


class RunExports(
    TypedDict("_RunExports", {"packages.conda": dict[str, dict[str, Any]]}),
):
    packages: dict[str, dict[str, Any]]


class Shard(RunExports):
    removed: list[str]


class _ShardedSubdirInfo(TypedDict):
    base_url: str
    shards_base_url: str
    subdir: rattler.platform.PlatformLiteral


class ShardedRepodata(TypedDict):
    info: _ShardedSubdirInfo
    shards: dict[str, bytes]
