package server

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"

	"github.com/StevenBuglione/sprite-gen/internal/spec"
)

type Server struct {
	Listen  string
	DataDir string
	Worker  string
	mu      sync.Mutex
	jobs    map[string]*job
}

type job struct {
	ID     string    `json:"id"`
	Status string    `json:"status"`
	Error  string    `json:"error,omitempty"`
	Dir    string    `json:"-"`
	Started time.Time `json:"started"`
}

func New(listen, dataDir, worker string) *Server {
	return &Server{Listen: listen, DataDir: dataDir, Worker: worker, jobs: map[string]*job{}}
}

func (s *Server) Serve() error {
	if err := os.MkdirAll(s.DataDir, 0o755); err != nil {
		return err
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/health", s.health)
	mux.HandleFunc("POST /v1/jobs", s.create)
	mux.HandleFunc("GET /v1/jobs/{id}", s.get)
	mux.HandleFunc("GET /v1/jobs/{id}/artifacts", s.artifacts)
	fmt.Println("sprite-gen serve", s.Listen)
	return http.ListenAndServe(s.Listen, mux)
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"ok":true,"service":"sprite-gen"}`))
}

func (s *Server) create(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(64 << 20); err != nil {
		http.Error(w, err.Error(), 400)
		return
	}
	sp, err := spec.DecodeJSON([]byte(r.FormValue("spec")))
	if err != nil {
		http.Error(w, "spec: "+err.Error(), 400)
		return
	}
	file, hdr, err := r.FormFile("image")
	if err != nil {
		http.Error(w, "image required", 400)
		return
	}
	defer file.Close()
	id := time.Now().UTC().Format("20060102T150405Z")
	dir := filepath.Join(s.DataDir, id)
	if err := os.MkdirAll(filepath.Join(dir, "out"), 0o755); err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	src, err := os.Create(filepath.Join(dir, "source.png"))
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	if _, err := io.Copy(src, file); err != nil {
		src.Close()
		http.Error(w, err.Error(), 500)
		return
	}
	src.Close()
	_ = hdr
	b, _ := sp.JSON()
	_ = os.WriteFile(filepath.Join(dir, "spec.json"), b, 0o644)
	j := &job{ID: id, Status: "queued", Dir: dir, Started: time.Now()}
	s.mu.Lock()
	s.jobs[id] = j
	s.mu.Unlock()
	go s.run(j)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(j)
}

func (s *Server) run(j *job) {
	s.set(j.ID, "running", "")
	cmd := exec.Command("python3", s.Worker, j.Dir)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Dir = j.Dir
	if err := cmd.Run(); err != nil {
		s.set(j.ID, "error", err.Error())
		return
	}
	s.set(j.ID, "done", "")
}

func (s *Server) set(id, status, err string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if j := s.jobs[id]; j != nil {
		j.Status = status
		j.Error = err
	}
}

func (s *Server) get(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	s.mu.Lock()
	j := s.jobs[id]
	s.mu.Unlock()
	if j == nil {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(j)
}

func (s *Server) artifacts(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	s.mu.Lock()
	j := s.jobs[id]
	s.mu.Unlock()
	if j == nil || j.Status != "done" {
		http.Error(w, "not ready", 409)
		return
	}
	out := filepath.Join(j.Dir, "out")
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", `attachment; filename="`+id+`.zip"`)
	zw := zip.NewWriter(w)
	defer zw.Close()
	entries, _ := os.ReadDir(out)
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		wf, err := zw.Create(e.Name())
		if err != nil {
			return
		}
		f, err := os.Open(filepath.Join(out, e.Name()))
		if err != nil {
			return
		}
		_, _ = io.Copy(wf, f)
		f.Close()
	}
}
