from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    NA = "n/a"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_ABORTED = "run_aborted"
    DEMULTIPLEXING_STARTED = "demultiplexing_started"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_FINISHED = "analysis_finished"
    ANALYSIS_NOT_POSSIBLE = "analysis_not_possible"
    ANALYSIS_AND_BACKUP_NOT_REQUIRED = "analysis_and_backup_not_required"


@dataclass(frozen=True)
class Run:
    """Represents a run in the NGSD database."""

    name: str
    status: RunStatus
