from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal

from .config import AppConfig, configured_entity_ids, parse_options
from .ha_client import HaState, HomeAssistantClient, StateCache
from .mqtt import MqttBridge, SeasonMqttFacade
from .outdoor import OutdoorEngine, OutdoorState
from .persistence import StateStore


LOGGER = logging.getLogger(__name__)
OPTIONS_FILE = Path("/data/options.json")
DATABASE_FILE = Path("/data/dh_climate.db")
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0-local")
OUTDOOR_TICK_SECONDS = 300.0


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
        self.command_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._calculation_lock = asyncio.Lock()
        self._last_outdoor_state: OutdoorState | None = None

        loop = asyncio.get_running_loop()
        self.mqtt = MqttBridge(
            host=os.environ["MQTT_HOST"],
            port=int(os.environ["MQTT_PORT"]),
            username=os.environ.get("MQTT_USER", ""),
            password=os.environ.get("MQTT_PASSWORD", ""),
            loop=loop,
        )
        self.facade = SeasonMqttFacade(
            bridge=self.mqtt,
            app_version=APP_VERSION,
            started_at=self.started_at,
            command_queue=self.command_queue,
        )
        self.ha = HomeAssistantClient(
            token=os.environ["SUPERVISOR_TOKEN"],
            entity_ids=self.cache.allowed,
        )

    async def run(self) -> None:
        self.facade.start()
        self.facade.set_available(False)

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
            asyncio.create_task(self._command_loop(), name="season-commands"),
            asyncio.create_task(self._periodic_outdoor_loop(), name="outdoor-tick"),
        ]
        try:
            await self.stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.facade.stop()

    async def _on_snapshot(self, states: list[HaState]) -> None:
        self.cache.replace_snapshot(states)
        await self._recalculate(
            observed_at=datetime.now(timezone.utc),
            record_sample=True,
        )

    async def _on_state(self, state: HaState) -> None:
        if not self.cache.apply(state):
            return
        await self._recalculate(
            observed_at=state.last_updated,
            record_sample=True,
        )

    async def _on_connection(self, connected: bool) -> None:
        if not connected:
            self.cache.clear()
            self.facade.set_available(False)
            return
        self.facade.set_available(
            self._last_outdoor_state.available
            if self._last_outdoor_state is not None
            else False
        )

    async def _recalculate(
        self,
        *,
        observed_at: datetime,
        record_sample: bool,
    ) -> OutdoorState:
        async with self._calculation_lock:
            state = self.outdoor.evaluate(
                self.cache.values(),
                observed_at=observed_at,
                record_sample=record_sample,
            )
            self._last_outdoor_state = state
            self.facade.publish_state(state)
            self.facade.set_available(state.available)
            return state

    async def _periodic_outdoor_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=OUTDOOR_TICK_SECONDS,
                )
            except TimeoutError:
                await self._recalculate(
                    observed_at=datetime.now(timezone.utc),
                    record_sample=False,
                )

    async def _command_loop(self) -> None:
        while not self.stop_event.is_set():
            command, payload = await self.command_queue.get()
            try:
                await self._handle_season_command(command, payload)
            except Exception:
                LOGGER.exception(
                    "Season command failed: command=%s payload=%s",
                    command,
                    payload,
                )
            finally:
                self.command_queue.task_done()

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
        await self._recalculate(
            observed_at=datetime.now(timezone.utc),
            record_sample=False,
        )


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
