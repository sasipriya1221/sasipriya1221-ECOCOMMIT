from __future__ import annotations

from .candidate8 import Candidate8Provider, Candidate8Result, run_candidate8


Candidate9Result = Candidate8Result


def run_candidate9(instruction: str, provider: Candidate8Provider) -> Candidate9Result:
    return run_candidate8(instruction, provider)
