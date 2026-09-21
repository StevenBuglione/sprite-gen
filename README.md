# sprite-gen

Go CLI that sends a character still to **olfa** (`10.10.10.8`) and returns a MiniMax-H3 video plus a packed sprite sheet.

Default recipe is **quality**: BF16 FL2VA, 8-step turbo LoRA, 640×640, 3 s (73 frames), last frame locked to the first, no audio. That is the best sheet we have produced on this box inside a ~2 minute hot-DiT budget.

Agents: read [`SKILL.md`](SKILL.md). Numbers live in [`defaults.toml`](defaults.toml).

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
| `quality` | Ship. BF16 + 8-step turbo. |
| `fast` | Prompt hunt only. INT8 + 4-step. |

Every default is a flag. `sprite-gen generate --help` lists them.
