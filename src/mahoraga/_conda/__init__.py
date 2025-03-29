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

__all__ = ["router", "split_repo"]

import fastapi

from mahoraga import _core

from . import _packages, _repodata, _sharded_repodata
from ._sharded_repodata import split_repo

router = fastapi.APIRouter(route_class=_core.APIRoute)
router.include_router(_repodata.router)
router.include_router(_sharded_repodata.router)
router.include_router(_packages.router)  # Must be the last included
