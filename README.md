---
title: Arkham Horror LCG Dividers
emoji: 🃏
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Arkham Horror LCG divider generator

Generates 3D-printable (STL) dividers for Arkham Horror: The Card Game campaigns:
one campaign divider, one per scenario, one per encounter set, with the official
localized names, exact card counts and the official encounter icons in relief.

Data comes from [ArkhamDividerData](https://github.com/neizerth/ArkhamDividerData)
(ArkhamDB and arkham-cards merged) and the icon vectors from
[ArkhamCards](https://github.com/zzorba/ArkhamCards). Divider resolution is a port of
[ArkhamDivider](https://github.com/neizerth/ArkhamDivider).

## Generate online (GitHub, no install)

Actions tab → **generate dividers** → **Run workflow**. Pick the campaign, language, pattern
and whether to include the Return to... sets, click Run. About two minutes later the run
shows an **Artifacts** box with a zip of the STLs and the manifest. Anyone with access to
this repository can do this.

## Use the app (Windows, no Python needed)

Download `ArkhamDividers-windows.zip` from Releases, unzip, double-click `ArkhamDividers.exe`.
Pick the campaign and language, move the sliders (plate and tab size, stagger slots, pattern,
text and icon size) while the top-view preview updates, click **Generuj STL**. The output
folder opens when done; your slider values are kept in `settings.json` for next time.

The folder works offline for every official campaign in Polish and English. Other
languages and icons for custom content are downloaded on first use.

Command line (`python arkham_dividers.py` from source):

```
python arkham_dividers.py --campaigns                       list campaign codes
python arkham_dividers.py --campaign eoe --lang pl --list   show the dividers and card counts
python arkham_dividers.py --campaign eoe --lang pl          write STLs to out\eoe_pl\
```

Options: `--lang en` (names as in the database), `--include-return` (adds the Return to...
sets), `--no-extra` (skips the core-box sets), `--only 3 7` (render some dividers only),
`--pattern grid`, `--layout other.toml`.

## Customise

Edit `layout.toml` next to the exe. Every length is in mm:

| Section | What it controls |
|---|---|
| `plate` | body size, base thickness (colour swap height), corner radius, edge fillet and chamfer |
| `tab` | tab size, number of stagger slots, side margin (must exceed 2 x corner radius) |
| `relief` | height of text and icons above the base |
| `pattern` | `solid`, `hex` or `grid`, cell size, wall, border, keep-out around the relief |
| `title`, `count`, `icon` | font, size, x/y relative to the body or tab centre, wrapping, embolden, minimum feature |

Icons are plain SVG files in `icons/`. Replace one to override it.

## Print

Flat on the bed, no supports, PLA, 0.2 mm layers. Add a filament change at the first
layer above the base thickness (Z = 1.2 mm with the default 1.0 mm base) for two-colour text.

## Build from source

```
pip install -r requirements.txt
python arkham_dividers.py --campaign eoe --lang pl
python test_counts.py
pwsh build.ps1                                      one-folder exe in dist\ArkhamDividers
```

Pushing a tag `v*` builds the zip on GitHub Actions and attaches it to a Release.

Fonts: `fonts/ArnoPro-Bold.ttf` is a licensed Adobe font; this repository is private for that reason.
