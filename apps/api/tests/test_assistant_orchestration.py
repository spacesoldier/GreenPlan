from greenplan_api.assistant import (
    ASSISTANT_TASKS,
    assistant_fingerprint,
    runnable_tasks,
)


def test_assistant_fingerprint_is_stable_for_the_same_delivery():
    entries = [
        {"relative_path": "Проект/head.dwg", "sha256": "b" * 64},
        {"relative_path": "Исходные/base.dwg", "sha256": "a" * 64},
    ]
    expected = assistant_fingerprint(entries, taxonomy_version="cad-v1", provider_version="rules-v2")

    assert assistant_fingerprint(
        list(reversed(entries)), taxonomy_version="cad-v1", provider_version="rules-v2",
    ) == expected
    assert assistant_fingerprint(
        entries, taxonomy_version="cad-v2", provider_version="rules-v2",
    ) != expected


def test_task_plan_only_releases_satisfied_dependencies():
    states = {task.key: "pending" for task in ASSISTANT_TASKS}
    assert runnable_tasks(states) == ["inventory"]

    states["inventory"] = "completed"
    assert runnable_tasks(states) == ["xref_graph", "semantic_taxonomy"]

    states["xref_graph"] = "completed"
    states["semantic_taxonomy"] = "completed"
    assert runnable_tasks(states) == ["summary"]


def test_failed_or_cancelled_dependency_does_not_release_downstream_task():
    states = {task.key: "pending" for task in ASSISTANT_TASKS}
    states["inventory"] = "failed"
    assert runnable_tasks(states) == []
