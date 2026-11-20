from dataclasses import dataclass

from issuance.report_payload import ReportPayload
from measurements.origins import ReadOrigin


@dataclass(frozen=True)
class ClaimOrigin:
    specimen_id: str
    deviation: int
    origin: ReadOrigin


def describe_claim_origins(payload: ReportPayload) -> tuple[ClaimOrigin, ClaimOrigin]:
    first, second = payload.readings
    return (ClaimOrigin(first.specimen_id, first.deviation, first.origin),
            ClaimOrigin(second.specimen_id, second.deviation, second.origin))
