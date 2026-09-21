package spec

import (
	"bytes"
	"encoding/json"
	"fmt"
	"image/png"
	"os"
	"path/filepath"
)

// LoadGuides validates before contacting the worker. Guides use the full video
// canvas; independently fitting each silhouette would destroy foot registration.
func LoadGuides(path string, frames, width, height int, lastLocked bool) ([]Guide, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var rows []struct {
		Frame int    `json:"frame"`
		Image string `json:"image"`
	}
	if err = json.Unmarshal(content, &rows); err != nil {
		return nil, err
	}
	if len(rows) < 1 || len(rows) > 8 {
		return nil, fmt.Errorf("require 1-8 pose guides")
	}
	seen := map[int]bool{}
	result := make([]Guide, 0, len(rows))
	for _, row := range rows {
		if row.Frame <= 0 || row.Frame >= frames || (lastLocked && row.Frame == frames-1) || seen[row.Frame] {
			return nil, fmt.Errorf("duplicate, anchored, or out-of-range guide frame %d", row.Frame)
		}
		seen[row.Frame] = true
		imagePath := row.Image
		if !filepath.IsAbs(imagePath) {
			imagePath = filepath.Join(filepath.Dir(path), imagePath)
		}
		data, err := os.ReadFile(imagePath)
		if err != nil {
			return nil, err
		}
		if len(data) > 6<<20 {
			return nil, fmt.Errorf("guide exceeds 6 MiB: %s", imagePath)
		}
		config, err := png.DecodeConfig(bytes.NewReader(data))
		if err != nil {
			return nil, fmt.Errorf("guide must be PNG: %w", err)
		}
		if config.Width != width || config.Height != height {
			return nil, fmt.Errorf("guide %s must match %dx%d video canvas", imagePath, width, height)
		}
		result = append(result, Guide{Frame: row.Frame, PNG: data})
	}
	return result, nil
}
