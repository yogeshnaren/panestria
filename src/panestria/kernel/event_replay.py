"""Replay committed canonical rows, independent of notification delivery or process memory."""

from __future__ import annotations

import json
from dataclasses import dataclass

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

MAX_CURSOR = 2**63 - 1


def parse_cursor(value: str) -> int:
    if len(value) > 19 or not value.isascii() or not value.isdigit() or (len(value) > 1 and value.startswith("0")):
        raise KernelDenied("invalid_cursor")
    cursor = int(value)
    if cursor > MAX_CURSOR:
        raise KernelDenied("invalid_cursor")
    return cursor


@dataclass(frozen=True)
class ReplayPage:
    events: tuple[dict[str, object], ...]
    snapshot: dict[str, object]
    resync: bool


class EventReplay:
    def read(self, uow: UnitOfWork, actor: Actor, goal_id: str, after: int, limit: int = 50) -> ReplayPage:
        if not 0 <= after <= MAX_CURSOR or not 1 <= limit <= 100:
            raise KernelDenied("invalid_cursor_or_limit")
        # One statement gives an authoritative state + high-water cursor from the
        # same PostgreSQL snapshot. A later event cannot advance the cursor past
        # state the browser did not receive.
        row = uow.execute(
            "SELECT g.status,COALESCE(r.floor_seq,0),(SELECT COALESCE(max(seq),0) FROM panestria.task_event),"
            " COALESCE((SELECT jsonb_agg(jsonb_build_object('id',t.id,'state',t.state,"
            " 'row_version',t.row_version::text,'lease_epoch',t.lease_epoch::text) ORDER BY t.id)"
            " FROM panestria.task t WHERE t.goal_id=g.id),'[]'::jsonb)"
            " FROM panestria.goal g LEFT JOIN panestria.event_retention r ON r.goal_id=g.id"
            " WHERE g.id=%s AND g.owner_id=%s AND g.project_id=%s FOR SHARE OF g",
            (goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        snapshot = {"goal_id": goal_id, "status": row[0], "cursor": str(row[2]), "tasks": row[3]}
        if after < row[1]:
            return ReplayPage((), snapshot, True)
        # Bound this page to the snapshot's high-water mark as well as its scope.
        rows = uow.execute(
            "SELECT seq,id::text,kind,payload,trace_id,schema_version,privacy_label,sha256"
            " FROM panestria.task_event WHERE goal_id=%s AND seq>%s AND seq<=%s ORDER BY seq LIMIT %s",
            (goal_id, after, row[2], limit),
        ).fetchall()
        events = tuple(
            {
                "seq": str(r[0]),
                "id": r[1],
                "kind": r[2],
                "payload": r[3],
                "trace_id": r[4],
                "schema_version": r[5],
                "privacy_label": r[6],
                "sha256": r[7],
            }
            for r in rows
        )
        return ReplayPage(events, snapshot, False)

    def retire_before(self, uow: UnitOfWork, actor: Actor, goal_id: str, floor: int, expected_version: int) -> int:
        if not 0 <= floor <= MAX_CURSOR:
            raise KernelDenied("invalid_cursor")
        row = uow.execute(
            "SELECT id FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        uow.execute("INSERT INTO panestria.event_retention(goal_id) VALUES (%s) ON CONFLICT DO NOTHING", (goal_id,))
        current = uow.execute(
            "SELECT floor_seq,row_version FROM panestria.event_retention WHERE goal_id=%s FOR UPDATE", (goal_id,)
        ).fetchone()
        if current is None or current[1] != expected_version or floor < current[0]:
            raise KernelDenied("version_conflict")
        high = uow.execute("SELECT COALESCE(max(seq),0) FROM panestria.task_event").fetchone()
        if high is None or floor > high[0]:
            raise KernelDenied("future_cursor")
        uow.execute(
            "UPDATE panestria.event_retention SET floor_seq=%s,row_version=row_version+1 WHERE goal_id=%s",
            (floor, goal_id),
        )
        return expected_version + 1


def sse_event(event: dict[str, object]) -> bytes:
    parse_cursor(str(event["seq"]))
    body = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"id: {event['seq']}\nevent: task-event\ndata: {body}\n\n".encode()
