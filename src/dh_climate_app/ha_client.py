from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib import request as urllib_request

import websockets


LOGGER = logging.getLogger(__name__)


def _parse_timestamp(value: object) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class HaState:
    entity_id: str
    state: str
    attributes: Mapping[str, Any]
    last_changed: datetime
    last_updated: datetime

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "HaState":
        return cls(
            entity_id=str(payload["entity_id"]),
            state=str(payload.get("state", "unknown")),
            attributes=dict(payload.get("attributes") or {}),
            last_changed=_parse_timestamp(payload.get("last_changed")),
            last_updated=_parse_timestamp(payload.get("last_updated")),
        )


class StateCache:
    """Current Home Assistant state with stale-event protection."""

    def __init__(self, allowed_entity_ids: Iterable[str]) -> None:
        self.allowed = frozenset(entity_id for entity_id in allowed_entity_ids if entity_id)
        self._states: dict[str, HaState] = {}

    def replace_snapshot(self, states: Iterable[HaState]) -> None:
        self._states = {
            state.entity_id: state
            for state in states
            if state.entity_id in self.allowed
        }

    def apply(self, state: HaState) -> bool:
        if state.entity_id not in self.allowed:
            return False
        previous = self._states.get(state.entity_id)
        if previous is not None and state.last_updated < previous.last_updated:
            return False
        self._states[state.entity_id] = state
        return True

    def clear(self) -> None:
        self._states.clear()

    def get(self, entity_id: str) -> HaState | None:
        return self._states.get(entity_id)

    def values(self) -> dict[str, str]:
        return {
            entity_id: state.state
            for entity_id, state in self._states.items()
        }

    def snapshot(self) -> dict[str, HaState]:
        return dict(self._states)


SnapshotCallback = Callable[[list[HaState]], Awaitable[None]]
StateCallback = Callable[[HaState], Awaitable[None]]
ConnectionCallback = Callable[[bool], Awaitable[None]]


class HomeAssistantClient:
    """Supervisor REST + WebSocket adapter.

    Reconnect contract:
    subscribe to state_changed first, start buffering events, obtain a fresh
    REST snapshot, then consume the buffered/live queue. StateCache timestamp
    ordering prevents an older buffered event from overwriting a newer
    snapshot state.
    """

    def __init__(
        self,
        *,
        token: str,
        entity_ids: Iterable[str],
        rest_base: str = "http://supervisor/core/api",
        websocket_url: str = "ws://supervisor/core/websocket",
        reconnect_delay_seconds: float = 5.0,
    ) -> None:
        self.token = token
        self.entity_ids = frozenset(entity_ids)
        self.rest_base = rest_base.rstrip("/")
        self.websocket_url = websocket_url
        self.reconnect_delay_seconds = reconnect_delay_seconds

    async def get_states(self) -> list[HaState]:
        payload = await asyncio.to_thread(self._request_json, "GET", "/states", None)
        if not isinstance(payload, list):
            raise RuntimeError("Home Assistant /states response is not a list")
        return [
            HaState.from_payload(item)
            for item in payload
            if isinstance(item, Mapping)
            and str(item.get("entity_id", "")) in self.entity_ids
        ]

    async def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, Any],
    ) -> Any:
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/services/{domain}/{service}",
            dict(data),
        )

    async def run_forever(
        self,
        *,
        on_snapshot: SnapshotCallback,
        on_state: StateCallback,
        on_connection: ConnectionCallback | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self._run_session(
                    on_snapshot=on_snapshot,
                    on_state=on_state,
                    on_connection=on_connection,
                    stop_event=stop,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Home Assistant connection failed")
                if on_connection is not None:
                    await on_connection(False)
                try:
                    await asyncio.wait_for(
                        stop.wait(),
                        timeout=self.reconnect_delay_seconds,
                    )
                except TimeoutError:
                    pass

    async def _run_session(
        self,
        *,
        on_snapshot: SnapshotCallback,
        on_state: StateCallback,
        on_connection: ConnectionCallback | None,
        stop_event: asyncio.Event,
    ) -> None:
        async with websockets.connect(
            self.websocket_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_size=2 * 1024 * 1024,
        ) as websocket:
            await self._authenticate(websocket)
            await self._subscribe_state_changed(websocket)

            queue: asyncio.Queue[HaState] = asyncio.Queue()
            reader = asyncio.create_task(
                self._reader_loop(websocket, queue),
                name="ha-state-reader",
            )
            try:
                snapshot = await self.get_states()
                await on_snapshot(snapshot)
                if on_connection is not None:
                    await on_connection(True)

                while not stop_event.is_set():
                    state = await queue.get()
                    try:
                        await on_state(state)
                    finally:
                        queue.task_done()
            finally:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
                if on_connection is not None:
                    await on_connection(False)

    async def _authenticate(self, websocket: Any) -> None:
        hello = json.loads(await websocket.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected HA websocket hello: {hello}")
        await websocket.send(
            json.dumps({"type": "auth", "access_token": self.token})
        )
        auth = json.loads(await websocket.recv())
        if auth.get("type") != "auth_ok":
            raise RuntimeError(f"Home Assistant websocket authentication failed: {auth}")

    @staticmethod
    async def _subscribe_state_changed(websocket: Any) -> None:
        request_id = 1
        await websocket.send(
            json.dumps(
                {
                    "id": request_id,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                }
            )
        )
        result = json.loads(await websocket.recv())
        if (
            result.get("type") != "result"
            or result.get("id") != request_id
            or result.get("success") is not True
        ):
            raise RuntimeError(f"Failed to subscribe to state_changed: {result}")

    async def _reader_loop(
        self,
        websocket: Any,
        queue: asyncio.Queue[HaState],
    ) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            state = self.parse_state_changed(message)
            if state is not None and state.entity_id in self.entity_ids:
                await queue.put(state)

    @staticmethod
    def parse_state_changed(message: Mapping[str, Any]) -> HaState | None:
        if message.get("type") != "event":
            return None
        event = message.get("event")
        if not isinstance(event, Mapping):
            return None
        if event.get("event_type") != "state_changed":
            return None
        data = event.get("data")
        if not isinstance(data, Mapping):
            return None
        new_state = data.get("new_state")
        if not isinstance(new_state, Mapping):
            return None
        return HaState.from_payload(new_state)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> Any:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            f"{self.rest_base}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib_request.urlopen(req, timeout=15) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else None
