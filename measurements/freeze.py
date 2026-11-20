import sqlite3
from collections.abc import Iterable

from rounds.registry import RoundRegistry
from rounds.specimens import require_name

from .frozen_store import FrozenRevision, FrozenRevisionStore
from .intake import Reading, accept_reading_pair
from .revisions import RevisionLink


def _check_origins(frozen: FrozenRevision, parent: FrozenRevision | None) -> None:
    if parent is None:
        for reading in frozen.readings:
            if reading.origin.locator != reading.origin.original_locator:
                raise ValueError('the initial revision requires original reading records')
        return
    for reading, earlier in zip(frozen.readings, parent.readings, strict=True):
        if reading.origin.original_locator != earlier.origin.original_locator:
            raise ValueError('a correction must trace to the same original reading')
        if reading.origin == earlier.origin:
            if reading.deviation != earlier.deviation:
                raise ValueError('a changed reading needs a correction record')
        elif reading.origin.locator == earlier.origin.locator:
            raise ValueError('a correction must have its own record location')
        elif reading.origin.locator == reading.origin.original_locator:
            raise ValueError('a correction cannot be stored at the original record location')


def freeze_revision(
    db: sqlite3.Connection,
    round_id: str,
    revision_id: str,
    readings: Iterable[Reading],
    *,
    parent_revision: str | None = None,
) -> FrozenRevision:
    require_name(revision_id, 'revision identifier')
    if parent_revision is not None:
        require_name(parent_revision, 'parent revision identifier')
    record = RoundRegistry(db).get(round_id)
    ordered = accept_reading_pair(record, readings)
    frozen = FrozenRevision(RevisionLink(round_id, revision_id, parent_revision), ordered)
    store = FrozenRevisionStore(db)
    with db:
        db.execute('BEGIN IMMEDIATE')
        parent = None
        if parent_revision is not None:
            parent = store.fetch(round_id, parent_revision)
            if parent is None:
                raise LookupError('parent revision is absent from the target round')
        _check_origins(frozen, parent)
        store.history.append(frozen.link)
        store.store(frozen)
    return frozen
