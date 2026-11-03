"""Independent verification of simulation results against the spec."""

from inkubit.verify.expected import ideal_distribution, noisy_distribution
from inkubit.verify.verdict import Verdict, verify_counts

__all__ = ["Verdict", "ideal_distribution", "noisy_distribution", "verify_counts"]
