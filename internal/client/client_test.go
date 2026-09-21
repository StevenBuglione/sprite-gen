package client

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/StevenBuglione/sprite-gen/internal/spec"
)

func TestFailedSubmittedJobDoesNotFallBackToSSH(t *testing.T) {
	submissions := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/v1/health":
			fmt.Fprint(w, `{"ok":true}`)
		case r.Method == "POST":
			submissions++
			fmt.Fprint(w, `{"id":"job-1","status":"queued"}`)
		default:
			fmt.Fprint(w, `{"id":"job-1","status":"error","error":"preview atlas too small"}`)
		}
	}))
	defer srv.Close()
	tmp := t.TempDir()
	source := filepath.Join(tmp, "source.png")
	if err := os.WriteFile(source, []byte("fixture"), 0600); err != nil {
		t.Fatal(err)
	}
	s := spec.Default()
	s.URL = srv.URL
	s.SSH = "invalid-do-not-run"
	s.Identity = "fixture"
	err := Generate(source, s, filepath.Join(tmp, "out"))
	if err == nil || !strings.Contains(err.Error(), "job job-1 failed") {
		t.Fatalf("unexpected error: %v", err)
	}
	if submissions != 1 {
		t.Fatalf("submitted %d jobs", submissions)
	}
}
