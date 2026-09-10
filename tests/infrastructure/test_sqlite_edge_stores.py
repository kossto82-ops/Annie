"""Round-trip persistence tests for the SQLite edge stores (Odysseus #6/#7/#8, D10)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.domain.retrieval.calendar_store import CalendarStore
from jarvis.domain.retrieval.notes_store import NotesStore
from jarvis.domain.retrieval.task_scheduler import TaskScheduler
from jarvis.infrastructure.sqlite_calendar_store import SqliteCalendarStore
from jarvis.infrastructure.sqlite_notes_store import SqliteNotesStore
from jarvis.infrastructure.sqlite_task_scheduler import SqliteTaskScheduler


def _ids() -> Callable[[], str]:
    counter = iter("abcd")
    return lambda: next(counter)


class TestSqliteNotesStore:
    def test_satisfies_the_notes_store_protocol(self) -> None:
        store = SqliteNotesStore(sqlite3.connect(":memory:"))
        assert isinstance(store, NotesStore)

    def test_create_list_get_round_trip(self) -> None:
        store = SqliteNotesStore(sqlite3.connect(":memory:"), id_factory=_ids())
        ids: list[str] = []
        for i in range(3):
            note = store.create_note(title=f"t{i}", body=f"b{i}", tags=(f"g{i}",))
            ids.append(note.id)
        assert [n.title for n in store.list_notes()] == ["t2", "t1", "t0"]
        assert store.get_note(ids[0]).body == "b0"

    def test_persists_across_new_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.db"
        connection = sqlite3.connect(path)
        SqliteNotesStore(connection, id_factory=_ids()).create_note(
            title="persist me", body="hello"
        )
        connection.close()

        notes = SqliteNotesStore(sqlite3.connect(path)).list_notes()
        assert len(notes) == 1
        assert notes[0].body == "hello"

    def test_update_changes_fields_and_preserves_created_at(self) -> None:
        store = SqliteNotesStore(sqlite3.connect(":memory:"), id_factory=_ids())
        note = store.create_note(title="a", body="b", tags=("one",))
        updated = store.update_note(note.id, title="a2", body="b2", tags=("two",))
        assert updated.title == "a2"
        assert updated.created_at == note.created_at
        assert updated.updated_at >= note.updated_at
        assert store.get_note(note.id).tags == ("two",)

    def test_delete_removes_the_note(self) -> None:
        store = SqliteNotesStore(sqlite3.connect(":memory:"), id_factory=_ids())
        note = store.create_note(title="gone", body="x")
        store.delete_note(note.id)
        assert store.list_notes() == ()
        with pytest.raises(KeyError):
            store.get_note(note.id)

    def test_search_filters_by_title_body_and_tags(self) -> None:
        store = SqliteNotesStore(sqlite3.connect(":memory:"), id_factory=_ids())
        store.create_note(title="Shopping", body="milk and eggs", tags=("errands",))
        store.create_note(title="Ideas", body="nothing here", tags=())
        assert [n.title for n in store.search_notes("milk")] == ["Shopping"]
        assert [n.title for n in store.search_notes("errands")] == ["Shopping"]
        assert [n.title for n in store.search_notes("nothing here")] == ["Ideas"]
        assert store.search_notes("zzz") == ()

    def test_get_unknown_id_raises(self) -> None:
        store = SqliteNotesStore(sqlite3.connect(":memory:"))
        with pytest.raises(KeyError):
            store.get_note("missing")


class TestSqliteCalendarStore:
    def test_satisfies_the_calendar_store_protocol(self) -> None:
        store = SqliteCalendarStore(sqlite3.connect(":memory:"))
        assert isinstance(store, CalendarStore)

    def test_create_list_get_round_trip(self) -> None:
        now = datetime.now(UTC)
        store = SqliteCalendarStore(sqlite3.connect(":memory:"), id_factory=_ids())
        ids: list[str] = []
        for i in range(3):
            event = store.create_event(
                title=f"t{i}",
                start=now + timedelta(hours=i),
                end=now + timedelta(hours=i + 1),
            )
            ids.append(event.id)
        assert [e.title for e in store.list_events()] == ["t0", "t1", "t2"]
        assert store.get_event(ids[1]).title == "t1"

    def test_persists_across_new_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "calendar.db"
        now = datetime.now(UTC)
        connection = sqlite3.connect(path)
        SqliteCalendarStore(connection, id_factory=_ids()).create_event(
            title="standup", start=now, end=now + timedelta(minutes=15)
        )
        connection.close()

        events = SqliteCalendarStore(sqlite3.connect(path)).list_events()
        assert len(events) == 1
        assert events[0].title == "standup"

    def test_update_and_delete(self) -> None:
        now = datetime.now(UTC)
        store = SqliteCalendarStore(sqlite3.connect(":memory:"), id_factory=_ids())
        event = store.create_event(
            title="old", start=now, end=now + timedelta(minutes=15)
        )
        updated = store.update_event(
            event.id,
            title="new",
            start=now,
            end=now + timedelta(minutes=30),
            description="",
            location="rooms",
            all_day=False,
        )
        assert updated.title == "new"
        assert updated.location == "rooms"
        store.delete_event(event.id)
        with pytest.raises(KeyError):
            store.get_event(event.id)

    def test_events_in_range_overlaps_but_does_not_include_outside_events(self) -> None:
        now = datetime.now(UTC)
        store = SqliteCalendarStore(sqlite3.connect(":memory:"), id_factory=_ids())
        store.create_event(
            title="inside", start=now, end=now + timedelta(hours=1)
        )
        store.create_event(
            title="tomorrow", start=now + timedelta(days=1), end=now + timedelta(days=1, hours=1)
        )
        within = store.events_in_range(now, now + timedelta(minutes=30))
        assert [e.title for e in within] == ["inside"]

    def test_get_unknown_id_raises(self) -> None:
        store = SqliteCalendarStore(sqlite3.connect(":memory:"))
        with pytest.raises(KeyError):
            store.get_event("missing")


class TestSqliteTaskScheduler:
    def test_satisfies_the_task_scheduler_protocol(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"))
        assert isinstance(store, TaskScheduler)

    def test_create_list_get_round_trip(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        ids: list[str] = []
        for i in range(3):
            task = store.create_task(
                name=f"t{i}", command=f"echo {i}", cron="0 9 * * *"
            )
            ids.append(task.id)
        assert [t.name for t in store.list_tasks()] == ["t2", "t1", "t0"]
        assert store.get_task(ids[0]).command == "echo 0"

    def test_persists_across_new_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "tasks.db"
        connection = sqlite3.connect(path)
        SqliteTaskScheduler(connection, id_factory=_ids()).create_task(
            name="backup", command="tar"
        )
        connection.close()

        tasks = SqliteTaskScheduler(sqlite3.connect(path)).list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "backup"

    def test_update_preserves_identity_and_created_at(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        task = store.create_task(name="a", command="echo a", cron="")
        updated = store.update_task(
            task.id,
            name="a2",
            command="echo b",
            cron="0 9 * * *",
            description="desc",
            enabled=True,
        )
        assert updated.name == "a2"
        assert updated.created_at == task.created_at
        assert store.get_task(task.id).cron == "0 9 * * *"

    def test_enable_and_disable_are_reversible(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        task = store.create_task(name="toggle", command="echo x")
        assert store.get_task(task.id).enabled is True
        assert store.disable_task(task.id).enabled is False
        assert store.get_task(task.id).enabled is False
        assert store.enable_task(task.id).enabled is True

    def test_due_tasks_ignores_disabled_and_unscheduled(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        task = store.create_task(name="never due", command="echo x")
        store.disable_task(task.id)
        assert store.due_tasks() == ()
        assert store.get_task(task.id).next_run is None

    def test_delete_and_get_unknown_raises(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        task = store.create_task(name="gone", command="echo x")
        store.delete_task(task.id)
        assert store.list_tasks() == ()
        with pytest.raises(KeyError):
            store.get_task(task.id)

    def test_bad_cron_is_rejected_clearly(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        with pytest.raises(ValueError, match="cron"):
            store.create_task(name="bad", command="echo x", cron="not a cron")
        task = store.create_task(name="good", command="echo x", cron="0 9 * * *")
        with pytest.raises(ValueError, match="cron"):
            store.update_task(
                task.id, name="good", command="echo x", cron="61 * * * *",
                description="", enabled=True,
            )

    def test_create_computes_next_run_from_cron(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        task = store.create_task(name="daily", command="echo x", cron="0 9 * * *")
        assert task.next_run is not None and task.next_run > datetime.now(UTC)
        assert (task.next_run.hour, task.next_run.minute) == (9, 0)
        unscheduled = store.create_task(name="once", command="echo x", cron="")
        assert unscheduled.next_run is None

    def test_record_run_persists_status_and_output(self, tmp_path: Path) -> None:
        path = tmp_path / "tasks.db"
        connection = sqlite3.connect(path)
        store = SqliteTaskScheduler(connection, id_factory=_ids())
        task = store.create_task(name="job", command="echo hi")
        ran = store.record_run(task.id, ok=True, output="all done")
        assert ran.last_status == "ok"
        assert ran.last_output == "all done"
        assert ran.last_run is not None
        connection.close()
        reloaded = SqliteTaskScheduler(sqlite3.connect(path)).get_task(task.id)
        assert reloaded.last_status == "ok"
        assert reloaded.last_output == "all done"

    def test_record_run_caps_output_and_marks_error(self) -> None:
        store = SqliteTaskScheduler(sqlite3.connect(":memory:"), id_factory=_ids())
        task = store.create_task(name="job", command="echo hi")
        ran = store.record_run(task.id, ok=False, output="x" * 5000)
        assert ran.last_status == "error"
        assert len(ran.last_output) == 2000

    def test_legacy_payloads_without_runs_read_honestly(self, tmp_path: Path) -> None:
        import json

        path = tmp_path / "tasks.db"
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE tasks (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        legacy = {
            "name": "old", "command": "echo old", "cron": "", "description": "",
            "enabled": True, "next_run": None,
            "created_at": "2026-09-01T10:00:00+00:00",
            "updated_at": "2026-09-01T10:00:00+00:00",
        }
        connection.execute(
            "INSERT INTO tasks (task_id, payload) VALUES (?, ?)",
            ("old1", json.dumps(legacy)),
        )
        connection.commit()
        task = SqliteTaskScheduler(connection).get_task("old1")
        assert task.last_run is None
        assert task.last_status is None
        assert task.last_output == ""


class TestLocalTaskSchedulerRuns:
    def test_record_run_bad_cron_and_next_run(self, tmp_path: Path) -> None:
        from jarvis.infrastructure.task_scheduler import LocalTaskScheduler

        store = LocalTaskScheduler(tmp_path)
        with pytest.raises(ValueError, match="cron"):
            store.create_task(name="bad", command="echo x", cron="nope nope")
        task = store.create_task(name="daily", command="echo x", cron="0 9 * * *")
        assert task.next_run is not None
        ran = store.record_run(task.id, ok=True, output="done")
        assert (ran.last_status, ran.last_output) == ("ok", "done")
        reloaded = LocalTaskScheduler(tmp_path).get_task(task.id)
        assert reloaded.last_status == "ok"

    def test_legacy_json_without_runs_reads_honestly(self, tmp_path: Path) -> None:
        import json

        from jarvis.infrastructure.task_scheduler import LocalTaskScheduler

        (tmp_path / "tasks.json").write_text(
            json.dumps({
                "old1": {
                    "name": "old", "command": "echo old", "cron": "",
                    "description": "", "enabled": True, "next_run": None,
                    "created_at": "2026-09-01T10:00:00+00:00",
                    "updated_at": "2026-09-01T10:00:00+00:00",
                }
            }),
            encoding="utf-8",
        )
        task = LocalTaskScheduler(tmp_path).get_task("old1")
        assert task.last_run is None and task.last_output == ""