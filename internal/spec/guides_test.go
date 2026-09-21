package spec

import (
	"encoding/json"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"testing"
)

func TestGuideCanvasAndPortableJSON(t *testing.T) {
	dir := t.TempDir()
	file, _ := os.Create(filepath.Join(dir, "pose.png"))
	if err := png.Encode(file, image.NewRGBA(image.Rect(0, 0, 64, 48))); err != nil {
		t.Fatal(err)
	}
	file.Close()
	path := filepath.Join(dir, "guides.json")
	os.WriteFile(path, []byte(`[{"frame":9,"image":"pose.png"}]`), 0600)
	guides, err := LoadGuides(path, 39, 64, 48, true)
	if err != nil {
		t.Fatal(err)
	}
	s := Default()
	s.Guides = guides
	data, _ := json.Marshal(s)
	decoded, err := DecodeJSON(data)
	if err != nil || len(decoded.Guides) != 1 || string(decoded.Guides[0].PNG) != string(guides[0].PNG) {
		t.Fatal("guide pixels lost in transport", err)
	}
	if _, err := LoadGuides(path, 39, 32, 48, true); err == nil {
		t.Fatal("accepted misregistered canvas")
	}
	os.WriteFile(path, []byte(`[{"frame":38,"image":"pose.png"}]`), 0600)
	if _, err := LoadGuides(path, 39, 64, 48, true); err == nil {
		t.Fatal("accepted conflicting last anchor")
	}
}
