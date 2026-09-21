package client

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/StevenBuglione/sprite-gen/internal/spec"
)

type Job struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Error  string `json:"error,omitempty"`
	MP4    string `json:"mp4,omitempty"`
	Sheet  string `json:"sheet,omitempty"`
}

func Generate(image string, s spec.Spec, outDir string) error {
	if image == "" {
		return fmt.Errorf("--image is required")
	}
	if s.Identity == "" && s.Prompt == "" {
		return fmt.Errorf("--identity is required unless --prompt is set")
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	if err := generateHTTP(image, s, outDir); err != nil {
		fmt.Fprintf(os.Stderr, "http %s failed (%v); trying ssh %s\n", s.URL, err, s.SSH)
		return generateSSH(image, s, outDir)
	}
	return nil
}

func generateHTTP(image string, s spec.Spec, outDir string) error {
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	specJSON, err := s.JSON()
	if err != nil {
		return err
	}
	_ = w.WriteField("spec", string(specJSON))
	part, err := w.CreateFormFile("image", filepath.Base(image))
	if err != nil {
		return err
	}
	f, err := os.Open(image)
	if err != nil {
		return err
	}
	if _, err := io.Copy(part, f); err != nil {
		f.Close()
		return err
	}
	f.Close()
	_ = w.Close()

	client := &http.Client{Timeout: time.Duration(s.TimeoutSeconds) * time.Second}
	base := strings.TrimRight(s.URL, "/")
	req, err := http.NewRequest(http.MethodPost, base+"/v1/jobs", body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("create job: %s: %s", resp.Status, b)
	}
	var job Job
	if err := json.NewDecoder(resp.Body).Decode(&job); err != nil {
		return err
	}
	fmt.Printf("job %s queued\n", job.ID)
	deadline := time.Now().Add(time.Duration(s.TimeoutSeconds) * time.Second)
	for time.Now().Before(deadline) {
		time.Sleep(3 * time.Second)
		st, err := getJSON(client, base+"/v1/jobs/"+job.ID)
		if err != nil {
			return err
		}
		if st.Status == "done" {
			return downloadZip(client, base+"/v1/jobs/"+job.ID+"/artifacts", outDir)
		}
		if st.Status == "error" {
			return fmt.Errorf("job failed: %s", st.Error)
		}
		fmt.Printf("status %s\n", st.Status)
	}
	return fmt.Errorf("timeout waiting for job %s", job.ID)
}

func getJSON(c *http.Client, url string) (Job, error) {
	resp, err := c.Get(url)
	if err != nil {
		return Job{}, err
	}
	defer resp.Body.Close()
	var j Job
	err = json.NewDecoder(resp.Body).Decode(&j)
	return j, err
}

func downloadZip(c *http.Client, url, outDir string) error {
	resp, err := c.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("artifacts: %s: %s", resp.Status, b)
	}
	tmp, err := os.CreateTemp("", "sprite-gen-*.zip")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := io.Copy(tmp, resp.Body); err != nil {
		tmp.Close()
		return err
	}
	tmp.Close()
	zr, err := zip.OpenReader(tmp.Name())
	if err != nil {
		return err
	}
	defer zr.Close()
	for _, f := range zr.File {
		dest := filepath.Join(outDir, filepath.Base(f.Name))
		rc, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.Create(dest)
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.Copy(out, rc)
		out.Close()
		rc.Close()
		if err != nil {
			return err
		}
		fmt.Println("wrote", dest)
	}
	return nil
}

func generateSSH(image string, s spec.Spec, outDir string) error {
	host := s.SSH
	if host == "" {
		return fmt.Errorf("no --url and no --ssh")
	}
	remote := fmt.Sprintf("/tmp/sprite-gen-%d", time.Now().UnixNano())
	specJSON, err := s.JSON()
	if err != nil {
		return err
	}
	if err := run("ssh", host, "mkdir", "-p", remote+"/out"); err != nil {
		return err
	}
	if err := run("scp", image, host+":"+remote+"/source.png"); err != nil {
		return err
	}
	tmpSpec, err := os.CreateTemp("", "spec-*.json")
	if err != nil {
		return err
	}
	if _, err := tmpSpec.Write(specJSON); err != nil {
		tmpSpec.Close()
		return err
	}
	tmpSpec.Close()
	defer os.Remove(tmpSpec.Name())
	if err := run("scp", tmpSpec.Name(), host+":"+remote+"/spec.json"); err != nil {
		return err
	}
	worker := os.Getenv("SPRITE_GEN_WORKER")
	if worker == "" {
		worker = "/home/olfa/ai/sprite-gen/worker/run_job.py"
	}
	if err := run("ssh", host, "python3", worker, remote); err != nil {
		return err
	}
	return run("scp", "-r", host+":"+remote+"/out/.", outDir)
}

func run(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	fmt.Println("+", name, strings.Join(args, " "))
	return cmd.Run()
}

func Status(url string) error {
	resp, err := http.Get(strings.TrimRight(url, "/") + "/v1/health")
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, err = io.Copy(os.Stdout, resp.Body)
	return err
}
