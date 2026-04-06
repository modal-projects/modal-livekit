# Modal Avatar Agent

A LiveKit voice agent with an audio-wave avatar, deployed on Modal. Uses
OpenAI's Realtime API for conversation and renders a waveform visualization
synced to the agent's speech.

## Architecture

This example has an additional component beyond the standard sandbox pool — the
**Avatar Dispatcher**, which runs the video renderer on a GPU:

```
┌─────────────────────┐       HTTP POST        ┌─────────────────────┐
│   Agent Worker      │ ───────────────────────▶│  Avatar Dispatcher  │
│   (Sandbox Pool)    │  "launch avatar for     │  (Modal Cls, GPU)   │
│                     │   this room"            │                     │
│  Voice agent with   │                         │  Runs avatar_       │
│  OpenAI Realtime    │                         │  runner.py as       │
│                     │                         │  subprocess          │
└─────────────────────┘                         └─────────────────────┘
```

- **Agent Worker** (`agent_worker.py`): Runs inside sandboxes. When a job
  arrives, it starts an OpenAI Realtime voice session and launches the avatar
  via the dispatcher. TTS audio is streamed to the avatar identity using
  `DataStreamAudioOutput`.

- **Avatar Dispatcher** (`dispatcher.py`): A Modal `Cls` on an A100 GPU.
  Launches `avatar_runner.py` as a subprocess and blocks until the session ends.
  The pool manager looks up its URL automatically at sandbox creation time.

- **Avatar Runner** (`avatar_runner.py`): Joins the room, subscribes to the
  agent's TTS audio stream, and publishes FFT waveform video frames. Uses
  `wave_viz.py` for rendering.

## Deploy

The dispatcher must be deployed **before** the pool (the pool looks up its URL):

```bash
# 1. Deploy the avatar dispatcher
modal deploy modal-avatar-agent/dispatcher.py

# 2. Deploy the agent pool
python modal-avatar-agent/agent_pool.py deploy
```

## What It Does

When a room is created and LiveKit dispatches a job, the agent:

1. Marks itself as active and triggers pool replenishment
2. Starts an OpenAI Realtime voice session
3. POSTs to the dispatcher to launch the avatar renderer on a GPU
4. Streams TTS audio to the avatar, which publishes waveform video to the room

## Files

| File | Description |
|---|---|
| `agent_worker.py` | Voice agent with OpenAI Realtime — runs inside sandboxes |
| `agent_pool.py` | Pool configuration and deployment CLI |
| `dispatcher.py` | Modal app that launches avatar runner on GPU |
| `avatar_runner.py` | Joins a room and generates audio-wave video frames |
| `wave_viz.py` | FFT-based waveform visualization renderer |
