# Shared settings

Put here the settings every pipeline script reads, so a change is made in one place only, for example:

- `datasets.yaml` – dataset names, provider, variables, years, scenarios, licence
- `area.yaml` – bounding box and spatial unit (municipalities)
- `periods.yaml` – the 10-year periods and the baseline

Never put passwords or API keys here: keep them in your home folder on OLGYAY (`~/.cdsapirc`, `~/.ddsapirc`).
