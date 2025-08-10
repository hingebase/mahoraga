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

__all__ = ["NormalizedName", "Simple"]

import functools
from typing import Annotated

import annotated_types as at
import packaging.utils
import pydantic

NormalizedName = Annotated[
    str,
    pydantic.AfterValidator(
        functools.partial(packaging.utils.canonicalize_name, validate=True),
    ),
]


class _Hashes(pydantic.BaseModel, extra="ignore"):
    sha256: str = ""


class _Entry(pydantic.BaseModel, extra="ignore"):
    filename: str
    hashes: _Hashes


class _Meta(pydantic.BaseModel, extra="ignore"):
    api_version: Annotated[
        str,
        at.Ge("1.0"),
        at.Lt("1.:"),
        pydantic.Field(alias="api-version"),
    ]


class Simple(pydantic.BaseModel, extra="ignore"):
    name: NormalizedName
    files: list[_Entry]
    meta: _Meta
