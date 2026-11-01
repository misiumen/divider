"""One runnable check: Edge of the Earth resolves to the expected dividers and counts.

  python test_counts.py
"""
import arkham_dividers as ad
import divider_cad as cad

core = ad.fetch(f"{ad.DATA_URL}/core.json", "core.json")
d = ad.dividers("eoe", core)
by = {(x["type"], x["code"]): x for x in d}

assert [x["type"] for x in d].count("campaign") == 1
assert by["scenario", "ice_and_death"]["count"] == 21, by["scenario", "ice_and_death"]  # encounterSets.ice_and_death.size
assert by["encounter", "striking_fear"]["count"] == 4, by["encounter", "striking_fear"]  # story override; full set is 7
assert ("encounter", "ice_and_death") not in by  # a scenario's main set is not duplicated as an encounter divider
assert len(d) == 1 + 5 + 19 + 4, len(d)  # campaign + scenarios + encounter sets + extra sets
assert [x["code"] for x in d if x["type"] == "scenario"][:2] == ["ice_and_death", "to_the_forbidden_peaks"]

pl = ad.fetch(f"{ad.DATA_URL}/pl.json", "pl.json")
assert ad.translate(by["scenario", "ice_and_death"], pl) not in (None, "Ice and Death")
assert ad.translate(by["campaign", "eoe"], pl) not in (None, "Edge of the Earth")

tsk = ad.dividers("tsk", core)
assert any(x["code"] == "concealed_cards" and x["count"] == 43 for x in tsk)

# sanitizer: the self-intersecting official campaign icon becomes a valid filled shape
ad.ensure_svg("eoe_campaign", ad.icomoon())
g = cad.svg_geom(ad.ICONS / "eoe_campaign.svg", 10)
assert g.is_valid and g.area > 5, g.area

print("ok:", len(d), "eoe dividers")
