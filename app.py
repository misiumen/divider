"""Web UI for the divider generator (Hugging Face Space or local):  python app.py  ->  http://localhost:7860"""
import pathlib
import shutil
import tempfile

import gradio as gr

import arkham_dividers as ad
import divider_cad as cad

core = ad.fetch(f"{ad.DATA_URL}/core.json", "core.json")
CAMPAIGNS = {f'{s["name"]}  [{s["code"]}]': s["code"] for s in core["stories"] if s.get("is_official")}
DEFAULT = next(k for k, v in CAMPAIGNS.items() if v == "eoe")


def generate(campaign, lang, include_return, pattern, progress=gr.Progress()):
    code = CAMPAIGNS[campaign]
    L = ad.load_layout(ad.ROOT / "layout.toml")
    L["pattern"]["type"] = pattern
    notes = []
    specs = ad.prepare(code, lang, L, include_return, log=notes.append)
    work = pathlib.Path(tempfile.mkdtemp(prefix="dividers_"))
    out = work / f"{code}_{lang}"
    out.mkdir()
    for d in progress.tqdm(specs, desc="rendering"):
        cad.export(cad.build(d, L, ad.ICONS), out / d["file"])
    ad.write_manifest(specs, out / "manifest.csv")
    zip_path = shutil.make_archive(str(work / f"arkham_dividers_{code}_{lang}"), "zip", out)
    table = [[d["index"], d["type"], d["title"], d["count"], d["slot"], "" if d["translated"] else f"no {lang} name"] for d in specs]
    return zip_path, table, "\n".join(notes) or f"{len(specs)} dividers rendered"


with gr.Blocks(title="Arkham Horror LCG dividers") as demo:
    gr.Markdown(
        "# Arkham Horror LCG 3D-printable dividers\n"
        "Pick a campaign and a language, get a zip of STLs: one divider per scenario and "
        "encounter set, with official names, card counts and encounter icons in relief. "
        "Print flat, filament swap at Z = 1.2 mm for two colours."
    )
    with gr.Row():
        campaign = gr.Dropdown(list(CAMPAIGNS), value=DEFAULT, label="Campaign")
        lang = gr.Dropdown(core["languages"], value="pl", label="Language")
    with gr.Row():
        include_return = gr.Checkbox(False, label="Include Return to… sets and scenarios")
        pattern = gr.Radio(["hex", "grid", "solid"], value="hex", label="Body pattern")
    button = gr.Button("Generate STLs", variant="primary")
    zip_out = gr.File(label="Download")
    table = gr.Dataframe(headers=["#", "type", "title", "cards", "tab slot", "note"], label="Dividers")
    notes = gr.Textbox(label="Notes", lines=2)
    button.click(generate, [campaign, lang, include_return, pattern], [zip_out, table, notes])

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1)  # ponytail: one render at a time, OCC is not thread-safe
    demo.launch(server_name="0.0.0.0", server_port=7860)
