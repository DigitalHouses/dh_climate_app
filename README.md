# Репозиторий DigitalHouses Climate App

Этот репозиторий публикует **DigitalHouses Climate App** для Home Assistant.

Само приложение Home Assistant находится в каталоге:

```text
dh_climate_app/
```

- [Обзор приложения](dh_climate_app/README.md)
- [Пользовательская документация](dh_climate_app/DOCS.md)
- [Архитектура](dh_climate_app/docs/ARCHITECTURE.md)
- [План приёмочного тестирования HAOS](dh_climate_app/HAOS_TEST_PLAN.md)

URL репозитория для Store приложений Home Assistant:

```text
https://github.com/DigitalHouses/dh_climate_app
```

## Обновление Experimental-версии

Репозиторий имеет стандартную структуру пользовательского репозитория приложений Home Assistant. После публикации новой версии в `main` обновите метаданные Store:

```bash
ha store reload
```

Не используйте `ha store repair` для обычных обновлений. Repair предназначен только для восстановления повреждённого локального клона репозитория Supervisor.
