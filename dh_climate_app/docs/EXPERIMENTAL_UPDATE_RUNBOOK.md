# Experimental update runbook

This runbook is the canonical update procedure for the source-build Experimental channel of DigitalHouses Climate App.

Repository:

```text
https://github.com/DigitalHouses/dh_climate_app
```

Store repository slug:

```text
8d59ce70
```

Installed App slug:

```text
8d59ce70_dh_climate_app
```

## Supervisor repository semantics

A normal Store refresh is:

```text
GitHub main advances
        ↓
ha store reload
        ↓
Supervisor git pull reports changed=true
        ↓
Store metadata is re-read
        ↓
version_latest advances
```

Do **not** run `ha store repair` as part of a routine update.

Repository repair is a corruption-recovery operation. Supervisor re-clones the
repository during repair, but repair itself does not refresh Store App metadata.
If `repair` is immediately followed by `reload`, the git checkout is already
at the newest commit; the reload can therefore report no git change and skip
re-reading App metadata. The visible symptom is a stale `version_latest`.

## Canonical update procedure

### 1. Reload Store

Run on HAOS:

```bash
APP="8d59ce70_dh_climate_app"

ha store reload

ha apps info "$APP" | grep -E '^state:|^version:|^version_latest:|^update_available:'
```

Expected before update:

```text
version: <old>
version_latest: <new>
update_available: true
```

### 2. Update App

```bash
ha apps update 8d59ce70_dh_climate_app
```

Then verify:

```bash
ha apps info 8d59ce70_dh_climate_app \
  | grep -E '^state:|^version:|^version_latest:|^update_available:'
```

Expected:

```text
state: started
version: <new>
version_latest: <new>
update_available: false
```

## If reload does not advance version_latest

First verify that GitHub `main` really contains the expected version:

```bash
git ls-remote https://github.com/DigitalHouses/dh_climate_app.git refs/heads/main

curl -fsSL https://raw.githubusercontent.com/DigitalHouses/dh_climate_app/main/dh_climate_app/config.yaml \
  | grep '^version:'
```

If GitHub is still old, this is a repository/release problem.

If GitHub is new but Store is old, inspect Supervisor Store logs before taking a
repair action. Do not use `ha store repair` merely to force a refresh.

## Repair is exceptional

Use:

```bash
ha store repair 8d59ce70
```

only when Supervisor reports that the local custom repository is corrupt or
explicitly recommends repository reset/repair.

Because repair replaces the local clone without itself re-reading Store App
metadata, a Supervisor restart may be required after an intentional repair if
no newer upstream commit exists to make a subsequent `ha store reload` detect
a git change.

## Decision tree

```text
new version committed + CI green
        |
        v
ha store reload
        |
        +-- Store sees new version --> ha apps update
        |
        +-- Store still old
                |
                v
        verify GitHub main from HAOS
                |
                +-- GitHub old --> repository/release problem
                |
                +-- GitHub new --> inspect Supervisor Store logs
                                   |
                                   +-- repository corrupt
                                   |      --> repair
                                   |
                                   +-- repository healthy
                                          --> do not repair blindly
```

## Important rule

`ha store repair` is not an update command.

Routine updates use `ha store reload`. Repair is reserved for a damaged local
repository.
