# sprite-gen

The worker invokes sprite-h3 through `worker/cached_sprite_h3.py`. Staged input
images use SHA256-based upload names so identical references can reuse ComfyUI's
conditioning cache when only the seed changes. This is scoped to the worker's
process and does not modify the upstream sprite-h3 installation. Deploy the
adapter alongside `run_job.py`; different image bytes always get a new name.

For a separate neural matting worker, `--chroma '#808080' --matte-profile deferred`
returns the original lossless `frames/raw` and video. The manifest explicitly
marks transparency as pending and omits game-ready frames/sheets. This supports
video generation and matting on different GPUs without lossy MP4 round trips.

Go CLI that sends a character still to **olfa** (`10.10.10.8`) and returns a MiniMax-H3 video plus a packed sprite sheet.

Default recipe is **quality**: INT8 FL2VA, 4-step turbo LoRA, 512×512, requested 2 s, last frame locked to the first, no audio. Use the live flags or defaults.toml for settings; actual video frame count is reported in manifest.json.

Agents (Codex, etc.): read [`AGENTS.md`](AGENTS.md) first. Short skill: [`SKILL.md`](SKILL.md). Numbers: [`defaults.toml`](defaults.toml). **One generate at a time.**

## Install (Windows)

```powershell
git clone https://github.com/StevenBuglione/sprite-gen.git
cd sprite-gen
go build -o sprite-gen.exe ./cmd/sprite-gen
```

## Generate

```powershell
.\sprite-gen.exe generate --image "D:\art\hero.png" --identity "an oni swordsman in a white horned mask..." --action idle --out .\out
```

The CLI posts to `http://10.10.10.8:8787`. If that is down it falls back to `ssh olfa@10.10.10.8`.

## Worker (olfa)

```bash
# on olfa, after ComfyUI + MiniMax-H3 weights exist
sudo -u olfa bash -lc 'install -d ~/ai/sprite-gen'
# copy this repo to ~/ai/sprite-gen, then:
go build -o /home/olfa/ai/sprite-gen/sprite-gen ./cmd/sprite-gen
cp worker/sprite-gen.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now sprite-gen
# ComfyUI must be listening on 127.0.0.1:8188
```

One H3 job at a time. Do not run Pixal3D and sprite-gen together.

## Recipes

| `--recipe` | Use |
|---|---|
| `quality` | INT8 + 4-step turbo; current default. |
| `fast` | INT8 + 4-step turbo; currently the same settings. |
| `max` | BF16 + 8-step turbo; slower and more memory intensive. |

Every default is a flag. `sprite-gen generate --help` lists them.

Use `frames/all` at the manifest's fps for smooth animation. The small atlas is an
optional preview; a packing failure preserves full frames and video, with a warning
in the manifest. Facing accepts `left` and `right`; the older `side` flag aliases right.
Submitted jobs are never automatically regenerated through SSH after a job or download failure.

For authored intermediate poses, `--guides guides.json` accepts a JSON list such
as `[{"frame":9,"image":"passing.png"}]`. Guide images are opaque RGB PNGs at the
exact video canvas size; paths are relative to the JSON file. Register the body
and floor consistently before submitting. Frame zero and a locked final frame
remain owned by the primary reference. The CLI rejects duplicate/out-of-range
frames, mismatched canvases, more than eight guides, or PNGs over 6 MiB each.

Guides travel with the job as image bytes and become native `MiniMaxH3AddGuide`
conditioning nodes. The kit retains guide hashes, staged guide PNGs and the exact
submitted `workflow.api.json`. They constrain poses; they do not guarantee a
correct gait, seamless loop, clean alpha, or a particular generation latency.
Deploy `worker/pose_guides.py` alongside the worker and cached adapter.
