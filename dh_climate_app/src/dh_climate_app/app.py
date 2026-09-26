from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal

from .climate_log import ClimateLog
from .config import AppConfig, configured_entity_ids, parse_options
from .core import Profile, Season
from .devices import compile_room_devices
from .events import ClimateEventEngine
from .executor import DeviceExecutor, ReconcileSummary
from .ha_client import HaState, HomeAssistantClient, StateCache
from .humidity import HumidityEngine, HumidityState
from .mqtt import ClimateMqttFacade, MqttBridge, MqttCommand
from .outdoor import OutdoorEngine, OutdoorState
from .persistence import StateStore
from .problems import Problem, collect_problems
from .rooms import RoomEngine, RoomState
from .telemetry import TelemetryClient, TelemetryRunner
from .weather import WeatherState, build_weather_state, select_weather_source


LOGGER = logging.getLogger(__name__)
OPTIONS_FILE = Path("/data/options.json")
DATABASE_FILE = Path("/data/dh_climate.db")
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0-local")
RUNTIME_TICK_SECONDS = 10.0
WEATHER_FORECAST_REFRESH_SECONDS = 15 * 60
SEASON_RANGE_DEBOUNCE_SECONDS = 0.1

ROOM_TARGET_COMMANDS = {
    "heat_day": (Season.HEAT, Profile.DAY),
    "heat_night": (Season.HEAT, Profile.NIGHT),
    "heat_away": (Season.HEAT, Profile.AWAY),
    "heat_antifreeze": (Season.HEAT, Profile.ANTIFREEZE),
    "cool_day": (Season.COOL, Profile.DAY),
    "cool_night": (Season.COOL, Profile.NIGHT),
    "cool_away": (Season.COOL, Profile.AWAY),
}


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
        self.events = ClimateEventEngine()
        self.weather_source = select_weather_source(
            config.outdoor.temperature_sources,
            config.outdoor.humidity_sources,
        )

        self.command_queue: asyncio.Queue[MqttCommand] = asyncio.Queue()
        self._calculation_lock = asyncio.Lock()
        self._ha_connected = False
        self._last_outdoor_state: OutdoorState | None = None
        self._last_room_states: dict[str, RoomState] = {}
        self._last_humidity_states: dict[str, HumidityState] = {}
        self._last_weather_state: WeatherState | None = None
        self._weather_forecast_response: object | None = None
        self._weather_source_last_updated: datetime | None = None
        self._weather_forecast_fetched_at: datetime | None = None
        self._last_reconcile = ReconcileSummary(commands=0, problems=())
        self._last_problems: tuple[Problem, ...] = ()
        self._last_room_log_signatures: dict[str, tuple[object, ...]] = {}

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
            weather_enabled=self.weather_source is not None,
        )
        self.ha = HomeAssistantClient(
            token=os.environ["SUPERVISOR_TOKEN"],
            entity_ids=self.cache.allowed,
        )
        self.climate_log = ClimateLog(self.ha)
        self.executor = DeviceExecutor(
            self.ha,
            climate_log=self.climate_log,
        )
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
            await self.climate_log.close()
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
            self.events.reset()
            self._weather_source_last_updated = None
            self._weather_forecast_fetched_at = None
            self._weather_forecast_response = None
            self.facade.set_season_available(False)
            self.facade.set_rooms_available(False)
            return

        await self._recalculate(
            observed_at=datetime.now(timezone.utc),
            record_outdoor_sample=False,
        )

    async def _evaluate_weather(
        self,
        snapshot: dict[str, HaState],
        *,
        observed_at: datetime,
    ) -> WeatherState | None:
        if self.weather_source is None:
            return None

        source_state = snapshot.get(self.weather_source)
        if source_state is None:
            return WeatherState(
                source_entity=self.weather_source,
                condition="unknown",
                precipitation_type="unknown",
                precipitation_mm=None,
                forecast_at=None,
                observed_at=observed_at,
            )

        if source_state.state in {"unknown", "unavailable"}:
            return build_weather_state(
                source_entity=self.weather_source,
                ha_state=source_state,
                hourly_forecast_response=None,
                observed_at=observed_at,
            )

        forecast_expired = (
            self._weather_forecast_fetched_at is None
            or (
                observed_at - self._weather_forecast_fetched_at
            ).total_seconds() >= WEATHER_FORECAST_REFRESH_SECONDS
        )
        needs_forecast = (
            self._weather_forecast_fetched_at is None
            or self._weather_source_last_updated != source_state.last_updated
            or forecast_expired
        )
        if needs_forecast:
            try:
                self._weather_forecast_response = await self.ha.call_service_response(
                    "weather",
                    "get_forecasts",
                    {
                        "entity_id": self.weather_source,
                        "type": "hourly",
                    },
                )
            except Exception:
                LOGGER.warning(
                    "Hourly weather forecast unavailable for %s",
                    self.weather_source,
                    exc_info=True,
                )
                self._weather_forecast_response = None
            self._weather_source_last_updated = source_state.last_updated
            self._weather_forecast_fetched_at = observed_at

        return build_weather_state(
            source_entity=self.weather_source,
            ha_state=source_state,
            hourly_forecast_response=(
                self._weather_forecast_response
                if isinstance(self._weather_forecast_response, dict)
                else None
            ),
            observed_at=observed_at,
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
            weather_state = await self._evaluate_weather(
                snapshot,
                observed_at=observed_at,
            )
            room_states = self.rooms.evaluate_all(
                values,
                season=outdoor_state.season,
            )
            humidity_states = self.humidity.evaluate_all(values)

            for room_id, room_state in room_states.items():
                signature = (
                    room_state.season.value,
                    room_state.effective_profile.value,
                    room_state.climate_control_enabled,
                    room_state.control_action.value,
                    room_state.control_target_temperature,
                    room_state.window_state,
                )
                if self._last_room_log_signatures.get(room_id) != signature:
                    self._last_room_log_signatures[room_id] = signature
                    self.climate_log.write2climate_log(
                        f"ROOM · {room_id}",
                        (
                            f"season={room_state.season.value}"
                            f" temp={room_state.current_temperature}"
                            f" target={room_state.control_target_temperature}"
                            f" profile={room_state.effective_profile.value}"
                            f" control={room_state.control_action.value}"
                            f" enabled={room_state.climate_control_enabled}"
                            f" window={room_state.window_state}"
                        ),
                    )

            self._last_outdoor_state = outdoor_state
            self._last_room_states = room_states
            self._last_humidity_states = humidity_states
            self._last_weather_state = weather_state

            self.facade.publish_season(outdoor_state)
            if weather_state is not None:
                self.facade.publish_weather(weather_state)

            for room_id, room_state in room_states.items():
                profile_targets = {
                    key: self.store.get_room_target(room_id, season, profile)
                    for key, (season, profile) in ROOM_TARGET_COMMANDS.items()
                }
                self.facade.publish_room(
                    room_state,
                    profile_targets=profile_targets,
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

            for event in self.events.observe(
                outdoor=outdoor_state,
                weather=weather_state,
                rooms=room_states,
                problems=self._last_problems,
                observed_at=observed_at,
            ):
                self.facade.publish_event(event)

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
        deferred: MqttCommand | None = None
        range_commands = {"target_temp_low", "target_temp_high"}

        while not self.stop_event.is_set():
            command = deferred
            if command is None:
                command = await self.command_queue.get()
            else:
                deferred = None

            if command.scope == "season" and command.command in range_commands:
                batch = [command]
                try:
                    await asyncio.sleep(SEASON_RANGE_DEBOUNCE_SECONDS)
                    while True:
                        try:
                            queued = self.command_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if (
                            queued.scope == "season"
                            and queued.command in range_commands
                        ):
                            batch.append(queued)
                            continue
                        deferred = queued
                        break

                    await self._handle_season_range_commands(batch)
                    if self._ha_connected:
                        await self._recalculate(
                            observed_at=datetime.now(timezone.utc),
                            record_outdoor_sample=False,
                        )
                except Exception:
                    LOGGER.exception(
                        "MQTT season range command failed: %s",
                        [(item.command, item.payload) for item in batch],
                    )
                finally:
                    for _ in batch:
                        self.command_queue.task_done()
                continue

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
        elif command.scope == "target":
            if command.room_id is None:
                raise ValueError("target command requires room_id")
            await self._handle_room_profile_target_command(
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

        await self._handle_season_range_commands(
            [MqttCommand(scope="season", command=command, payload=payload)]
        )

    async def _handle_season_range_commands(
        self,
        commands: list[MqttCommand],
    ) -> None:
        thresholds = self.store.get_season_thresholds()
        heat = thresholds.heat
        cool = thresholds.cool

        for item in commands:
            if item.scope != "season":
                raise ValueError("season range batch contains non-season command")
            try:
                value = round(float(item.payload), 1)
            except ValueError as exc:
                raise ValueError(
                    f"invalid numeric season command: {item.payload}"
                ) from exc

            if item.command == "target_temp_low":
                heat = value
            elif item.command == "target_temp_high":
                cool = value
            else:
                raise ValueError(
                    f"unsupported season range command: {item.command}"
                )

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
            # The room climate facade is read-only during interseason. Ignore
            # commands from HA/HomeKit until a real HEAT/COOL season is active.
            if state.season is Season.OFF:
                return
            mode = payload.strip().lower()
            if mode == "off":
                self.store.set_climate_control_enabled(room_id, False)
                return
            if mode == "auto":
                self.store.set_climate_control_enabled(room_id, True)
                return
            raise ValueError(
                f"hvac_mode={mode} is not supported; use off or auto"
            )

        if command == "target_temperature":
            if state.season is Season.OFF:
                return
            try:
                target = round(float(payload), 1)
            except ValueError as exc:
                raise ValueError(f"invalid room target={payload}") from exc
            if not 5.0 <= target <= 35.0:
                raise ValueError("room target must be between 5 and 35")

            # Native thermostat contract: changing the climate target always
            # changes the profile that is actually active for the user now.
            self.store.set_room_target(
                room_id,
                state.season,
                state.effective_profile,
                target,
            )
            return

        raise ValueError(f"unsupported room command={command}")

    async def _handle_room_profile_target_command(
        self,
        room_id: str,
        command: str,
        payload: str,
    ) -> None:
        if room_id not in self._last_room_states:
            raise ValueError(f"room state is not available: {room_id}")
        try:
            season, profile = ROOM_TARGET_COMMANDS[command]
        except KeyError as exc:
            raise ValueError(f"unsupported room target setting={command}") from exc
        try:
            target = round(float(payload), 1)
        except ValueError as exc:
            raise ValueError(f"invalid room target={payload}") from exc
        if not 5.0 <= target <= 35.0:
            raise ValueError("room target must be between 5 and 35")
        self.store.set_room_target(room_id, season, profile, target)

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
