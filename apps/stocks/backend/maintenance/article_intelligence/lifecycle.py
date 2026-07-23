"""Validated lifecycle for resumable maintenance batches."""

from enum import StrEnum


class BatchState(StrEnum):
    CREATED = "CREATED"
    EXPORTING = "EXPORTING"
    GENERATING = "GENERATING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


_TRANSITIONS: dict[BatchState, frozenset[BatchState]] = {
    BatchState.CREATED: frozenset({BatchState.EXPORTING}),
    BatchState.EXPORTING: frozenset({BatchState.GENERATING, BatchState.FAILED}),
    BatchState.GENERATING: frozenset({BatchState.READY_TO_PUBLISH, BatchState.PARTIAL, BatchState.FAILED}),
    BatchState.READY_TO_PUBLISH: frozenset({BatchState.PUBLISHING}),
    BatchState.PUBLISHING: frozenset({BatchState.COMPLETED, BatchState.PARTIAL, BatchState.FAILED}),
    BatchState.PARTIAL: frozenset({BatchState.GENERATING, BatchState.PUBLISHING}),
    BatchState.FAILED: frozenset(),
    BatchState.COMPLETED: frozenset(),
}


def transition_batch(current: BatchState, target: BatchState, *, recovery: bool = False) -> BatchState:
    if recovery and current == BatchState.FAILED and target in {
        BatchState.EXPORTING, BatchState.GENERATING, BatchState.PUBLISHING,
    }:
        return target
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"invalid maintenance batch transition: {current} -> {target}")
    return target