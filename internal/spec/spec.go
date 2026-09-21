package spec

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Spec is the full job request. Defaults live in defaults.toml; every field
// can be overridden by --config and then by CLI flags (last write wins).
type Spec struct {
	Guides            []Guide `json:"guides,omitempty"`
	Name              string  `json:"name" toml:"name"`
	Action            string  `json:"action" toml:"action"`
	Facing            string  `json:"facing" toml:"facing"`
	Recipe            string  `json:"recipe" toml:"recipe"`
	Style             string  `json:"style" toml:"style"`
	Identity          string  `json:"identity" toml:"identity"`
	Motion            string  `json:"motion" toml:"motion"`
	Prompt            string  `json:"prompt" toml:"prompt"`
	Width             int     `json:"width" toml:"width"`
	Height            int     `json:"height" toml:"height"`
	Seconds           float64 `json:"seconds" toml:"seconds"`
	FPS               int     `json:"fps" toml:"fps"`
	Steps             int     `json:"steps" toml:"steps"`
	Sampler           string  `json:"sampler" toml:"sampler"`
	Scheduler         string  `json:"scheduler" toml:"scheduler"`
	Seed              int64   `json:"seed" toml:"seed"`
	CFG               float64 `json:"cfg" toml:"cfg"`
	UNet              string  `json:"unet" toml:"unet"`
	LoRA              string  `json:"lora" toml:"lora"`
	CLIP              string  `json:"clip" toml:"clip"`
	Chroma            string  `json:"chroma" toml:"chroma"`
	MatteProfile      string  `json:"matte_profile" toml:"matte_profile"`
	FigureHeightRatio float64 `json:"figure_height_ratio" toml:"figure_height_ratio"`
	BaselineRatio     float64 `json:"baseline_ratio" toml:"baseline_ratio"`
	LoopLastFrame     bool    `json:"loop_last_frame" toml:"loop_last_frame"`
	Audio             bool    `json:"audio" toml:"audio"`
	CellWidth         int     `json:"cell_width" toml:"cell_width"`
	CellHeight        int     `json:"cell_height" toml:"cell_height"`
	BaseFrames        int     `json:"base_frames" toml:"base_frames"`
	FrameMS           int     `json:"frame_ms" toml:"frame_ms"`
	URL               string  `json:"url,omitempty" toml:"url"`
	SSH               string  `json:"ssh,omitempty" toml:"ssh"`
	TimeoutSeconds    int     `json:"timeout_seconds" toml:"timeout_seconds"`
}

// Guide is an already registered RGB PNG, carried with the portable job request.
type Guide struct {
	Frame int    `json:"frame"`
	PNG   []byte `json:"png"`
}

func Default() Spec {
	return Spec{
		Name: "sprite", Action: "idle", Facing: "down", Recipe: "quality",
		Style: "painterly 2D-animated game-sprite, inked illustration with cel-shaded cloth and a clean silhouette",
		Width: 512, Height: 512, Seconds: 2, FPS: 24, Steps: 4,
		Sampler: "euler", Scheduler: "simple", Seed: 424242, CFG: 1,
		UNet:   "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
		LoRA:   "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
		CLIP:   "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
		Chroma: "#FF00FF", MatteProfile: "chroma", FigureHeightRatio: 0.70, BaselineRatio: 0.856,
		LoopLastFrame: true, Audio: false,
		CellWidth: 128, CellHeight: 128, BaseFrames: 8, FrameMS: 100,
		URL: "http://10.10.10.8:8787", SSH: "olfa@10.10.10.8", TimeoutSeconds: 900,
	}
}

// ApplyRecipe overlays a named recipe. quality is the default (BF16, 8-step).
func (s *Spec) ApplyRecipe(name string) {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "", "quality":
		// INT8 + 4-step turbo + last-frame lock. DiT is 20 GB and can stay
		// resident with the encoder under --highvram (~51 GB).
		s.Recipe = "quality"
		s.Width, s.Height, s.Seconds, s.Steps = 512, 512, 2, 4
		s.UNet = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
		s.LoRA = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
		s.LoopLastFrame = true
		s.Audio = false
	case "fast":
		s.Recipe = "fast"
		s.Width, s.Height, s.Seconds, s.Steps = 512, 512, 2, 4
		s.UNet = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
		s.LoRA = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
		s.LoopLastFrame = true
		s.Audio = false
	case "max":
		s.Recipe = "max"
		s.Width, s.Height, s.Seconds, s.Steps = 640, 640, 3, 8
		s.UNet = "minimax_h3_fl2va_bf16.safetensors"
		s.LoRA = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
		s.LoopLastFrame = true
		s.Audio = false
	}
}

func (s Spec) Frames() int {
	// MiniMax-H3 length is 17n+5 at 24 fps.
	sec := s.Seconds
	if sec <= 0 {
		sec = 3
	}
	fps := s.FPS
	if fps <= 0 {
		fps = 24
	}
	raw := int(sec*float64(fps) + 0.5)
	if raw < 5 {
		raw = 5
	}
	mod := raw % 17
	need := (5 - mod) % 17
	if need < 0 {
		need += 17
	}
	return raw + need
}

func (s Spec) JSON() ([]byte, error) {
	return json.MarshalIndent(s, "", "  ")
}

func DecodeJSON(b []byte) (Spec, error) {
	s := Default()
	if err := json.Unmarshal(b, &s); err != nil {
		return Spec{}, err
	}
	return s, nil
}

// LoadTOML reads a flat TOML defaults/config file without a third-party parser.
func LoadTOML(path string, s *Spec) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return applyTOML(string(b), s)
}

func applyTOML(src string, s *Spec) error {
	for _, line := range strings.Split(src, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, "[") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		k = strings.TrimSpace(k)
		v = strings.TrimSpace(v)
		v = strings.Trim(v, `"`)
		if err := setField(s, k, v); err != nil {
			return fmt.Errorf("%s: %w", k, err)
		}
	}
	return nil
}

func setField(s *Spec, k, v string) error {
	switch k {
	case "name":
		s.Name = v
	case "action":
		s.Action = v
	case "facing":
		s.Facing = v
	case "recipe":
		s.ApplyRecipe(v)
	case "style":
		s.Style = v
	case "identity":
		s.Identity = v
	case "motion":
		s.Motion = v
	case "prompt":
		s.Prompt = v
	case "width":
		n, err := strconv.Atoi(v)
		s.Width = n
		return err
	case "height":
		n, err := strconv.Atoi(v)
		s.Height = n
		return err
	case "seconds":
		n, err := strconv.ParseFloat(v, 64)
		s.Seconds = n
		return err
	case "fps":
		n, err := strconv.Atoi(v)
		s.FPS = n
		return err
	case "steps":
		n, err := strconv.Atoi(v)
		s.Steps = n
		return err
	case "sampler":
		s.Sampler = v
	case "scheduler":
		s.Scheduler = v
	case "seed":
		n, err := strconv.ParseInt(v, 10, 64)
		s.Seed = n
		return err
	case "cfg":
		n, err := strconv.ParseFloat(v, 64)
		s.CFG = n
		return err
	case "unet":
		s.UNet = v
	case "lora":
		s.LoRA = v
	case "clip":
		s.CLIP = v
	case "chroma":
		s.Chroma = v
	case "matte_profile":
		s.MatteProfile = v
	case "figure_height_ratio":
		n, err := strconv.ParseFloat(v, 64)
		s.FigureHeightRatio = n
		return err
	case "baseline_ratio":
		n, err := strconv.ParseFloat(v, 64)
		s.BaselineRatio = n
		return err
	case "loop_last_frame":
		s.LoopLastFrame = v == "true" || v == "1"
	case "audio":
		s.Audio = v == "true" || v == "1"
	case "cell_width":
		n, err := strconv.Atoi(v)
		s.CellWidth = n
		return err
	case "cell_height":
		n, err := strconv.Atoi(v)
		s.CellHeight = n
		return err
	case "base_frames":
		n, err := strconv.Atoi(v)
		s.BaseFrames = n
		return err
	case "frame_ms":
		n, err := strconv.Atoi(v)
		s.FrameMS = n
		return err
	case "url":
		s.URL = v
	case "ssh":
		s.SSH = v
	case "timeout_seconds":
		n, err := strconv.Atoi(v)
		s.TimeoutSeconds = n
		return err
	}
	return nil
}

func FindDefaults() string {
	cands := []string{"defaults.toml"}
	if exe, err := os.Executable(); err == nil {
		cands = append(cands, filepath.Join(filepath.Dir(exe), "defaults.toml"))
	}
	if home, err := os.UserHomeDir(); err == nil {
		cands = append(cands, filepath.Join(home, ".sprite-gen", "defaults.toml"))
	}
	for _, p := range cands {
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p
		}
	}
	return ""
}

func Dump(s Spec) string {
	b, _ := s.JSON()
	return string(bytes.TrimSpace(b))
}
