# DigitalHouses Climate App repository

This repository publishes the **DigitalHouses Climate App** for Home Assistant.

The Home Assistant App lives in:

```text
dh_climate_app/
```

- [App overview](dh_climate_app/README.md)
- [User documentation](dh_climate_app/DOCS.md)
- [Architecture](dh_climate_app/docs/ARCHITECTURE.md)
- [HAOS acceptance plan](dh_climate_app/HAOS_TEST_PLAN.md)

Repository URL for the Home Assistant App store:

```text
https://github.com/DigitalHouses/dh_climate_app
```


## Updating the Experimental App

The repository is a standard Home Assistant custom App repository. After a new
version is committed to `main`, refresh Store metadata with:

```bash
ha store reload
```

Do not use `ha store repair` for routine updates. Repair is reserved for a
corrupt local Supervisor repository clone.
