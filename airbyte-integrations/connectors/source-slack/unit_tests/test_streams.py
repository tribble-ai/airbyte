#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

import re
from unittest.mock import Mock

import pendulum
import pytest
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator
from airbyte_cdk.models import (
    AirbyteStateBlob,
    AirbyteStateMessage,
    AirbyteStateType,
    AirbyteStreamState,
    ConfiguredAirbyteCatalog,
    StreamDescriptor,
    Type,
)
from source_slack.source import ChannelMessages, Channels, SourceSlack, Threads, Users


@pytest.fixture
def authenticator(legacy_token_config):
    return TokenAuthenticator(legacy_token_config["api_token"])


@pytest.mark.parametrize(
    "start_date, end_date, messages, stream_state, expected_result",
    (
        (
            "2020-01-01T00:00:00Z",
            "2020-01-02T00:00:00Z",
            [{"ts": 1577866844, "reply_count": 1}, {"ts": 1577877406, "reply_count": 2}],
            {},
            [
                # two thread-parent messages per each channel (reply_count > 0 only)
                {"channel": 3, "ts": 1577866844},
                {"channel": 3, "ts": 1577877406},
                {"channel": 4, "ts": 1577866844},
                {"channel": 4, "ts": 1577877406},
                {},
            ],
        ),
        ("2020-01-02T00:00:00Z", "2020-01-01T00:00:00Z", [], {}, [{}]),
        (
            "2020-01-01T00:00:00Z",
            "2020-01-02T00:00:00Z",
            [{"ts": 1577866844, "reply_count": 1}, {"ts": 1577877406, "reply_count": 1}],
            {"float_ts": 1577915266},
            [
                # two messages per each channel per datetime slice
                {"channel": 3, "ts": 1577866844},
                {"channel": 3, "ts": 1577877406},
                {"channel": 3, "ts": 1577866844},
                {"channel": 3, "ts": 1577877406},
                {"channel": 4, "ts": 1577866844},
                {"channel": 4, "ts": 1577877406},
                {"channel": 4, "ts": 1577866844},
                {"channel": 4, "ts": 1577877406},
                {},
            ],
        ),
    ),
)
def test_threads_stream_slices(
    requests_mock, authenticator, legacy_token_config, start_date, end_date, messages, stream_state, expected_result
):
    requests_mock.register_uri(
        "GET", "https://slack.com/api/conversations.history", [{"json": {"messages": messages}}, {"json": {"messages": messages}}]
    )
    start_date = pendulum.parse(start_date)
    end_date = end_date and pendulum.parse(end_date)
    stream = Threads(
        authenticator=authenticator,
        default_start_date=start_date,
        end_date=end_date,
        lookback_window=pendulum.Duration(days=legacy_token_config["lookback_window"]),
        channel_filter=legacy_token_config["channel_filter"],
    )
    stream.state = stream_state
    slices = list(stream.stream_slices(stream_state=stream_state))
    assert slices == expected_result


def _history_periods(slices, channel):
    return [(s["oldest"], s["latest"]) for s in slices if s.get("channel") == channel]


def _channel_messages(authenticator, config, start_date, end_date):
    channels = Channels(authenticator=authenticator, channel_filter=config["channel_filter"])
    return ChannelMessages(
        parent=channels,
        authenticator=authenticator,
        default_start_date=pendulum.parse(start_date),
        end_date=pendulum.parse(end_date),
        channel_filter=config["channel_filter"],
    )


def test_channel_messages_new_channel_starts_from_start_date(authenticator, legacy_token_config):
    stream = _channel_messages(authenticator, legacy_token_config, "2020-01-01T00:00:00Z", "2020-01-03T00:00:00Z")
    synced_until = pendulum.parse("2020-01-02T12:00:00Z").timestamp()
    stream.state = {"float_ts": synced_until, "channels": {"3": synced_until}}

    slices = list(stream.stream_slices(stream_state=stream.state))

    # Channel 3 resumes from its own cursor; channel 4 was just added and is read from the start date.
    assert _history_periods(slices, 3) == [(synced_until, pendulum.parse("2020-01-03T00:00:00Z").timestamp())]
    assert _history_periods(slices, 4)[0][0] == pendulum.parse("2020-01-01T00:00:00Z").timestamp()
    assert len(_history_periods(slices, 4)) == 2


def test_channel_messages_legacy_state_applies_to_configured_channels(authenticator, legacy_token_config):
    stream = _channel_messages(authenticator, legacy_token_config, "2020-01-01T00:00:00Z", "2020-01-03T00:00:00Z")
    synced_until = pendulum.parse("2020-01-02T12:00:00Z").timestamp()
    stream.state = {"float_ts": synced_until}

    slices = list(stream.stream_slices(stream_state=stream.state))

    assert _history_periods(slices, 3)[0][0] == synced_until
    assert _history_periods(slices, 4)[0][0] == synced_until
    assert stream.state["channels"] == {"3": synced_until, "4": synced_until}


def test_channel_messages_cursor_advances_past_empty_windows(requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", "https://slack.com/api/conversations.history", json={"ok": True, "messages": []})
    stream = _channel_messages(authenticator, legacy_token_config, "2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z")
    end_ts = pendulum.parse("2020-01-02T00:00:00Z").timestamp()

    for stream_slice in stream.stream_slices():
        list(stream.read_records(sync_mode=SyncMode.incremental, stream_slice=stream_slice))

    assert stream.state == {"channels": {"3": end_ts, "4": end_ts}, "float_ts": end_ts}


def test_threads_new_channel_skips_lookback_and_cursors_advance(requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    history = requests_mock.register_uri("GET", "https://slack.com/api/conversations.history", json={"ok": True, "messages": []})
    end_date = pendulum.parse("2020-01-03T00:00:00Z")
    synced_until = pendulum.parse("2020-01-02T12:00:00Z").timestamp()
    stream = Threads(
        authenticator=authenticator,
        default_start_date=pendulum.parse("2020-01-01T00:00:00Z"),
        end_date=end_date,
        lookback_window=pendulum.Duration(days=1),
        channel_filter=legacy_token_config["channel_filter"],
    )
    stream.state = {"float_ts": synced_until, "channels": {"3": synced_until}}

    assert list(stream.stream_slices()) == [{}]

    oldest_by_channel = {}
    for request in history.request_history:
        oldest_by_channel.setdefault(request.qs["channel"][0], float(request.qs["oldest"][0]))
    # Channel 3 rescans one lookback window before its cursor; new channel 4 starts at the start date.
    assert oldest_by_channel == {
        "3": synced_until - pendulum.Duration(days=1).total_seconds(),
        "4": pendulum.parse("2020-01-01T00:00:00Z").timestamp(),
    }
    assert stream.state["channels"] == {"3": end_date.timestamp(), "4": end_date.timestamp()}


def test_read_checkpoints_per_channel_state(requests_mock, legacy_token_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri(
        "GET",
        "https://slack.com/api/conversations.history",
        json={"ok": True, "messages": [{"ts": "1577923200.000100", "reply_count": 1}]},
    )
    requests_mock.register_uri(
        "GET",
        "https://slack.com/api/conversations.replies",
        json={"ok": True, "messages": [{"ts": "1577923200.000100"}, {"ts": "1577923300.000200"}]},
    )
    config = {**legacy_token_config, "start_date": "2020-01-01T00:00:00Z", "end_date": "2020-01-03T00:00:00Z"}
    synced_until = pendulum.parse("2020-01-02T12:00:00Z").timestamp()
    catalog = ConfiguredAirbyteCatalog.parse_obj(
        {
            "streams": [
                {
                    "stream": {"name": name, "json_schema": {}, "supported_sync_modes": ["incremental"]},
                    "sync_mode": "incremental",
                    "destination_sync_mode": "append",
                }
                for name in ("channel_messages", "threads")
            ]
        }
    )
    state = [
        AirbyteStateMessage(
            type=AirbyteStateType.STREAM,
            stream=AirbyteStreamState(
                stream_descriptor=StreamDescriptor(name=name),
                stream_state=AirbyteStateBlob.parse_obj({"float_ts": synced_until, "channels": {"3": synced_until}}),
            ),
        )
        for name in ("channel_messages", "threads")
    ]

    messages = list(SourceSlack().read(Mock(), config, catalog, state))

    final_state = {}
    for message in messages:
        if message.type == Type.STATE:
            final_state[message.state.stream.stream_descriptor.name] = message.state.stream.stream_state.dict()
    end_ts = pendulum.parse("2020-01-03T00:00:00Z").timestamp()
    assert final_state["channel_messages"] == {"float_ts": end_ts, "channels": {"3": end_ts, "4": end_ts}}
    assert final_state["threads"] == {"float_ts": end_ts, "channels": {"3": end_ts, "4": end_ts}}

    records = [m.record for m in messages if m.type == Type.RECORD]
    # Channel 4 was not in the saved state, so its history is read too.
    assert {(r.stream, r.data["channel_id"]) for r in records} == {
        ("channel_messages", 3),
        ("channel_messages", 4),
        ("threads", 3),
        ("threads", 4),
    }


@pytest.mark.parametrize("headers, expected_result", (({}, 5), ({"Retry-After": 15}, 15)))
def test_backoff(authenticator, headers, expected_result):
    stream = Users(authenticator=authenticator)
    assert stream.backoff_time(Mock(headers=headers)) == expected_result


def test_channels_stream_with_autojoin(authenticator) -> None:
    """
    The test uses the `conversations_list` fixture(autouse=true) as API mocker.
    """
    expected = [
        {'name': 'advice-data-architecture', 'id': 1, 'is_member': False},
        {'name': 'advice-data-orchestration', 'id': 2, 'is_member': True},
        {'name': 'airbyte-for-beginners', 'id': 3, 'is_member': False},
        {'name': 'good-reads', 'id': 4, 'is_member': True},
    ]
    stream = Channels(channel_filter=[], join_channels=True, authenticator=authenticator)
    assert list(stream.read_records(None)) == expected


def test_channels_resolved_via_channel_ids(requests_mock, authenticator) -> None:
    """channel_ids uses conversations.info and does not require conversations.list."""
    requests_mock.register_uri(
        "GET",
        re.compile(r"https://slack\.com/api/conversations\.info.*"),
        json={"ok": True, "channel": {"id": "C111", "name": "from-info", "is_member": True}},
    )
    stream = Channels(channel_filter=[], channel_ids=["C111"], join_channels=False, authenticator=authenticator)
    out = list(stream.read_records(None))
    assert len(out) == 1
    assert out[0]["id"] == "C111"
    assert out[0]["name"] == "from-info"


def test_threads_stream_slices_skips_messages_without_replies(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path
) -> None:
    # Isolate response cache so prior tests' conversations.history responses are not reused.
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri(
        "GET",
        "https://slack.com/api/conversations.history",
        [{"json": {"messages": [{"ts": 1577866844}]}}, {"json": {"messages": [{"ts": 1577866844}]}}],
    )
    stream = Threads(
        authenticator=authenticator,
        default_start_date=pendulum.parse("2020-01-01T00:00:00Z"),
        end_date=pendulum.parse("2020-01-02T00:00:00Z"),
        lookback_window=pendulum.Duration(days=legacy_token_config["lookback_window"]),
        channel_filter=legacy_token_config["channel_filter"],
    )
    slices = list(stream.stream_slices(stream_state={}))
    assert slices == [{}]
    

@pytest.fixture
def fast_backoff(monkeypatch):
    # The CDK sleeps for the backoff time plus a second before every retry.
    monkeypatch.setattr("source_slack.source.SlackStream.backoff_time", lambda self, response: 0.001)
    monkeypatch.setattr("airbyte_cdk.sources.streams.http.rate_limiting.time.sleep", lambda seconds: None)


def _read_all(stream):
    records = []
    for stream_slice in stream.stream_slices():
        records.extend(stream.read_records(sync_mode=SyncMode.incremental, stream_slice=stream_slice))
    return records


def _threads(authenticator, config, start_date, end_date):
    return Threads(
        authenticator=authenticator,
        default_start_date=pendulum.parse(start_date),
        end_date=pendulum.parse(end_date),
        lookback_window=pendulum.Duration(days=1),
        channel_filter=config["channel_filter"],
    )


HISTORY_URL = "https://slack.com/api/conversations.history"
REPLIES_URL = "https://slack.com/api/conversations.replies"
SYNCED_UNTIL = pendulum.parse("2020-01-01T00:00:00Z").timestamp()
END_TS = pendulum.parse("2020-01-02T00:00:00Z").timestamp()


def test_channel_messages_retries_transient_error_without_reusing_cached_failure(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path, fast_backoff
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    history = requests_mock.register_uri(
        "GET",
        HISTORY_URL,
        [
            {"json": {"ok": False, "error": "internal_error"}},
            {"json": {"ok": True, "messages": [{"ts": "1577880000.000100"}]}},
        ],
    )
    stream = _channel_messages(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    records = _read_all(stream)

    assert history.call_count == 3  # channel 3 fails once and is retried; channel 4 succeeds
    assert [r["channel_id"] for r in records] == [3, 4]
    assert stream.state["channels"] == {"3": END_TS, "4": END_TS}


@pytest.mark.parametrize("error", ("internal_error", "invalid_auth"))
def test_channel_messages_persistent_error_fails_without_advancing(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path, fast_backoff, error
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": False, "error": error})
    stream = _channel_messages(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    with pytest.raises(Exception):
        _read_all(stream)

    assert stream.state["channels"] == {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}


def test_channel_messages_channel_error_holds_back_only_that_channel(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": []})
    unreadable = requests_mock.register_uri("GET", f"{HISTORY_URL}?channel=3", json={"ok": False, "error": "not_in_channel"})
    stream = _channel_messages(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-03T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    _read_all(stream)

    # Channel 3's first window failed, so its second window is not requested and its cursor stays put.
    assert unreadable.call_count == 1
    assert stream.state["channels"] == {"3": SYNCED_UNTIL, "4": pendulum.parse("2020-01-03T00:00:00Z").timestamp()}


def test_threads_parent_scan_error_holds_back_channel(requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": []})
    requests_mock.register_uri("GET", f"{HISTORY_URL}?channel=3", json={"ok": False, "error": "channel_not_found"})
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    _read_all(stream)

    assert stream.state["channels"] == {"3": SYNCED_UNTIL, "4": END_TS}


def test_threads_retries_transient_replies_error(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path, fast_backoff
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": [{"ts": "1577880000.000100", "reply_count": 1}]})
    replies = requests_mock.register_uri(
        "GET",
        REPLIES_URL,
        [
            {"json": {"ok": False, "error": "internal_error"}},
            {"json": {"ok": True, "messages": [{"ts": "1577880000.000100"}, {"ts": "1577880100.000200"}]}},
        ],
    )
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    records = _read_all(stream)

    # Two thread parents per channel, plus one retry for channel 3's first thread.
    assert replies.call_count == 5
    assert len(records) == 8
    assert stream.state["channels"] == {"3": END_TS, "4": END_TS}


@pytest.mark.parametrize("error", ("internal_error", "missing_scope"))
def test_threads_persistent_replies_error_fails_without_advancing(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path, fast_backoff, error
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": [{"ts": "1577880000.000100", "reply_count": 1}]})
    requests_mock.register_uri("GET", REPLIES_URL, json={"ok": False, "error": error})
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    with pytest.raises(Exception):
        _read_all(stream)

    assert stream.state["channels"] == {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}


def test_threads_replies_channel_error_holds_back_only_that_channel(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": [{"ts": "1577880000.000100", "reply_count": 1}]})
    requests_mock.register_uri("GET", REPLIES_URL, json={"ok": True, "messages": [{"ts": "1577880000.000100"}]})
    requests_mock.register_uri("GET", f"{REPLIES_URL}?channel=3", json={"ok": False, "error": "not_in_channel"})
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    records = _read_all(stream)

    assert {r["channel_id"] for r in records} == {4}
    assert stream.state["channels"] == {"3": SYNCED_UNTIL, "4": END_TS}


def test_threads_deleted_thread_is_treated_as_empty(requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": [{"ts": "1577880000.000100", "reply_count": 1}]})
    requests_mock.register_uri("GET", REPLIES_URL, json={"ok": False, "error": "thread_not_found"})
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    assert _read_all(stream) == []
    assert stream.state["channels"] == {"3": END_TS, "4": END_TS}


def test_read_does_not_checkpoint_past_failed_history(requests_mock, legacy_token_config, monkeypatch, tmp_path, fast_backoff):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": False, "error": "internal_error"})
    config = {**legacy_token_config, "start_date": "2019-12-01T00:00:00Z", "end_date": "2020-01-02T00:00:00Z"}
    catalog = ConfiguredAirbyteCatalog.parse_obj(
        {
            "streams": [
                {
                    "stream": {"name": "channel_messages", "json_schema": {}, "supported_sync_modes": ["incremental"]},
                    "sync_mode": "incremental",
                    "destination_sync_mode": "append",
                }
            ]
        }
    )
    state = [
        AirbyteStateMessage(
            type=AirbyteStateType.STREAM,
            stream=AirbyteStreamState(
                stream_descriptor=StreamDescriptor(name="channel_messages"),
                stream_state=AirbyteStateBlob.parse_obj({"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}),
            ),
        )
    ]

    messages = []
    with pytest.raises(Exception):
        for message in SourceSlack().read(Mock(), config, catalog, state):
            messages.append(message)

    assert [m for m in messages if m.type == Type.RECORD] == []
    assert [m for m in messages if m.type == Type.STATE] == []


def test_threads_stops_requesting_replies_after_channel_error(
    requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path
):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    parents = [{"ts": f"157788000{i}.000100", "reply_count": 1} for i in range(3)]
    requests_mock.register_uri("GET", HISTORY_URL, json={"ok": True, "messages": parents})
    requests_mock.register_uri("GET", REPLIES_URL, json={"ok": True, "messages": []})
    unreadable = requests_mock.register_uri("GET", f"{REPLIES_URL}?channel=3", json={"ok": False, "error": "not_in_channel"})
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")
    stream.state = {"channels": {"3": SYNCED_UNTIL, "4": SYNCED_UNTIL}}

    _read_all(stream)

    assert unreadable.call_count == 1
    assert stream.state["channels"] == {"3": SYNCED_UNTIL, "4": END_TS}


def test_read_records_skips_channel_that_already_failed(requests_mock, authenticator, legacy_token_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REQUEST_CACHE_PATH", str(tmp_path))
    replies = requests_mock.register_uri("GET", REPLIES_URL, json={"ok": False, "error": "not_in_channel"})
    stream = _threads(authenticator, legacy_token_config, "2019-12-01T00:00:00Z", "2020-01-02T00:00:00Z")

    for ts in ("1577880000.000100", "1577880001.000100"):
        assert list(stream.read_records(sync_mode=SyncMode.incremental, stream_slice={"channel": 3, "ts": ts})) == []

    assert replies.call_count == 1
