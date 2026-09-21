#!/usr/bin/env python3
"""Run one sprite-gen job on olfa: stage, MiniMax-H3 I2V, pack Godot sheet."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SPRITE_H3 = Path(os.environ.get("SPRITE_GEN_SPRITE_H3", "/home/olfa/ai/sprite_h3"))
COMFY = os.environ.get("SPRITE_GEN_COMFY", "http://127.0.0.1:8188")
WORKFLOW = SPRITE_H3 / "workflows/minimax_h3/i2v/workflow.api.json"
CONFIG = SPRITE_H3 / "config.local.toml"
PY = SPRITE_H3 / ".venv/bin/python"
CLI = SPRITE_H3 / ".venv/bin/sprite-h3"


def action_motion_class(action: str) -> str:
    """Do not append planted-feet instructions to a running or jumping prompt."""
    action = action.strip().lower().replace("-", "_")
    if action in {"idle", "guard", "block", "parry", "perfect_parry", "breathe"}:
        return "static"
    if action in {"walk", "run", "sprint", "jog", "sneak", "crawl", "swim"}:
        return "locomotion"
    return "displacement"


def load_spec(job: Path) -> dict:
    spec = json.loads((job / "spec.json").read_text())
    spec.setdefault("action", "idle")
    spec.setdefault("facing", "down")
    spec.setdefault("name", "sprite")
    spec.setdefault("width", 640)
    spec.setdefault("height", 640)
    spec.setdefault("seconds", 3.0)
    spec.setdefault("fps", 24)
    spec.setdefault("steps", 8)
    spec.setdefault("seed", 424242)
    spec.setdefault("chroma", "#FF00FF")
    spec.setdefault("matte_profile", "chroma")
    if spec["matte_profile"] not in {"chroma", "neutral-warm", "deferred"}:
        raise ValueError("matte_profile must be chroma, neutral-warm or deferred")
    spec.setdefault("loop_last_frame", True)
    spec.setdefault("audio", False)
    spec.setdefault("base_frames", 8)
    spec.setdefault("cell_width", 128)
    spec.setdefault("cell_height", 128)
    spec.setdefault("frame_ms", 100)
    spec.setdefault("figure_height_ratio", 0.7)
    spec.setdefault("baseline_ratio", 0.856)
    spec.setdefault("style", "painterly 2D-animated game-sprite")
    # Preserve the legacy CLI's advertised side-facing alias.
    if spec["facing"] == "side":
        spec["facing"] = "right"
    if spec["facing"] not in {"down", "up", "left", "right", "_"}:
        raise ValueError(f"Unsupported facing: {spec['facing']!r}")
    return spec


def wait_comfy(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=3).read()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2)
    raise SystemExit(f"ComfyUI not up at {COMFY}: {last}")


def patch_workflow(spec: dict) -> None:
    data = json.loads(WORKFLOW.read_text())
    if "105:6" in data:
        data["105:6"]["inputs"]["unet_name"] = spec.get(
            "unet", "minimax_h3_fl2va_bf16.safetensors"
        )
    if "105:lora" in data:
        lora = spec.get("lora") or ""
        data["105:lora"]["inputs"]["lora_name"] = lora or data["105:lora"]["inputs"].get(
            "lora_name", ""
        )
        data["105:lora"]["inputs"]["strength_model"] = 0.0 if not lora else 1.0
    if "105:13" in data:
        data["105:13"]["inputs"]["clip_name"] = spec.get(
            "clip", "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
        )
        data["105:13"]["inputs"]["device"] = "default"
    if "105:9" in data:
        data["105:9"]["inputs"]["steps"] = int(spec.get("steps", 8))
        data["105:9"]["inputs"]["scheduler"] = spec.get("scheduler", "simple")
        if spec.get("lora"):
            data["105:9"]["inputs"]["model"] = ["105:lora", 0]
    if "105:17" in data:
        data["105:17"]["inputs"]["sampler_name"] = spec.get("sampler", "euler")
    if "105:16" in data and spec.get("lora"):
        data["105:16"]["inputs"]["model"] = ["105:lora", 0]
    if "105:104" in data:
        data["105:104"]["inputs"]["width"] = int(spec["width"])
        data["105:104"]["inputs"]["height"] = int(spec["height"])
    if not spec.get("audio"):
        data.pop("105:23", None)
        data.pop("105:24", None)
        if "105:91" in data:
            data["105:91"]["inputs"].pop("audio", None)
    WORKFLOW.write_text(json.dumps(data, indent=2) + "\n")


def write_workspace(job: Path, spec: dict) -> Path:
    ws = job / "workspace"
    tmpl = ws / "templates" / "job"
    proj = ws / "projects" / "job" / spec["name"]
    (tmpl / "motions").mkdir(parents=True, exist_ok=True)
    (proj / "sources").mkdir(parents=True, exist_ok=True)
    (ws / "workspace.toml").write_text('name = "sprite-gen"\n')
    motion = spec.get("motion") or (
        "The character performs one subtle idle cycle. Gentle breathing begins "
        "during the opening second, cloth shifts by 1.50 seconds, and by 2.50 "
        "seconds the character returns to the exact initial posture with both "
        "feet fixed, then holds that pose through the end."
    )
    (tmpl / "motions" / f"{spec['action']}.txt").write_text(motion + "\n")
    loop = "true" if spec.get("loop_last_frame", True) else "false"
    style = spec.get("style") or "painterly 2D-animated game-sprite"
    # Honor the CLI's full-prompt flag instead of silently rebuilding its prose.
    prompt = spec.get("prompt")
    prompt_override = f"prompt_override = {json.dumps(prompt, ensure_ascii=False)}\n" if prompt else ""
    (tmpl / "template.toml").write_text(
        f"""name = "job"
group = "characters"
kind = "figure"

[prompt]
composer = "sprite-i2va"
style = {style!r}

[consistency]
figure_height = "exact"
frame_counts = "exact"

[canvas]
width = {int(spec["width"])}
height = {int(spec["height"])}
background = {spec.get("chroma", "#FF00FF")!r}
figure_height_ratio = {spec.get("figure_height_ratio", 0.7)}
baseline_ratio = {spec.get("baseline_ratio", 0.856)}

[video]
requested_seconds = {spec.get("seconds", 3.0)}
fps = {int(spec.get("fps", 24))}
seed = {int(spec.get("seed", 424242))}
cfg_scale = {spec.get("cfg", 1.0)}

[processing]
remove_background = true
background_tolerance = 48
background_soft_tolerance = 80
background_minimum_alpha = 48
anchor = "bottom-center"
trim_transparent = true

[frames]
base_count = {int(spec.get("base_frames", 8))}
drop_first = 0
drop_last = 0

[sheet]
layout = "grid"
cell_width = {int(spec.get("cell_width", 128))}
cell_height = {int(spec.get("cell_height", 128))}
padding = 0
frame_duration_ms = {int(spec.get("frame_ms", 100))}
resample = "lanczos"
bounce = false
figure_height_px = 96

[[actions]]
name = {spec["action"]!r}
enabled = true
motion_file = "motions/{spec["action"]}.txt"
motion_class = {action_motion_class(spec['action'])!r}
closed = {loop}
loop_anchor = "first-last"
{prompt_override}
"""
    )
    identity = spec.get("identity") or "the character in Picture 1"
    (proj / "project.toml").write_text(
        f"""name = {spec["name"]!r}
template = "job"

[source]
{spec["facing"]} = "sources/{spec["facing"]}.png"

[character]
identity = {identity!r}
"""
    )
    src = job / "source.png"
    dest = proj / "sources" / f"{spec['facing']}.png"
    shutil.copyfile(src, dest)
    return proj / "project.toml"


def sh3(*args: str) -> None:
    cmd = [str(CLI), *args]
    if args and args[0] == "run" and CONFIG.exists():
        cmd.extend(["--config", str(CONFIG)])
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(SPRITE_H3))


def newest_run() -> Path:
    runs = Path("/home/olfa/ai/sprite-pipeline/workspace/runs")
    if not runs.exists():
        runs = SPRITE_H3 / "runs"
    # Repairs change old run mtimes; timestamped names preserve creation order.
    cands = sorted((p for p in runs.glob("*") if p.is_dir()), key=lambda p: p.name, reverse=True)
    if not cands:
        raise SystemExit("no sprite-h3 run directory")
    return cands[0]


def main() -> int:
    job = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    spec = load_spec(job)
    subprocess.call(["systemctl", "--user", "start", "minimax-h3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_comfy()
    patch_workflow(spec)
    project = write_workspace(job, spec)
    sh3("run", str(project), "--action", spec["action"], "--facing", spec["facing"])
    run = newest_run()
    cell = run / "actions" / spec["action"] / spec["facing"]
    if spec["matte_profile"] == "deferred":
        collect_artifacts(job / "out", spec, run, cell)
        print("wrote raw video kit; neural matting pending", job / "out", flush=True)
        return 0
    subprocess.run([str(PY), str(Path(__file__).with_name("clean_matte.py")), "reprocess", str(run), "--profile", spec["matte_profile"], "--key", spec["chroma"]], check=True)
    sh3("review", str(run), "--action", spec["action"], "--facing", spec["facing"])
    sh3(
        "curate",
        str(run),
        "--action",
        spec["action"],
        "--facing",
        spec["facing"],
        "--accept-suggestions",
    )
    pack_warning = None
    try:
        sh3("pack", str(run), "--action", spec["action"], "--facing", spec["facing"])
    except subprocess.CalledProcessError as exc:
        # Full-size frames are the primary artifact. A too-small preview cell must
        # not discard a successfully generated video or cause an expensive retry.
        pack_warning = f"Preview atlas could not be packed (exit {exc.returncode}); use frames/all or repack with a larger cell."
        print(pack_warning, flush=True)
    collect_artifacts(job / "out", spec, run, cell, pack_warning=pack_warning)
    print("wrote", job / "out")
    return 0


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def collect_artifacts(out: Path, spec: dict, run: Path, cell: Path, *, pack_warning: str | None = None) -> None:
    """Ship everything an agent needs to build Godot/Unity animations."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    action = spec["action"]
    facing = spec["facing"]
    mp4 = cell / "raw" / "output.mp4"
    if mp4.exists():
        _copy(mp4, out / "video" / f"{action}.mp4")

    staged = cell / "input" / "staged.png"
    if staged.exists():
        _copy(staged, out / "first-frame" / "staged.png")
    prompt = cell / "resolved-prompt.txt"
    if prompt.exists():
        _copy(prompt, out / "prompt.txt")
    motion = cell / "resolved-motion.txt"
    if motion.exists():
        _copy(motion, out / "motion.txt")

    raw_frames = sorted((cell / "raw" / "frames").glob("*.png"))
    for png in raw_frames:
        _copy(png, out / "frames" / "raw" / png.name)
    if spec.get("matte_profile") == "deferred":
        if not mp4.exists() or not raw_frames:
            raise RuntimeError("Generation did not produce both a video and lossless raw frames")
        manifest = {
            "action": action, "facing": facing, "video": f"video/{action}.mp4",
            "raw_frames_dir": "frames/raw", "raw_frame_count": len(raw_frames),
            "all_frames_dir": None, "all_frame_count": 0,
            "matte_status": "pending_external_processing", "sheet": None,
            "sheet_json": None, "contact_sheet": None,
            "fps": spec.get("fps", 24), "run": str(run), "spec": spec,
            "warnings": ["Raw RGB source only. Run neural matting before game import."],
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (out / "run.json").write_text(json.dumps({"run": str(run), "spec": spec}, indent=2))
        return

    rgba_dir = None
    proc_revs = sorted((cell / "processing").glob("*/frames/rgba"))
    if proc_revs:
        rgba_dir = proc_revs[-1]
        for png in sorted(rgba_dir.glob("*.png")):
            _copy(png, out / "frames" / "all" / png.name)

    selected = []
    for pack in sorted((cell / "repack").glob("*")):
        if not (pack / "sheet.png").exists():
            continue
        _copy(pack / "sheet.png", out / "sheet" / "sheet.png")
        if (pack / "contact-sheet.png").exists():
            _copy(pack / "contact-sheet.png", out / "sheet" / "contact-sheet.png")
        if (pack / "sheet.json").exists():
            _copy(pack / "sheet.json", out / "sheet" / "sheet.json")
        meta = json.loads((pack / "sheet.json").read_text()) if (pack / "sheet.json").exists() else {}
        for i, rel in enumerate(meta.get("repack", {}).get("selected_frames") or []):
            src = run / rel
            if src.exists():
                name = f"{i:02d}_{src.name}"
                _copy(src, out / "frames" / "selected" / name)
                selected.append(f"frames/selected/{name}")

    all_frame_count = len(list((out / "frames" / "all").glob("*.png")))
    if not mp4.exists() or all_frame_count == 0:
        raise RuntimeError("Generation did not produce both a video and full RGBA frames")
    manifest = {
        "action": action,
        "facing": facing,
        "video": f"video/{action}.mp4" if mp4.exists() else None,
        "sheet": "sheet/sheet.png" if (out / "sheet/sheet.png").exists() else None,
        "sheet_json": "sheet/sheet.json" if (out / "sheet/sheet.json").exists() else None,
        "contact_sheet": "sheet/contact-sheet.png" if (out / "sheet/contact-sheet.png").exists() else None,
        "all_frames_dir": "frames/all",
        "all_frame_count": all_frame_count,
        "raw_frames_dir": "frames/raw" if raw_frames else None,
        "raw_frame_count": len(raw_frames),
        "warnings": [pack_warning] if pack_warning else [],
        "selected_frames": selected,
        "selected_count": len(selected),
        "fps": spec.get("fps", 24),
        "frame_ms": spec.get("frame_ms", 100),
        "cell": {"width": spec.get("cell_width", 128), "height": spec.get("cell_height", 128)},
        "note": "frames/all is every keyed+aligned frame at generation resolution. frames/selected is the 8-frame loop used in sheet.png. Import frames/all for full animation control.",
        "run": str(run),
        "spec": spec,
    }
    qa_path = run / "matte-quality.json"
    if qa_path.exists():
        _copy(qa_path,out / "matte-quality.json")
        manifest["matte_quality"] = json.loads(qa_path.read_text())
        if not manifest["matte_quality"].get("usable",False):
            manifest["warnings"].append("Rejected background quality; inspect retained raw video before importing.")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "run.json").write_text(json.dumps({"run": str(run), "spec": spec}, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
