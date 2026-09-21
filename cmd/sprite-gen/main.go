package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/StevenBuglione/sprite-gen/internal/client"
	"github.com/StevenBuglione/sprite-gen/internal/server"
	"github.com/StevenBuglione/sprite-gen/internal/spec"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "generate":
		os.Exit(runGenerate(os.Args[2:]))
	case "serve":
		os.Exit(runServe(os.Args[2:]))
	case "status":
		os.Exit(runStatus(os.Args[2:]))
	case "help", "-h", "--help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command %s\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, `sprite-gen — remote MiniMax-H3 sprite sheets

  sprite-gen generate --image still.png --identity "..."
  sprite-gen status
  sprite-gen serve --listen 0.0.0.0:8787

Defaults: defaults.toml (quality recipe). Skill: SKILL.md
`)
}

func runGenerate(args []string) int {
	s := spec.Default()
	if p := spec.FindDefaults(); p != "" {
		_ = spec.LoadTOML(p, &s)
	}
	fs := flag.NewFlagSet("generate", flag.ExitOnError)
	image := fs.String("image", "", "source still (required)")
	out := fs.String("out", "out", "local output directory")
	config := fs.String("config", "", "TOML overlay")
	guides := fs.String("guides", "", "JSON array of {frame,image} registered PNG pose guides")
	recipe := fs.String("recipe", s.Recipe, "quality|fast|max")
	fs.StringVar(&s.Name, "name", s.Name, "character name")
	fs.StringVar(&s.Action, "action", s.Action, "idle, walk, attack, ...")
	fs.StringVar(&s.Facing, "facing", s.Facing, "down, up, left, right, _ (side aliases right)")
	fs.StringVar(&s.Identity, "identity", s.Identity, "view-neutral character description")
	fs.StringVar(&s.Style, "style", s.Style, "art style")
	fs.StringVar(&s.Motion, "motion", s.Motion, "one-cycle motion text")
	fs.StringVar(&s.Prompt, "prompt", s.Prompt, "full H3 prompt (skips composer)")
	fs.IntVar(&s.Width, "width", s.Width, "canvas width")
	fs.IntVar(&s.Height, "height", s.Height, "canvas height")
	fs.Float64Var(&s.Seconds, "seconds", s.Seconds, "requested duration")
	fs.IntVar(&s.FPS, "fps", s.FPS, "frames per second")
	fs.IntVar(&s.Steps, "steps", s.Steps, "sampler steps")
	fs.StringVar(&s.Sampler, "sampler", s.Sampler, "euler, ...")
	fs.StringVar(&s.Scheduler, "scheduler", s.Scheduler, "simple, ...")
	fs.Int64Var(&s.Seed, "seed", s.Seed, "noise seed")
	fs.Float64Var(&s.CFG, "cfg", s.CFG, "CFG scale")
	_ = fs.String("unet", s.UNet, "bf16|int8|filename")
	_ = fs.String("lora", s.LoRA, "8step|4step|none|filename")
	fs.StringVar(&s.CLIP, "clip", s.CLIP, "text encoder filename")
	fs.StringVar(&s.Chroma, "chroma", s.Chroma, "key color")
	fs.StringVar(&s.MatteProfile, "matte-profile", s.MatteProfile, "chroma|neutral-warm|deferred (deferred returns raw frames for external neural matting)")
	fs.Float64Var(&s.FigureHeightRatio, "figure-height-ratio", s.FigureHeightRatio, "figure height vs canvas")
	fs.Float64Var(&s.BaselineRatio, "baseline-ratio", s.BaselineRatio, "foot baseline")
	_ = fs.Bool("loop-last-frame", s.LoopLastFrame, "pin last frame to first")
	_ = fs.Bool("no-loop-last-frame", false, "disable last-frame lock")
	_ = fs.Bool("audio", s.Audio, "decode H3 audio")
	_ = fs.Bool("no-audio", false, "skip audio decode")
	fs.IntVar(&s.CellWidth, "cell-width", s.CellWidth, "sheet cell width")
	fs.IntVar(&s.CellHeight, "cell-height", s.CellHeight, "sheet cell height")
	fs.IntVar(&s.BaseFrames, "base-frames", s.BaseFrames, "frames kept in the sheet")
	fs.IntVar(&s.FrameMS, "frame-ms", s.FrameMS, "ms per sheet frame")
	fs.StringVar(&s.URL, "url", s.URL, "worker URL")
	fs.StringVar(&s.SSH, "ssh", s.SSH, "ssh fallback host")
	fs.IntVar(&s.TimeoutSeconds, "timeout", s.TimeoutSeconds, "job timeout seconds")
	_ = fs.Parse(args)
	if *config != "" {
		if err := spec.LoadTOML(*config, &s); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
	}
	explicit := map[string]bool{}
	fs.Visit(func(f *flag.Flag) { explicit[f.Name] = true })
	if explicit["recipe"] {
		s.ApplyRecipe(*recipe)
	}
	fs.Visit(func(f *flag.Flag) {
		switch f.Name {
		case "name":
			s.Name = f.Value.String()
		case "action":
			s.Action = f.Value.String()
		case "facing":
			s.Facing = f.Value.String()
		case "identity":
			s.Identity = f.Value.String()
		case "style":
			s.Style = f.Value.String()
		case "motion":
			s.Motion = f.Value.String()
		case "prompt":
			s.Prompt = f.Value.String()
		case "width":
			fmt.Sscanf(f.Value.String(), "%d", &s.Width)
		case "height":
			fmt.Sscanf(f.Value.String(), "%d", &s.Height)
		case "seconds":
			fmt.Sscanf(f.Value.String(), "%f", &s.Seconds)
		case "fps":
			fmt.Sscanf(f.Value.String(), "%d", &s.FPS)
		case "steps":
			fmt.Sscanf(f.Value.String(), "%d", &s.Steps)
		case "sampler":
			s.Sampler = f.Value.String()
		case "scheduler":
			s.Scheduler = f.Value.String()
		case "seed":
			fmt.Sscanf(f.Value.String(), "%d", &s.Seed)
		case "cfg":
			fmt.Sscanf(f.Value.String(), "%f", &s.CFG)
		case "unet":
			s.UNet = expandUNet(f.Value.String())
		case "lora":
			s.LoRA = expandLoRA(f.Value.String())
		case "clip":
			s.CLIP = f.Value.String()
		case "chroma":
			s.Chroma = f.Value.String()
		case "matte-profile":
			s.MatteProfile = f.Value.String()
		case "figure-height-ratio":
			fmt.Sscanf(f.Value.String(), "%f", &s.FigureHeightRatio)
		case "baseline-ratio":
			fmt.Sscanf(f.Value.String(), "%f", &s.BaselineRatio)
		case "frame-ms":
			fmt.Sscanf(f.Value.String(), "%d", &s.FrameMS)
		case "loop-last-frame":
			s.LoopLastFrame = f.Value.String() == "true"
		case "no-loop-last-frame":
			s.LoopLastFrame = false
		case "audio":
			s.Audio = f.Value.String() == "true"
		case "no-audio":
			s.Audio = false
		case "cell-width":
			fmt.Sscanf(f.Value.String(), "%d", &s.CellWidth)
		case "cell-height":
			fmt.Sscanf(f.Value.String(), "%d", &s.CellHeight)
		case "base-frames":
			fmt.Sscanf(f.Value.String(), "%d", &s.BaseFrames)
		case "url":
			s.URL = f.Value.String()
		case "ssh":
			s.SSH = f.Value.String()
		case "timeout":
			fmt.Sscanf(f.Value.String(), "%d", &s.TimeoutSeconds)
		}
	})
	if *guides != "" {
		var err error
		s.Guides, err = spec.LoadGuides(*guides, s.Frames(), s.Width, s.Height, s.LoopLastFrame)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
	}
	if err := client.Generate(*image, s, *out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func expandUNet(v string) string {
	switch strings.ToLower(v) {
	case "bf16":
		return "minimax_h3_fl2va_bf16.safetensors"
	case "int8":
		return "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
	default:
		return v
	}
}

func expandLoRA(v string) string {
	switch strings.ToLower(v) {
	case "8step":
		return "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
	case "4step":
		return "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
	case "none", "off":
		return ""
	default:
		return v
	}
}

func runServe(args []string) int {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	listen := fs.String("listen", "0.0.0.0:8787", "bind address")
	data := fs.String("data", defaultData(), "job directory")
	worker := fs.String("worker", defaultWorker(), "python run_job.py")
	_ = fs.Parse(args)
	if err := server.New(*listen, *data, *worker).Serve(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func runStatus(args []string) int {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	url := fs.String("url", spec.Default().URL, "worker URL")
	_ = fs.Parse(args)
	if err := client.Status(*url); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func defaultData() string {
	if v := os.Getenv("SPRITE_GEN_DATA"); v != "" {
		return v
	}
	return "/home/olfa/ai/sprite-gen/data"
}

func defaultWorker() string {
	if v := os.Getenv("SPRITE_GEN_WORKER"); v != "" {
		return v
	}
	if exe, err := os.Executable(); err == nil {
		p := filepath.Join(filepath.Dir(exe), "worker", "run_job.py")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "/home/olfa/ai/sprite-gen/worker/run_job.py"
}
