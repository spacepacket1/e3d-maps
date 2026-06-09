from __future__ import annotations

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict


class CompatBaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra="forbid")
