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

## Known Supervisor behavior

Home Assistant Supervisor can keep an old Store index for a custom Git repository even after:

- the repository default branch already contains the new version;
- `ha store repair` performs a fresh clone;
- `ha store reload` completes successfully.

The observable symptom is:

```text
GitHub main config.yaml = new version
ha apps info version_latest = old version
```

This is a Supervisor Store-state problem, not an App build or GitHub problem.

Do not spend time diagnosing GitHub, DNS, CDN, branch selection or App code once the direct GitHub checks below prove the new version is visible from HAOS.

## Canonical update procedure

### 1. Refresh Store once

Run on HAOS:

```bash
APP="8d59ce70_dh_climate_app"

ha store repair 8d59ce70
ha store reload

ha apps info "$APP" | grep -E '^state:|^version:|^version_latest:|^update_available:'
```

If `version_latest` is the expected new version, update normally.

### 2. If Store still shows the old version, verify GitHub directly

```bash
git ls-remote https://github.com/DigitalHouses/dh_climate_app.git refs/heads/main

curl -fsSL https://raw.githubusercontent.com/DigitalHouses/dh_climate_app/main/dh_climate_app/config.yaml \
  | grep '^version:'
```

If HAOS sees the expected `main` commit and expected `version:`, GitHub is proven healthy.

### 3. Immediately restart Supervisor

Do not continue with Store log analysis first.

Run **only** the restart command:

```bash
ha supervisor restart
```

A Supervisor restart may terminate the VS Code add-on terminal/Ingress session.
This is expected. Do not put post-restart commands in the same shell block.

After Supervisor is back, reopen `HAOS → VS Code → Terminal` and continue:

```bash
APP="8d59ce70_dh_climate_app"

ha store repair 8d59ce70
ha store reload

ha apps info "$APP" | grep -E '^state:|^version:|^version_latest:|^update_available:'
```

Expected result before update:

```text
version: <old>
version_latest: <new>
update_available: true
```

Then run:

```bash
ha apps update 8d59ce70_dh_climate_app
```

## Decision tree

```text
new version committed + CI green
        |
        v
repair + reload once
        |
        +-- Store sees new version --> update App
        |
        +-- Store still old
                |
                v
        direct GitHub check from HAOS
                |
                +-- GitHub also old --> repository/release problem
                |
                +-- GitHub new --> Supervisor Store state stale
                                   |
                                   v
                         restart Supervisor
                         reopen Terminal
                         repair + reload
                         update App
```

## Important rule

For this Experimental source-build workflow, a second round of broad diagnostics is not justified when:

1. GitHub `main` contains the expected version;
2. HAOS can fetch that version directly;
3. Supervisor Store still reports the previous `version_latest`.

That combination is treated as a known stale Supervisor Store state and the standard recovery is a Supervisor restart followed by one repository repair/reload.
