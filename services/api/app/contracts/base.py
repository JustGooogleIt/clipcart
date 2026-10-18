"""Shared Pydantic base for canonical records: forbid extras, finite numbers, camelCase JSON."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Record(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        alias_generator=to_camel,
        populate_by_name=True,
        allow_inf_nan=False,
    )

    def wire(self) -> dict:
        """JSON-safe camelCase dict for API responses and Mongo documents."""
        return self.model_dump(mode="json", by_alias=True)


class Mutable(Record):
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        alias_generator=to_camel,
        populate_by_name=True,
        allow_inf_nan=False,
    )


def from_doc(model: type[Record], doc: dict) -> Record:
    """Validate a stored document, ignoring storage-only keys (_id, ownerId, ...)."""
    allowed = set()
    for name, f in model.model_fields.items():
        allowed.add(name)
        if f.alias:
            allowed.add(f.alias)
        allowed.add(model.model_config["alias_generator"](name))
    return model.model_validate({k: v for k, v in doc.items() if k in allowed})
