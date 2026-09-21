---
name: sprite-gen
description: >
  Generate game sprite sheets from a character still via MiniMax-H3 on olfa
  (10.10.10.8). Use when the user wants idle/walk/attack sheets, Godot atlases,
  or to remote-generate sprites. Defaults are the quality recipe (BF16, 8-step
  turbo, 640², 3s, last-frame lock). Override with flags; do not invent host
  paths. Run `sprite-gen generate --help` for the live flag list.
---

# sprite-gen

Windows (or any) CLI. Worker lives on `olfa@10.10.10.8`. One job returns an mp4, a packed PNG sheet, `sheet.json`, and a contact strip.

Defaults are in `defaults.toml` in this repo (copied to `~/.sprite-gen/defaults.toml` if present). Do not duplicate numbers here — change that file or pass flags.

## When to use

- User wants a sprite sheet / atlas / character animation from a still.
- User says generate sprites, idle cycle, Godot sheet, or MiniMax-H3 I2V for a character.

## Commands

```bash
sprite-gen generate --image PATH --action idle --identity "DESCRIPTION"
sprite-gen generate --image PATH --recipe fast
sprite-gen generate --image PATH --width 640 --steps 8 --unet bf16
sprite-gen status --url http://10.10.10.8:8787
sprite-gen serve --listen 0.0.0.0:8787    # on olfa only
```

`--image` is required for `generate`. `--identity` is required unless `--prompt` is a full MiniMax-H3 prompt.

## Recipes

| `--recipe` | When |
|---|---|
| `quality` (default) | INT8 DiT kept in RAM, 4-step turbo, 512², 2s, last-frame lock. Measured ~124 s hot. |
| `fast` | Same but 512². |
| `max` | BF16, 8-step turbo, 3s. Best look, ~8 min. |

Flags after `--recipe` override the recipe.

## Flags agents should actually use

Identity and motion (do not stuff camera or background into identity):

- `--identity` view-neutral character description
- `--style` art style
- `--motion` one-cycle action text with timestamps
- `--prompt` full prompt; skips composer
- `--action` idle, walk, attack, or any name
- `--facing` down, side, up, or `_`

Quality / time:

- `--recipe quality|fast`
- `--unet` filename or `bf16` / `int8`
- `--lora` filename or `8step` / `4step` / `none`
- `--steps` `--width` `--height` `--seconds`
- `--loop-last-frame` / `--no-loop-last-frame`
- `--audio` / `--no-audio`
- `--seed`

Sheet:

- `--cell-width` `--cell-height` `--base-frames` `--frame-ms`
- `--chroma` default `#FF00FF`

Remote:

- `--url` default `http://10.10.10.8:8787`
- `--ssh` default `olfa@10.10.10.8` (used if URL is down)
- `--out` local directory
- `--timeout` seconds

## What comes back

`generate --out DIR` unpacks a full animation kit, not just one atlas:

- `manifest.json` — index for agents
- `video/{action}.mp4`
- `sheet/sheet.png` + `sheet.json` + `contact-sheet.png` (8-frame atlas)
- `frames/all/*.png` — **every** keyed, aligned frame at generation resolution (use this for animation)
- `frames/selected/*.png` — the 8 frames in the atlas
- `first-frame/staged.png`, `prompt.txt`

Do not import only `sheet.png` if you need a full cycle. Prefer `frames/all`.

## Rules

- Do not put MiniMax-H3 on the 10 GB RTX 3080 (`10.10.10.12`). Generate on olfa.
- `--recipe max` is BF16 and will not hit 2 minutes.
- Do not set `--steps` above 8 with turbo LoRA. Use last-frame lock instead of extra steps to stop turning.
- One H3 job at a time on olfa.
- First job after worker boot is cold (DiT load). Later jobs are the 2-minute target.
