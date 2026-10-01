# Инструкция по обновлению Experimental

Это каноническая процедура обновления Experimental-канала DigitalHouses Climate App, который сейчас доставляется через сборку из исходников.

Репозиторий:

```text
https://github.com/DigitalHouses/dh_climate_app
```

Slug репозитория Store:

```text
8d59ce70
```

Slug установленного App:

```text
8d59ce70_dh_climate_app
```

## Семантика репозитория Supervisor

Штатное обновление Store:

```text
GitHub main продвинулся
        ↓
ha store reload
        ↓
Supervisor git pull сообщает changed=true
        ↓
Store повторно читает metadata
        ↓
version_latest обновляется
```

Не запускайте `ha store repair` как часть обычного обновления.

Repository repair — операция восстановления повреждённого локального репозитория. Во время repair Supervisor заново клонирует репозиторий, но сам repair не обновляет metadata App в Store. Если сразу после `repair` выполнить `reload`, git checkout уже будет на последнем commit; reload может сообщить отсутствие изменений git и не перечитать App metadata. Видимый симптом — устаревший `version_latest`.

## Каноническая процедура обновления

### 1. Обновить Store

Запустить в HAOS:

```bash
APP="8d59ce70_dh_climate_app"

ha store reload

ha apps info "$APP" | grep -E '^state:|^version:|^version_latest:|^update_available:'
```

Ожидаемое состояние до обновления App:

```text
version: <old>
version_latest: <new>
update_available: true
```

### 2. Обновить App

```bash
ha apps update 8d59ce70_dh_climate_app
```

После этого проверить:

```bash
ha apps info 8d59ce70_dh_climate_app \
  | grep -E '^state:|^version:|^version_latest:|^update_available:'
```

Ожидается:

```text
state: started
version: <new>
version_latest: <new>
update_available: false
```

## Если reload не обновил version_latest

Сначала убедитесь, что GitHub `main` действительно содержит ожидаемую версию:

```bash
git ls-remote https://github.com/DigitalHouses/dh_climate_app.git refs/heads/main

curl -fsSL https://raw.githubusercontent.com/DigitalHouses/dh_climate_app/main/dh_climate_app/config.yaml \
  | grep '^version:'
```

Если GitHub всё ещё содержит старую версию — проблема на стороне репозитория/релиза.

Если GitHub уже новый, а Store всё ещё старый — сначала изучить Store logs Supervisor. Не использовать `ha store repair` только ради принудительного refresh.

## Repair — исключительная операция

Использовать:

```bash
ha store repair 8d59ce70
```

только если Supervisor сообщает о повреждении локального custom repository или явно рекомендует reset/repair репозитория.

Поскольку repair заменяет локальный clone, но сам не перечитывает App metadata Store, после намеренного repair может потребоваться restart Supervisor, если в upstream нет более нового commit, который позволил бы последующему `ha store reload` обнаружить git change.

## Дерево решения

```text
новая версия закоммичена + CI green
        |
        v
ha store reload
        |
        +-- Store видит новую версию --> ha apps update
        |
        +-- Store всё ещё старый
                |
                v
        проверить GitHub main из HAOS
                |
                +-- GitHub старый --> проблема repository/release
                |
                +-- GitHub новый --> проверить Store logs Supervisor
                                   |
                                   +-- repository повреждён
                                   |      --> repair
                                   |
                                   +-- repository исправен
                                          --> не делать repair вслепую
```

## Важное правило

`ha store repair` — не команда обновления.

Для обычных обновлений используется `ha store reload`. Repair предназначен только для повреждённого локального репозитория.
