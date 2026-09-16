from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from ..models import ListingObservation, CoverageRow


@dataclass
class ScanResult:
    listings: list[ListingObservation]
    coverage: list[CoverageRow]
    errors: list[str]


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    async def scan(self) -> ScanResult:
        raise NotImplementedError
