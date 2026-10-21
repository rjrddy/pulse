package gateway

import (
	"bufio"
	"encoding/json"
	"errors"
	"os"
	"sync"
	"time"
)

type Record struct {
	ID           string    `json:"id"`
	Outcome      string    `json:"outcome"`
	Backend      string    `json:"backend"`
	FirstAudioMS float64   `json:"first_audio_ms"`
	TotalMS      float64   `json:"total_ms"`
	At           time.Time `json:"at"`
}
type Journal struct {
	mu      sync.Mutex
	file    *os.File
	records []Record
}

func OpenJournal(path string) (*Journal, error) {
	f, e := os.OpenFile(path, os.O_CREATE|os.O_RDWR|os.O_APPEND, 0600)
	if e != nil {
		return nil, e
	}
	j := &Journal{file: f}
	s := bufio.NewScanner(f)
	for s.Scan() {
		var r Record
		if e = json.Unmarshal(s.Bytes(), &r); e != nil {
			f.Close()
			return nil, errors.New("corrupt journal; inspect before restart")
		}
		j.records = append(j.records, r)
		if len(j.records) > 200 {
			j.records = append([]Record{}, j.records[len(j.records)-200:]...)
		}
	}
	if e = s.Err(); e != nil {
		f.Close()
		return nil, e
	}
	return j, nil
}
func (j *Journal) Close() error { return j.file.Close() }
func (j *Journal) Append(r Record) error {
	j.mu.Lock()
	defer j.mu.Unlock()
	b, e := json.Marshal(r)
	if e != nil {
		return e
	}
	if _, e = j.file.Write(append(b, '\n')); e != nil {
		return e
	}
	if e = j.file.Sync(); e != nil {
		return e
	}
	j.records = append(j.records, r)
	if len(j.records) > 200 {
		j.records = append([]Record{}, j.records[len(j.records)-200:]...)
	}
	return nil
}
func (j *Journal) History() []Record {
	j.mu.Lock()
	defer j.mu.Unlock()
	start := max(0, len(j.records)-200)
	return append([]Record{}, j.records[start:]...)
}
