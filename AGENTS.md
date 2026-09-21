# sprite-gen — agent guide

Use this file if you are generating game sprites or if you need to fix the tool.

**One MiniMax-H3 job at a time. Never queue a second generate until the first `sprite-gen generate` has exited.** The GPU on olfa cannot run two clips. Parallel generates will fail or thrash RAM.

## What it is

`sprite-gen` is a Go CLI on Windows that sends a character still to **olfa** (`10.10.10.8`) and unpacks a full animation kit (video + every keyed frame + 8-frame atlas).

Repo: https://github.com/StevenBuglione/sprite-gen  
Windows checkout / fix the CLI here: `D:\Users\steve\sprite-gen`  
Binary on PATH: `D:\.go\bin\sprite-gen.exe` (`go install ./cmd/sprite-gen` from the checkout)

Worker (do not generate on this Windows box): **olfa**, hostname `venus`, `olfa@10.10.10.8`

| Piece | Where | What to fix |
|---|---|---|
| CLI (Go) | `D:\Users\steve\sprite-gen` | flags, HTTP client, zip extract, `cmd/sprite-gen`, `internal/` |
| Worker binary | `/home/olfa/ai/sprite-gen/sprite-gen` | `systemctl --user restart sprite-gen` after `GOOS=linux GOARCH=amd64 go build` and copy |
| Job runner | `/home/olfa/ai/sprite-gen/worker/run_job.py` | staging, Comfy submit, packing, **artifact layout** |
| ComfyUI / H3 | olfa `minimax-h3.service`, code `~/ai/ComfyUI` | model load, OOM, `--highvram` INT8 |
| Sprite H3 pack | `/home/olfa/ai/sprite_h3` | prepare / review / curate / pack |
| Weights | `~/ai/ComfyUI/models/` | DiT, LoRA, CLIP, VAEs |

`10.10.10.12` is a 10 GB RTX 3080. **Do not run MiniMax-H3 there.** Do not run Pixal3D and sprite-gen at the same time (same Comfy port 8188, same RAM).

## Generate (Windows)

```powershell
sprite-gen status
# must print {"ok":true,"service":"sprite-gen"}

sprite-gen generate `
  --image "C:\path\to\character.png" `
  --identity "view-neutral description of the character" `
  --action idle `
  --out .\sprites\hero\idle
```

`--image` and `--identity` are required (unless `--prompt` is a full H3 prompt).

Wait for the command to exit. Then read `.\sprites\hero\idle\manifest.json`.

### One job at a time

- Run **one** `sprite-gen generate` process.
- Do not background a second generate. Do not fire idle and walk together.
- If `sprite-gen status` is fine but a generate is already running, wait.
- After a job finishes you may start the next action (walk, attack, …).

Hot jobs (worker already warmed) are ~2 minutes at default settings. First job after Comfy reboot is slower (model load).

## What you get (`--out`)

Do **not** only use `sheet/sheet.png`. That is an 8-frame 128×128 atlas. Full animation is `frames/all`.

For neural matting on a separate GPU, use `--chroma '#808080'
--matte-profile deferred`. This returns `frames/raw` lossless RGB frames and the
source video, with `matte_status: pending_external_processing`. It deliberately
does not publish `frames/all` or a game-ready sheet. Finish matting before import.
This avoids baking saturated magenta/green spill into generated edges. The
neutral-gray direction was visually better in the demon-character qualification;
the extraction model alone did not fix saturated spill in the old footage.

`neutral-warm` is a legacy opt-in palette suppression experiment. It excludes
intentional blue/green/purple, and the game owner rejected its visual quality.
Do not present its residual-color counter as proof of clean art.

```
manifest.json                 start here
video/{action}.mp4
frames/all/000000.png …       every keyed, aligned frame (USE THIS)
frames/selected/00_….png      the 8 atlas frames
sheet/sheet.png
sheet/sheet.json
sheet/contact-sheet.png
first-frame/staged.png
prompt.txt
```

Godot: `AnimatedSprite2D` from `frames/all` (or SpriteFrames from the atlas if you only need the 8-frame loop). Prefer `frames/all`.

## Flags you actually need

Defaults live in `defaults.toml`. Override with flags.

| Goal | Flags |
|---|---|
| Default (~2 min hot) | none extra (`--recipe quality`: INT8, 4-step turbo, 512², 2s, last-frame lock) |
| Sharper 640 | `--width 640 --height 640` (~3 min hot) |
| Best look, slow | `--recipe max` (BF16, 8-step, ~8 min) — avoid unless asked |
| New action | `--action walk` (or attack, jump, …) plus `--motion "…"` |
| Facing | `--facing down` (default), `right`, `left`, `up`; `side` aliases `right` |
| Stop turning | keep `--loop-last-frame` (default on) |
| Different seed | `--seed 123` |

`--motion` should be one cycle with timestamps, feet planted for idle, return to the start pose. Do not describe camera or background in `--identity`. Background is chroma `#FF00FF`.

`sprite-gen generate --help` is the live flag list.

The worker classifies idle/guard/parry as static, walk/run as locomotion, and other
actions as displacement, so it does not append planted-foot rules to a jump or run.
If a wide weapon or pose does not fit the preview atlas, the job still returns its
video and `frames/all`; the manifest records a warning and null sheet paths. Use
`--cell-width 256 --cell-height 192` for wider preview cells. Never discard the full
frames just because the eight-frame preview sheet could not be packed.

SSH fallback happens only when the worker cannot be reached before submission.
Once a job is submitted, poll/download failures do not launch another generation.
Recover artifacts from an existing run without GPU work on olfa:

```bash
python3 /home/olfa/ai/sprite-gen/worker/recover_artifacts.py JOB_DIR RUN_DIR --out NEW_OUTPUT_DIR
```

## If generate fails

1. `sprite-gen status` — worker down? SSH to olfa:
   - `systemctl --user status sprite-gen`
   - `systemctl --user status minimax-h3`
   - `journalctl --user -u sprite-gen -n 50 --no-pager`
   - `journalctl --user -u minimax-h3 -n 50 --no-pager`
2. Worker HTTP is `http://10.10.10.8:8787`. CLI falls back to `ssh olfa@10.10.10.8` if HTTP fails.
3. OOM / tiny free RAM on olfa: do not use `--recipe max` or `--highvram` with BF16+encoder together. INT8 highvram is the supported path (`/home/olfa/ai/bin/start-minimax-h3`).
4. After editing Go, `go install ./cmd/sprite-gen` on Windows. After editing the worker, copy `run_job.py` to `/home/olfa/ai/sprite-gen/worker/` (no service restart). After editing the Go **server**, cross-compile linux amd64, `systemctl --user stop sprite-gen`, replace `/home/olfa/ai/sprite-gen/sprite-gen`, start it again.

## Fix map

- **CLI bugs, flags, unzip:** Windows `D:\Users\steve\sprite-gen`, then `go install ./cmd/sprite-gen` and push `github.com/StevenBuglione/sprite-gen`.
- **Missing frames in the zip, pack, Comfy graph, matte:** olfa `/home/olfa/ai/sprite-gen/worker/run_job.py` (source of truth also in the repo `worker/run_job.py`).
- **H3 too slow / OOM / Comfy flags:** olfa `~/ai/bin/start-minimax-h3` and `minimax-h3.service`. Keep INT8 + `--highvram`. Do not `--highvram` BF16.
- **Sprite H3 prepare/pack behavior:** `/home/olfa/ai/sprite_h3` (upstream-style install; not this Go repo).

Push fixes to GitHub so Windows and olfa do not drift.
