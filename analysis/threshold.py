from enum import StrEnum
from fractions import Fraction

from rounds.rules import InspectionRule


class RecheckDecision(StrEnum):
    RETEST = 'retest'
    RELEASE = 'release'


def classify_mean(mean: Fraction, rule: InspectionRule) -> RecheckDecision:
    if mean >= rule.threshold:
        return RecheckDecision.RETEST
    return RecheckDecision.RELEASE
