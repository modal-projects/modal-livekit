# Modal Avatar Agent

A LiveKit voice agent with an audio-wave avatar, deployed on [Modal](https://modal.com).

## Architecture

The system has three components that run on Modal:

```
┌─────────────────────┐       HTTP POST        ┌─────────────────────┐
│   Agent Worker      │ ───────────────────────▶│  Avatar Dispatcher  │
│   (Sandbox Pool)    │  "launch avatar for     │  (Modal Cls)        │
│                     │   this room"            │                     │
│  Connects to LK,    │                         │  Spawns avatar_     │
│  waits for jobs,    │       HTTP POST         │  runner.py as       │
│  runs voice agent   │ ──────────────┐         │  subprocess, blocks │
│                     │  "replenish   │         │  until done         │
└─────────────────────┘   the pool"   │         └─────────────────────┘
                                      ▼
                          ┌─────────────────────┐
                          │  Agent Pool         │
                          │  (Sandbox Manager)  │
                          │                     │
                          │  Maintains warm     │
                          │  sandbox pool,      │
                          │  scheduled cleanup  │
                          └─────────────────────┘
```

- **Agent Worker** (`agent_worker.py`): The LiveKit agent. Runs inside Modal Sandboxes,
  connects to LiveKit via WebSocket, and waits for job dispatch. When a job arrives, it
  launches an avatar worker and starts a voice session. It also triggers pool replenishment
  so there's always a warm agent ready.

- **Avatar Dispatcher** (`dispatcher.py`): A Modal Cls that launches `avatar_runner.py`
  as a subprocess and blocks until the avatar session completes. Exposes an HTTP POST
  endpoint (`launch_avatar`) so the agent worker can fire-and-forget.

- **Agent Pool** (`agent_pool.py`): Manages a pool of warm Sandboxes, each running an
  agent worker. Replenishment happens two ways: immediately (via HTTP POST from the agent
  worker when it takes a job) and on a schedule (safety net cleanup every minute).

- **Avatar Runner** (`avatar_runner.py`): Connects to a LiveKit room, generates audio-wave
  video frames synced to TTS output, and publishes them. Uses `wave_viz.py` for waveform
  rendering.

## Prerequisites

- A [Modal](https://modal.com) account with `modal` CLI installed and authenticated
- A [LiveKit](https://livekit.io) Cloud project (or self-hosted server)
- An OpenAI API key (for the realtime voice model)

## Setup

### 1. Create the Modal secret

Store your LiveKit and OpenAI credentials as a Modal secret:

```bash
modal secret create livekit-agent \
  LIVEKIT_URL=wss://your-project.livekit.cloud \
  LIVEKIT_API_KEY=your-api-key \
  LIVEKIT_API_SECRET=your-api-secret \
  OPENAI_API_KEY=your-openai-key
```

### 2. Deploy the Avatar Dispatcher

```bash
modal deploy -m modal-avatar-agent.dispatcher
```

### 3. Deploy the Agent Pool

```bash
python -m examples.avatar_agents.audio_wave.modal.agent_pool deploy
```

This deploys the pool manager and starts the scheduled maintenance function,
which will create the initial set of warm sandboxes.

### 4. Run initial pool maintenance

To immediately populate the pool without waiting for the first scheduled run:

```bash
python -m examples.avatar_agents.audio_wave.modal.agent_pool maintain
```

## Pool Management

```bash
# Check current pool status
python -m examples.avatar_agents.audio_wave.modal.agent_pool check

# Manually trigger maintenance (cleanup + replenish)
python -m examples.avatar_agents.audio_wave.modal.agent_pool maintain
```

## Configuration

Key constants in `agent_pool.py`:

| Constant | Default | Description |
|---|---|---|
| `POOL_SIZE` | 3 | Number of warm agent sandboxes to maintain |
| `SANDBOX_TIMEOUT_SECONDS` | 1800 (30 min) | Max lifetime per sandbox |
| `MIN_REMAINING_SECONDS` | 300 (5 min) | Minimum time left for a sandbox to be considered usable |
| `POOL_MAINTENANCE_SCHEDULE` | 1 min | How often scheduled maintenance runs |

## Files

| File | Description |
|---|---|
| `agent_worker.py` | LiveKit voice agent — runs inside sandboxes |
| `dispatcher.py` | Modal app that launches avatar runner subprocesses |
| `agent_pool.py` | Modal app that manages the warm sandbox pool |
| `avatar_runner.py` | Connects to a room and generates audio-wave video |
| `wave_viz.py` | Waveform visualization renderer |
