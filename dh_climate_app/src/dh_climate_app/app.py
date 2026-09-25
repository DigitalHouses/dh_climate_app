from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal

from .config import AppConfig, configured_entity_ids, parse_options
from .core import Profile, Season
from .devices import compile_room_devices
from .executor import DeviceExecutor, ReconcileSummary
from .ha_client import HaState, HomeAssistantClient, StateCache
from .humidity import HumidityEngine, HumidityState
from .mqtt import ClimateMqttFacade, MqttBridge, MqttCommand
from .outdoor import OutdoorEngine, OutdoorState
from .persistence import StateStore
from .problems import Problem, collect_problems
from .rooms import ProfileEditOverlay, RoomEngine, RoomState
from .telemetry import TelemetryClient, TelemetryRunner


LOGGER = logging.getLogger(__name__)
OPTIONS_FILE = Path("/data/options.json")
DATABASE_FILE = Path("/data/dh_climate.db")
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0-local")
RUNTIME_TICK_SECONDS = 10.0


def load_options(path: Path = OPTIONS_FILE) -> AppConfig:
    with path.open("r", encoding="utf-8") as handle:
        return parse_options(json.load(handle))


class ClimateRuntime:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.started_at = datetime.now(timezone.utc)
        self.stop_event = asyncio.Event()
        self.cache = StateCache(configured_entity_ids(config))
        self.store = StateStore(DATABASE_FILE)
        self.store.initialize(config)
        if not self.store.integrity_check():
            raise RuntimeError("SQLite integrity_check failed")

        self.outdoor = OutdoorEngine(
            config=config.outdoor,
            store=self.store,
            hysteresis=config.global_config.hysteresis,
        )
        self.rooms = RoomEngine(config=config, store=self.store)
        self.humidity = HumidityEngine(config=config, store=self.store)
        self.profile_overlay = ProfileEditOverlay(idle_timeout_seconds=10.0)

        self.command_queue: asyncio.Queue[MqttCommand] = asyncio.Queue()
        self._calculation_lock = asyncio.Lock()
        self._ha_connected = False
        self._last_outdoor_state: OutdoorState | None = None
        self._last_room_states: dict[str, RoomState] = {}
        self._last_humidity_states: dict[str, HumidityState] = {}
        self._last_reconcile = ReconcileSummary(commands=0, problems=())
        self._last_problems: tuple[Problem, ...] = ()

        loop = asyncio.get_running_loop()
        self.mqtt = MqttBridge(
            host=os.environ["MQTT_HOST"],
            port=int(os.environ["MQTT_PORT"]),
            username=os.environ.get("MQTT_USER", ""),
            password=os.environ.get("MQTT_PASSWORD", ""),
            loop=loop,
        )
        self.facade = ClimateMqttFacade(
            bridge=self.mqtt,
            app_version=APP_VERSION,
            started_at=self.started_at,
            rooms=config.rooms,
            command_queue=self.command_queue,
        )
        self.ha = HomeAssistantClient(
            token=os.environ["SUPERVISOR_TOKEN"],
            entity_ids=self.cache.allowed,
        )
        self.executor = DeviceExecutor(self.ha)
        self.telemetry = TelemetryClient(
            enabled=config.telemetry_enabled,
            version=APP_VERSION,
        )
        self.telemetry_runner = TelemetryRunner(self.telemetry)

    async def run(self) -> None:
        self.facade.start()
        self.telemetry_runner.start()
        self.facade.set_season_available(False)
        self.facade.set_rooms_available(False)

        tasks = [
            asyncio.create_task(
                self.ha.run_forever(
                    on_snapshot=self._on_snapshot,
                    on_state=self._on_state,
                    on_connection=self._on_connection,
                    stop_event=self.stop_event,
                ),
                name="ha-client",
            ),
            asyncio.create_task(self._command_loop(), name="mqtt-commands"),
            asyncio.create_task(self._periodic_loop(), name="runtime-tick"),
        ]
        try:
            await self.stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.telemetry_runner.stop()
            self.facade.stop()

    async def _on_snapshot(self, states: list[HaState]) -> None:
        self.cache.replace_snapshot(states)
        await self._recalculate(
            observed_at=datetime.now(timezone.utc),
            record_outdoor_sample=True,
        )

    async def _on_state(self, state: HaState) -> None:
        if not self.cache.apply(state):
            return
        await self._recalculate(
            observed_at=state.last_updated,
            record_outdoor_sample=True,
        )

    async def _on_connection(self, connected: bool) -> None:
        self._ha_connected = connected
        if not connected:
            self.cache.clear()
            self.facade.set_season_available(False)
            self.facade.set_rooms_available(False)
            return

        await self._recalculate(
            observed_at=datetime.now(timezone.utc),
            record_outdoor_sample=False,
        )

    async def _recalculate(
        self,
        *,
        observed_at: datetime,
        record_outdoor_sample: bool,
    ) -> OutdoorState:
        async with self._calculation_lock:
            values = self.cache.values()
            snapshot = self.cache.snapshot()
            outdoor_state = self.outdoor.evaluate(
                snapshot,
                observed_at=observed_at,
                record_sample=record_outdoor_sample,
            )
            room_states = self.rooms.evaluate_all(
                values,
                season=outdoor_state.season,
            )
            humidity_states = self.humidity.evaluate_all(values)

            self._last_outdoor_state = outdoor_state
            self._last_room_states = room_states
            self._last_humidity_states = humidity_states

            self.facade.publish_season(outdoor_state)

            for room_id, room_state in room_states.items():
                published_profile = self.profile_overlay.selected(
                    room_id,
                    effective_profile=room_state.effective_profile,
                )
                published_target = room_state.target_temperature
                if room_state.season is not Season.OFF:
                    selected_target = self.store.get_room_target(
                        room_id,
                        room_state.season,
                        published_profile,
                    )
                    if selected_target is not None:
                        published_target = selected_target

                self.facade.publish_room(
                    room_state,
                    published_profile=published_profile.value,
                    published_target=published_target,
                )

            for humidity_state in humidity_states.values():
                self.facade.publish_humidity(humidity_state)

            system_available = self._ha_connected and outdoor_state.available
            self.facade.set_season_available(system_available)

            if self._ha_connected:
                desired = compile_room_devices(
                    config=self.config,
                    room_states=room_states,
                    humidity_states=humidity_states,
                    outdoor_temperature=outdoor_state.current_temperature,
                )
                self._last_reconcile = await self.executor.reconcile(
                    desired,
                    snapshot,
                )
            else:
                self._last_reconcile = ReconcileSummary(commands=0, problems=())

            self._last_problems = collect_problems(
                outdoor=outdoor_state,
                rooms=room_states,
                humidity=humidity_states,
                execution=self._last_reconcile.problems,
            )
            self.facade.publish_problems(self._last_problems)

            return outdoor_state

    async def _periodic_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=RUNTIME_TICK_SECONDS,
                )
            except TimeoutError:
                if self._ha_connected:
                    await self._recalculate(
                        observed_at=datetime.now(timezone.utc),
                        record_outdoor_sample=False,
                    )

    async def _command_loop(self) -> None:
        while not self.stop_event.is_set():
            command = await self.command_queue.get()
            try:
                await self._handle_command(command)
            except Exception:
                LOGGER.exception(
                    "MQTT command failed: scope=%s room=%s command=%s payload=%s",
                    command.scope,
                    command.room_id,
                    command.command,
                    command.payload,
                )
            finally:
                self.command_queue.task_done()

    async def _handle_command(self, command: MqttCommand) -> None:
        if command.scope == "system":
            await self._handle_system_command(command.command, command.payload)
        elif command.scope == "season":
            await self._handle_season_command(command.command, command.payload)
        elif command.scope == "room":
            if command.room_id is None:
                raise ValueError("room command requires room_id")
            await self._handle_room_command(
                command.room_id,
                command.command,
                command.payload,
            )
        elif command.scope == "humidity":
            if command.room_id is None:
                raise ValueError("humidity command requires room_id")
            await self._handle_humidity_command(
                command.room_id,
                command.command,
                command.payload,
            )
        else:
            raise ValueError(f"unsupported command scope={command.scope}")

        if self._ha_connected:
            await self._recalculate(
                observed_at=datetime.now(timezone.utc),
                record_outdoor_sample=False,
            )

    async def _handle_system_command(self, command: str, payload: str) -> None:
        if command == "delete_telemetry":
            if payload.strip().upper() != "DELETE":
                raise ValueError("invalid delete telemetry command payload")
            deleted = await asyncio.to_thread(self.telemetry.delete)
            if not deleted:
                raise RuntimeError("telemetry deletion failed")
            return
        raise ValueError(f"unsupported system command={command}")

    async def _handle_season_command(self, command: str, payload: str) -> None:
        if command == "hvac_mode":
            if payload != "heat_cool":
                raise ValueError("season thermostat supports only heat_cool")
            return

        try:
            value = round(float(payload), 1)
        except ValueError as exc:
            raise ValueError(f"invalid numeric season command: {payload}") from exc

        thresholds = self.store.get_season_thresholds()
        heat = thresholds.heat
        cool = thresholds.cool

        if command == "target_temp_low":
            heat = value
        elif command == "target_temp_high":
            cool = value
        else:
            raise ValueError(f"unsupported season command: {command}")

        self.outdoor.set_thresholds(heat=heat, cool=cool)

    async def _handle_room_command(
        self,
        room_id: str,
        command: str,
        payload: str,
    ) -> None:
        state = self._last_room_states.get(room_id)
        if state is None:
            raise ValueError(f"room state is not available: {room_id}")

        if command == "hvac_mode":
            mode = payload.strip().lower()
            if mode == "off":
                self.store.set_climate_control_enabled(room_id, False)
                return
            if state.season is Season.HEAT and mode == "heat":
                self.store.set_climate_control_enabled(room_id, True)
                return
            if state.season is Season.COOL and mode == "cool":
                self.store.set_climate_control_enabled(room_id, True)
                return
            if state.season is Season.OFF and mode in {"heat", "cool"}:
                return
            raise ValueError(
                f"hvac_mode={mode} is not allowed in season={state.season.value}"
            )

        if command == "profile":
            try:
                profile = Profile(payload.strip().lower())
            except ValueError as exc:
                raise ValueError(f"unsupported room profile={payload}") from exc
            if profile is Profile.ANTIFREEZE and state.season is not Season.HEAT:
                raise ValueError("antifreeze profile is only editable in HEAT season")
            self.profile_overlay.select(
                room_id,
                profile,
                effective_profile=state.effective_profile,
            )
            return

        if command == "target_temperature":
            if state.season is Season.OFF:
                return
            try:
                target = round(float(payload), 1)
            except ValueError as exc:
                raise ValueError(f"invalid room target={payload}") from exc
            if not 5.0 <= target <= 35.0:
                raise ValueError("room target must be between 5 and 35")

            selected_profile = self.profile_overlay.selected(
                room_id,
                effective_profile=state.effective_profile,
            )
            if (
                selected_profile is Profile.ANTIFREEZE
                and state.season is not Season.HEAT
            ):
                raise ValueError("antifreeze target exists only in HEAT season")
            self.store.set_room_target(
                room_id,
                state.season,
                selected_profile,
                target,
            )
            self.profile_overlay.touch(room_id)
            return

        raise ValueError(f"unsupported room command={command}")

    async def _handle_humidity_command(
        self,
        room_id: str,
        command: str,
        payload: str,
    ) -> None:
        if room_id not in self._last_humidity_states:
            raise ValueError(f"humidity is not configured for room={room_id}")

        if command == "state":
            state = payload.strip().upper()
            if state == "ON":
                self.store.set_humidity_control_enabled(room_id, True)
                return
            if state == "OFF":
                self.store.set_humidity_control_enabled(room_id, False)
                return
            raise ValueError(f"invalid humidity state={payload}")

        if command == "target":
            try:
                target = round(float(payload), 1)
            except ValueError as exc:
                raise ValueError(f"invalid humidity target={payload}") from exc
            if not 0.0 <= target <= 100.0:
                raise ValueError("humidity target must be between 0 and 100")
            self.store.set_humidity_target(room_id, target)
            return

        raise ValueError(f"unsupported humidity command={command}")


async def async_main() -> int:
    config = load_options()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runtime = ClimateRuntime(config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, runtime.stop_event.set)
        except NotImplementedError:
            pass

    LOGGER.info("Starting DigitalHouses Climate App %s", APP_VERSION)
    await runtime.run()
    LOGGER.info("DigitalHouses Climate App stopped")
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
