# Modal Browser Agent

A LiveKit agent that captures a web page using Playwright and publishes it as
video to a room, deployed on Modal.

## Deploy

```bash
python modal-browser-agent/agent_pool.py deploy
```

This deploys the pool manager and creates the initial set of warm sandboxes.
The sandbox image includes Chromium installed via Playwright.

## What It Does

When a room is created and LiveKit dispatches a job, the agent:

1. Marks itself as active and triggers pool replenishment
2. Launches a headless Chromium browser and navigates to Hacker News
3. Connects to the room and publishes the browser content as a video track

To change the target URL or viewport, edit `agent_worker.py`:

```python
page = await browser_ctx.new_page(
    url="https://news.ycombinator.com",  # change this
    width=1280,
    height=720,
    framerate=30,
)
```

## Files

| File | Description |
|---|---|
| `agent_worker.py` | The agent entrypoint — browser capture logic |
| `agent_pool.py` | Pool configuration and deployment CLI |
