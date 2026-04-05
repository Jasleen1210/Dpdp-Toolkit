package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"time"

	"dpdp-toolkit/agent-go/internal/config"
	"dpdp-toolkit/agent-go/internal/types"
)

type Client struct {
	httpClient *http.Client
	cfg        config.Config
}

func New(cfg config.Config) *Client {
	return &Client{
		httpClient: &http.Client{Timeout: 30 * time.Second},
		cfg:        cfg,
	}
}

func (c *Client) Register(ctx context.Context, payload types.DeviceRegistrationRequest) error {
	return c.postJSON(ctx, c.cfg.RegisterPath, payload, nil)
}

func (c *Client) FetchTasks(ctx context.Context, deviceID string) ([]types.Task, error) {
	pollRes, err := c.FetchTaskPoll(ctx, deviceID, "")
	if err != nil {
		return nil, err
	}
	return pollRes.Tasks, nil
}

func (c *Client) FetchTaskPoll(ctx context.Context, deviceID, since string) (types.TaskPollResponse, error) {
	u, err := c.makeURL(c.cfg.TasksPath)
	if err != nil {
		return types.TaskPollResponse{}, err
	}
	q := u.Query()
	q.Set("device_id", deviceID)
	if since != "" {
		q.Set("since", since)
	}
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return types.TaskPollResponse{}, err
	}
	c.applyHeaders(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return types.TaskPollResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return types.TaskPollResponse{}, fmt.Errorf("fetch tasks failed: status=%d body=%s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return types.TaskPollResponse{}, err
	}

	var poll types.TaskPollResponse
	if err := json.Unmarshal(body, &poll); err == nil {
		if poll.Tasks == nil {
			poll.Tasks = []types.Task{}
		}
		if poll.Updates == nil {
			poll.Updates = []types.TaskUpdate{}
		}
		return poll, nil
	}

	var direct []types.Task
	if err := json.Unmarshal(body, &direct); err == nil {
		return types.TaskPollResponse{Tasks: direct, Updates: []types.TaskUpdate{}}, nil
	}

	var wrapped types.TaskListResponse
	if err := json.Unmarshal(body, &wrapped); err != nil {
		return types.TaskPollResponse{}, fmt.Errorf("unable to parse task response: %w", err)
	}
	return types.TaskPollResponse{Tasks: wrapped.Tasks, Updates: []types.TaskUpdate{}}, nil
}

func (c *Client) SubmitResult(ctx context.Context, payload types.TaskResultPayload) error {
	return c.postJSON(ctx, c.cfg.ResultsPath, payload, nil)
}

func (c *Client) postJSON(ctx context.Context, p string, in any, out any) error {
	b, err := json.Marshal(in)
	if err != nil {
		return err
	}

	u, err := c.makeURL(p)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(b))
	if err != nil {
		return err
	}
	c.applyHeaders(req)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("request failed: path=%s status=%d body=%s", p, resp.StatusCode, string(body))
	}

	if out != nil {
		return json.NewDecoder(resp.Body).Decode(out)
	}
	return nil
}

func (c *Client) makeURL(p string) (*url.URL, error) {
	base, err := url.Parse(c.cfg.ServerURL)
	if err != nil {
		return nil, err
	}
	base.Path = path.Clean(base.Path + "/" + p)
	return base, nil
}

func (c *Client) applyHeaders(req *http.Request) {
	if c.cfg.OrgID != "" {
		req.Header.Set("X-Org-Id", c.cfg.OrgID)
	}
	if c.cfg.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.cfg.APIKey)
	}
}
