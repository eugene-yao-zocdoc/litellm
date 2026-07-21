"""Unit tests for the config-guardrail merge helpers in
``litellm.proxy.guardrails.usage_endpoints``.

The helpers surface config-only (in-memory) guardrails in the Guardrails Monitor
overview/detail/logs endpoints, merged with the DB-backed rows. They read the
in-memory registry lazily via ``from ...guardrail_registry import
IN_MEMORY_GUARDRAIL_HANDLER`` inside each function body, so the tests patch that
module attribute (the import source) with a fake handler and drive the real
helper code.
"""

from types import SimpleNamespace
from unittest import mock

from litellm.proxy.guardrails import usage_endpoints as MOD

_HANDLER_ATTR = "litellm.proxy.guardrails.guardrail_registry.IN_MEMORY_GUARDRAIL_HANDLER"


class _FakeLitellmParams:
    """Stand-in for the pydantic LitellmParams model on in-memory guardrails.

    Only the ``model_dump(exclude_none=...)`` contract that
    ``_normalize_in_memory_guardrail`` depends on is reproduced; the real model
    carries non-None defaults that would break the exact-equality assertions.
    """

    def __init__(self, data):
        self._data = data

    def model_dump(self, exclude_none=False):
        if exclude_none:
            return {k: v for k, v in self._data.items() if v is not None}
        return dict(self._data)


def _db_row(guardrail_id, guardrail_name):
    return SimpleNamespace(
        guardrail_id=guardrail_id,
        guardrail_name=guardrail_name,
        litellm_params={},
        guardrail_info={},
    )


def _fake_handler(in_memory, sources, by_id=None):
    by_id = by_id or {}
    h = mock.MagicMock()
    h.list_in_memory_guardrails.return_value = in_memory
    h.get_source.side_effect = lambda gid: sources.get(gid)
    h.get_guardrail_by_id.side_effect = lambda guardrail_id: by_id.get(guardrail_id)
    return h


def _patched_registry(in_memory, sources, by_id=None):
    return mock.patch(_HANDLER_ATTR, _fake_handler(in_memory, sources, by_id))


def _entries(db_rows, in_memory, sources):
    with _patched_registry(in_memory, sources):
        return MOD._config_guardrail_entries(db_rows)


def _overview(db_rows, in_memory, sources):
    with _patched_registry(in_memory, sources):
        return MOD._overview_guardrails(db_rows)


def _detail(guardrail_id, by_id, sources):
    with _patched_registry([], sources, by_id):
        return MOD._config_guardrail_detail(guardrail_id)


def _usage_log_ids(guardrail_id, db_guardrail=None, by_id=None, sources=None):
    with _patched_registry([], sources or {}, by_id or {}):
        return MOD._usage_log_guardrail_ids(guardrail_id, db_guardrail)


# --- _normalize_in_memory_guardrail ---


def test_normalize_dumps_params_and_defaults_info():
    g = {
        "guardrail_id": "uuid-1",
        "guardrail_name": "gcp-model-armor",
        "litellm_params": _FakeLitellmParams({"guardrail": "model_armor", "mode": None}),
    }
    out = MOD._normalize_in_memory_guardrail(g)
    assert out.guardrail_id == "uuid-1"
    assert out.guardrail_name == "gcp-model-armor"
    assert out.litellm_params == {"guardrail": "model_armor"}
    assert out.guardrail_info == {}


def test_normalize_dict_params_passthrough():
    g = {"guardrail_id": "id", "guardrail_name": "n", "litellm_params": {"guardrail": "x"}}
    out = MOD._normalize_in_memory_guardrail(g)
    assert out.litellm_params == {"guardrail": "x"}


def test_normalize_absent_and_none_params_default_empty():
    out = MOD._normalize_in_memory_guardrail({"guardrail_id": "id", "guardrail_name": "n"})
    assert out.litellm_params == {}
    out2 = MOD._normalize_in_memory_guardrail({"guardrail_id": "id", "guardrail_name": "n", "litellm_params": None})
    assert out2.litellm_params == {}


def test_normalize_non_dict_info_defaults_empty():
    g = {
        "guardrail_id": "id",
        "guardrail_name": "n",
        "litellm_params": {},
        "guardrail_info": "not-a-dict",
    }
    out = MOD._normalize_in_memory_guardrail(g)
    assert out.guardrail_info == {}


# --- _config_guardrail_entries ---


def test_config_entry_surfaced_when_not_in_db():
    im = [{"guardrail_id": "uuid-c", "guardrail_name": "cfg", "litellm_params": _FakeLitellmParams({})}]
    out = _entries([], im, {"uuid-c": "config"})
    assert [e.guardrail_id for e in out] == ["uuid-c"]


def test_dedupe_by_id_and_name():
    im = [
        {"guardrail_id": "dup-id", "guardrail_name": "x", "litellm_params": _FakeLitellmParams({})},
        {"guardrail_id": "uuid-n", "guardrail_name": "dup-name", "litellm_params": _FakeLitellmParams({})},
    ]
    sources = {"dup-id": "config", "uuid-n": "config"}
    out = _entries([_db_row("dup-id", "other"), _db_row("other-id", "dup-name")], im, sources)
    assert out == []


def test_non_config_source_skipped():
    im = [{"guardrail_id": "uuid-db", "guardrail_name": "stale", "litellm_params": _FakeLitellmParams({})}]
    out = _entries([], im, {"uuid-db": "db"})
    assert out == []


def test_config_entry_none_id_skipped():
    im = [{"guardrail_id": None, "guardrail_name": "noid", "litellm_params": _FakeLitellmParams({})}]
    out = _entries([], im, {})
    assert out == []


def test_mixed_batch_only_new_survives():
    im = [
        {"guardrail_id": "new-id", "guardrail_name": "new", "litellm_params": _FakeLitellmParams({})},
        {"guardrail_id": "dup-id", "guardrail_name": "whatever", "litellm_params": _FakeLitellmParams({})},
        {"guardrail_id": "nid", "guardrail_name": "dup-name", "litellm_params": _FakeLitellmParams({})},
        {"guardrail_id": "db-id", "guardrail_name": "dbsrc", "litellm_params": _FakeLitellmParams({})},
    ]
    sources = {"new-id": "config", "dup-id": "config", "nid": "config", "db-id": "db"}
    db = [_db_row("dup-id", "somename"), _db_row("other-id", "dup-name")]
    out = _entries(db, im, sources)
    assert [e.guardrail_id for e in out] == ["new-id"]


# --- _overview_guardrails ---


def test_overview_merges_db_and_config():
    im = [{"guardrail_id": "cfg", "guardrail_name": "c", "litellm_params": _FakeLitellmParams({})}]
    db = [_db_row("db1", "d1")]
    out = _overview(db, im, {"cfg": "config"})
    assert [g.guardrail_id for g in out] == ["db1", "cfg"]


# --- _config_guardrail_detail ---


def test_detail_config_hit_returns_entry():
    im = {
        "gid-c": {
            "guardrail_id": "gid-c",
            "guardrail_name": "c",
            "litellm_params": _FakeLitellmParams({"guardrail": "x"}),
        }
    }
    out = _detail("gid-c", by_id=im, sources={"gid-c": "config"})
    assert out is not None
    assert out.guardrail_id == "gid-c"
    assert out.litellm_params == {"guardrail": "x"}


def test_detail_db_and_none_source_returns_none():
    im = {"gid-db": {"guardrail_id": "gid-db", "guardrail_name": "s", "litellm_params": _FakeLitellmParams({})}}
    assert _detail("gid-db", by_id=im, sources={"gid-db": "db"}) is None
    assert _detail("gid-db", by_id=im, sources={}) is None


def test_detail_no_match_returns_none():
    assert _detail("missing", by_id={}, sources={}) is None


# --- _usage_log_guardrail_ids ---


def test_usage_log_ids_include_db_guardrail_name():
    assert _usage_log_ids("db-uuid", _db_row("db-uuid", "DB Guardrail")) == [
        "db-uuid",
        "DB Guardrail",
    ]


def test_usage_log_ids_include_config_guardrail_name():
    config = {
        "cfg-uuid": {
            "guardrail_id": "cfg-uuid",
            "guardrail_name": "Config Guardrail",
            "litellm_params": _FakeLitellmParams({}),
        }
    }
    assert _usage_log_ids(
        "cfg-uuid",
        by_id=config,
        sources={"cfg-uuid": "config"},
    ) == ["cfg-uuid", "Config Guardrail"]


def test_usage_log_ids_unknown_or_stale_source_remain_uuid_only():
    stale = {
        "stale-uuid": {
            "guardrail_id": "stale-uuid",
            "guardrail_name": "Stale Guardrail",
            "litellm_params": _FakeLitellmParams({}),
        }
    }
    assert _usage_log_ids("unknown-uuid") == ["unknown-uuid"]
    assert _usage_log_ids(
        "stale-uuid",
        by_id=stale,
        sources={"stale-uuid": "db"},
    ) == ["stale-uuid"]
