# LiveKit Agents on Modal

Examples of deploying [LiveKit Agents](https://docs.livekit.io/agents/) on [Modal](https://modal.com) using a warm sandbox pool.

## Examples

| Example | Description |
|---|---|
| [`modal-basic-agent/`](modal-basic-agent/) | Minimal agent that connects to a room and logs. Good starting point. |
| [`modal-browser-agent/`](modal-browser-agent/) | Captures a web page with Playwright and publishes it as video to a room. |
| [`modal-avatar-agent/`](modal-avatar-agent/) | Voice agent (OpenAI Realtime) with an audio-wave avatar rendered on a GPU. |

## How It Works

Each example uses a **warm sandbox pool** to keep LiveKit agents connected and
ready for instant dispatch. The pool infrastructure lives in
[`shared/sandbox_pool.py`](shared/sandbox_pool.py) and is reused by all examples.

```
┌──────────────────┐
│  LiveKit Server   │
│                    │
│  Dispatches jobs   │
│  to idle agents    │
└────────┬───────────┘
         │ WebSocket
         ▼
┌──────────────────┐       HTTP POST        ┌──────────────────┐
│  Sandbox (idle)   │ ────────────────────▶ │  Pool Manager     │
│  Sandbox (idle)   │  "activate" /          │                    │
│  Sandbox (active) │  "deactivate" /        │  Tracks state,     │
│  ...              │  "replenish"           │  creates/removes   │
└──────────────────┘                         │  sandboxes         │
                                              └──────────────────┘
```

**Lifecycle:**

1. The pool maintains N idle sandboxes, each running an agent worker connected
   to LiveKit via WebSocket.
2. LiveKit assigns a job to an idle worker. The worker calls `activate` (marks
   itself busy) and `replenish` (triggers creation of a replacement sandbox).
3. When the job ends, the worker calls `deactivate`.
4. Scheduled maintenance runs every minute: terminates dead sandboxes, replaces
   expiring idle ones, and tops up the pool.

Active sandboxes are never terminated by the pool — only dead or idle sandboxes
are cleaned up.

## Prerequisites

- A [Modal](https://modal.com) account with the `modal` CLI installed and authenticated
- A [LiveKit Cloud](https://livekit.io) project (or self-hosted server)
- [uv](https://docs.astral.sh/uv/) for Python dependency management

## Setup

All commands should be run from the repo root.

### 1. Install dependencies

```bash
uv sync
```

### 2. Create the Modal secret

Store your LiveKit and OpenAI credentials as a Modal secret named `livekit-agent`:

```bash
modal secret create livekit-agent \
  LIVEKIT_URL=wss://your-project.livekit.cloud \
  LIVEKIT_API_KEY=your-api-key \
  LIVEKIT_API_SECRET=your-api-secret \
  OPENAI_API_KEY=your-openai-key
```

> Not all examples need every key. The basic and browser agents only require
> `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. The avatar agent
> also needs `OPENAI_API_KEY`.

### 3. Deploy an example

See the README in each example directory for deployment steps.

## Pool Management

Every example uses the same CLI for pool management:

```bash
# Deploy the pool and create initial sandboxes
python <example>/agent_pool.py deploy

# Check pool status (idle/active/dead, time remaining)
python <example>/agent_pool.py check

# Manually trigger maintenance
python <example>/agent_pool.py maintain
```

## Configuration

Pool behavior is configured via `PoolConfig` in each example's `agent_pool.py`.
Defaults from [`shared/sandbox_pool.py`](shared/sandbox_pool.py):

| Parameter | Default | Description |
|---|---|---|
| `pool_size` | 3 | Number of idle sandboxes to maintain |
| `sandbox_timeout_seconds` | 86400 (24h) | Modal sandbox lifetime |
| `min_remaining_seconds` | 7200 (2h) | Idle sandboxes with less time remaining are replaced |
| `maintenance_interval_minutes` | 1 | How often scheduled maintenance runs |
| `sandbox_region` | `us-west` | Region for sandbox containers |

## Testing

Join a LiveKit room using the
[Agents Playground](https://agents-playground.livekit.io/) (connected to your
LiveKit project). The deployed agent should pick up the job automatically.

## Debugging

- **Pool status:** `python <example>/agent_pool.py check`
- **Sandbox logs:** Modal dashboard → your `*-sandboxes` app → click a sandbox
- **Pool function logs:** Modal dashboard → your `*-pool` app → function logs
- **Agent not connecting:** Verify the `livekit-agent` secret has correct values

## Project Structure

```
├── shared/
│   └── sandbox_pool.py        # Reusable pool infrastructure
├── basic-agents/               # Original non-Modal agent scripts
│   ├── minimal_worker.py
│   └── browser_agent.py
├── modal-basic-agent/          # Minimal agent on Modal
│   ├── agent_worker.py
│   └── agent_pool.py
├── modal-browser-agent/        # Browser capture agent on Modal
│   ├── agent_worker.py
│   └── agent_pool.py
└── modal-avatar-agent/         # Voice agent + avatar on Modal
    ├── agent_worker.py
    ├── agent_pool.py
    ├── dispatcher.py
    ├── avatar_runner.py
    └── wave_viz.py
```
