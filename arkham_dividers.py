"""Arkham Horror LCG 3D-printable divider generator.

  python arkham_dividers.py --campaigns                        list campaign codes
  python arkham_dividers.py --campaign eoe --lang pl --list    print the divider table only
  python arkham_dividers.py --campaign eoe --lang pl           render STLs to out/eoe_pl/

Data: ArkhamDividerData core.json + <lang>.json (ArkhamDB and arkham-cards already merged
upstream; names are the official localized ones, nothing is translated here).
Icons: ArkhamCards icomoon project -> icons/<name>.svg, written once; edit or replace a
file to override an icon. Divider resolution is a port of ArkhamDivider's
generateCampaignDividers (campaign, scenarios, encounter sets, extra sets).
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
import time
import tomllib
import urllib.request

import divider_cad as cad

ROOT = pathlib.Path(sys.executable).parent if getattr(sys, "frozen", False) else pathlib.Path(__file__).resolve().parent
DATA, ICONS, OUT = ROOT / "data", ROOT / "icons", ROOT / "out"
DATA_URL = "https://neizerth.github.io/ArkhamDividerData"
ICOMOON_URL = "https://raw.githubusercontent.com/zzorba/ArkhamCards/master/assets/icomoon/project.json"


def fetch(url, name):
    """Download once into data/, return parsed JSON."""
    path = DATA / name
    if not path.exists():
        DATA.mkdir(exist_ok=True)
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, path)
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ data (port of ArkhamDivider)


def _apply(es, data):
    """Story/scenario encounter_set_data overrides a partially gathered set's size and types."""
    d = next((d for d in data or [] if d["code"] == es["code"]), None)
    return es if not d else {**es, "size": d["size"], **({"types": d["types"]} if d.get("types") else {})}


def _sets(codes, sets, data):
    return [_apply(sets[c], data) for c in codes or [] if c in sets]


def _uniq(sets):
    seen = {}
    for s in sets:
        if s:
            seen.setdefault(s["code"], s)
    return list(seen.values())


def _cards(es):
    return sum(t["size"] for t in es.get("types") or [] if t["size"] > 0)


def relate(story, core, with_return=True):
    """mapStoryWithRelations: attach encounter set objects to a story and its scenarios."""
    sets = {s["code"]: s for s in core["encounterSets"]}
    by_icon = {}
    for s in core["encounterSets"]:
        by_icon.setdefault(s.get("icon"), s)
    data = story.get("encounter_set_data")

    def scenario(sc):
        d = sc.get("encounter_set_data")
        main = by_icon.get(sc.get("icon"))  # a scenario's main set is the one sharing its icon
        return {
            **sc,
            "encounterSets": _sets(sc.get("encounter_sets"), sets, d),
            "extraEncounterSets": _sets(sc.get("extra_encounter_sets"), sets, d),
            "encounterSet": _apply(main, d) if main else None,
        }

    out = {
        **story,
        "encounterSets": _sets(story.get("encounter_sets"), sets, data),
        "scenarioEncounterSets": _sets(story.get("scenario_encounter_sets"), sets, data),
        "extraEncounterSets": _sets(story.get("extra_encounter_sets"), sets, data),
        "scenarios": [scenario(sc) for sc in story.get("scenarios") or []],
        "returnStory": None,
    }
    if with_return and story.get("return_to_code"):
        rs = next((s for s in core["stories"] if s["code"] == story["return_to_code"]), None)
        if rs:
            out["returnStory"] = relate(rs, core, with_return=False)
    return out


def campaign_count(story):
    """getCampaignCards: sum of type sizes over the unique sets of the whole campaign."""
    sets = _uniq(
        story["encounterSets"]
        + story["scenarioEncounterSets"]
        + [s for sc in story["scenarios"] for s in [sc["encounterSet"], *sc["encounterSets"]]]
    )
    return sum(_cards(s) for s in sets)


def dividers(code, core, include_return=False, include_extra=True):
    """Divider specs for a campaign: campaign, scenarios (by number), encounter sets, extra sets."""
    story = next((s for s in core["stories"] if s["code"] == code), None)
    if not story:
        raise SystemExit(f"unknown campaign code {code!r} (see --campaigns)")
    st = relate(story, core)
    ret = st["returnStory"] if include_return else None
    stories = [s for s in (st, ret) if s]
    out = [{"type": "campaign", "code": s["code"], "title": s["name"], "icon": s.get("icon"), "count": campaign_count(s)} for s in stories]

    scenarios = [sc for s in stories for sc in s["scenarios"]]
    for sc in sorted(scenarios, key=lambda s: (s.get("number") is None, s.get("number") or 0)):
        main = sc["encounterSet"]
        out.append({"type": "scenario", "code": sc["id"], "title": sc["scenario_name"], "icon": sc.get("icon"), "count": _cards(main) if main else 0})

    main_codes = {sc["encounterSet"]["code"] for sc in scenarios if sc["encounterSet"]}
    base = _uniq([e for s in stories for e in s["encounterSets"]])
    extra = _uniq([e for s in stories for e in s["extraEncounterSets"]]) if include_extra else []
    extra_codes = {e["code"] for e in extra}
    for es in _uniq(base + extra):
        if es["code"] in main_codes:  # already represented by its scenario divider
            continue
        out.append({"type": "encounter", "code": es["code"], "title": es["name"], "icon": es.get("icon"), "count": _cards(es), "extra": es["code"] in extra_codes})
    if code == "tsk":  # ArkhamDivider special divider
        out.append({"type": "encounter", "code": "concealed_cards", "title": "Concealed Cards", "icon": "special_cards", "count": 43})
    return out


def translate(d, lang):
    """Official localized name from <lang>.json, keyed by the English name. None if absent."""
    keys = {"campaign": ("campaigns", "stories"), "scenario": ("scenarios",), "encounter": ("encounterSets",)}[d["type"]]
    for k in keys:
        table = lang.get(k) or {}
        v = table.get(d["title"]) or next((v for key, v in table.items() if key.lower() == d["title"].lower()), None)
        if v:
            return v
    return None


# ------------------------------------------------------------------ icons


def icomoon():
    """icon name -> (svg path list, width, height) from the ArkhamCards icomoon project."""
    proj = fetch(ICOMOON_URL, "icomoon_project.json")
    out = {}
    for s in proj["iconSets"]:
        names = {i["id"]: i["name"] for i in s.get("selection", [])}
        for ic in s["icons"]:
            name = names.get(ic["id"]) or (ic.get("tags") or [None])[0]  # same rule as ArkhamDividerData
            if name and name not in out:
                out[name] = (ic["paths"], ic.get("width") or s.get("height", 1024), s.get("height", 1024))
    return out


def ensure_svg(name, vec):
    """Write icons/<name>.svg once; an existing file (your override) is left alone."""
    path = ICONS / f"{name}.svg"
    if path.exists():
        return path
    if name not in vec:
        return None
    paths, w, h = vec[name]
    ICONS.mkdir(exist_ok=True)
    body = "".join(f'<path d="{d}"/>' for d in paths)
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>', encoding="utf-8")
    return path


# ------------------------------------------------------------------ cli


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", help="story code, e.g. eoe, core, rtnotz")
    ap.add_argument("--lang", default="pl", help="pl, en, de, ru ... (en = names as in core.json)")
    ap.add_argument("--layout", default=ROOT / "layout.toml", type=pathlib.Path)
    ap.add_argument("--include-return", action="store_true", help="also the Return to ... sets and scenarios")
    ap.add_argument("--no-extra", action="store_true", help="skip extra (core box) encounter sets")
    ap.add_argument("--list", action="store_true", help="print the divider table, render nothing")
    ap.add_argument("--only", type=int, nargs="*", help="render only these divider numbers")
    ap.add_argument("--campaigns", action="store_true", help="list official campaign codes and exit")
    a = ap.parse_args(argv)

    core = fetch(f"{DATA_URL}/core.json", "core.json")
    if a.campaigns:
        for s in core["stories"]:
            if s.get("is_official"):
                print(f'{s["code"]:10} {s["type"]:10} {s["name"]}')
        return
    if not a.campaign:
        ap.error("--campaign is required")
    lang = {} if a.lang == "en" else fetch(f"{DATA_URL}/{a.lang}.json", f"{a.lang}.json")
    L = tomllib.loads(a.layout.read_text(encoding="utf-8"))
    for key in ("title", "count"):  # relative font paths live next to the script / exe
        p = pathlib.Path(L[key]["font"])
        L[key]["font"] = str(p if p.is_absolute() else ROOT / p)

    specs = dividers(a.campaign, core, a.include_return, not a.no_extra)
    vec = None
    for i, d in enumerate(specs, 1):
        d["index"], d["slot"] = i, (i - 1) % L["tab"]["slots"]
        d["title_en"] = d["title"]
        local = translate(d, lang) if lang else None
        d["title"], d["translated"] = local or d["title_en"], bool(local) or not lang
        if d["icon"] and not (ICONS / f"{d['icon']}.svg").exists():
            vec = vec if vec is not None else icomoon()
            if not ensure_svg(d["icon"], vec):
                print(f"warning: no vector for icon {d['icon']!r}, divider {i} gets none")
                d["icon"] = None
        d["file"] = f"{i:02d}_{d['type']}_{slug(d['title_en'])}.stl"

    width = max(len(d["title"]) for d in specs)
    for d in specs:
        note = "" if d["translated"] else f"(no {a.lang} name)"
        print(f'{d["index"]:3} {d["type"]:9} slot {d["slot"]} {d["count"]:4}  {d["title"]:<{width}}  {d["icon"] or "(no icon)":28} {note}')
    if a.list:
        return

    out = OUT / f"{a.campaign}_{a.lang}"
    out.mkdir(parents=True, exist_ok=True)
    fields = ["index", "type", "code", "title", "title_en", "count", "icon", "slot", "translated", "file"]
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(specs)
    for d in specs:
        if a.only and d["index"] not in a.only:
            continue
        t = time.time()
        cad.export(cad.build(d, L, ICONS), out / d["file"])
        print(f'{d["file"]}  {time.time() - t:.1f}s')
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
