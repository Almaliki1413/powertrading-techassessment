"""ValidateDay: return ValidatedDay or a typed blocking error."""

from __future__ import annotations

from datetime import date

from app.application.resolve_dataset import DatasetReference, ResolveDataset
from app.domain.errors import IncompleteIntervalSet
from app.domain.models import ValidatedDay


class ValidateDay:
    def __init__(self, resolver: ResolveDataset) -> None:
        self.resolver = resolver

    def execute(self, dataset_id: str, selected_date: date) -> ValidatedDay:
        reference: DatasetReference = self.resolver.get(dataset_id)
        day = reference.validated.get(selected_date)
        if day is None:
            summary = next((item for item in reference.days if item.date == selected_date), None)
            raise IncompleteIntervalSet(
                "selected day is not validated and cannot be optimized",
                details={
                    "selected_date": selected_date.isoformat(),
                    "blocking_code": summary.blocking_code if summary else "ARCHIVE_NOT_FOUND",
                    "blocking_message": summary.blocking_message if summary else "day not in dataset",
                },
            )
        return day
