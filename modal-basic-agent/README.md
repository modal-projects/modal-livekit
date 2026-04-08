# Modal Basic Agent

A minimal LiveKit agent deployed on Modal. Connects to a room and logs — useful
as a starting point or for verifying the sandbox pool lifecycle.

## Deploy

```bash
python -m modal-basic-agent.agent_pool deploy
```

This deploys the pool manager and creates the initial set of warm sandboxes.

## What It Does

When a room is created and LiveKit dispatches a job, the agent:

1. Marks itself as active and triggers pool replenishment
2. Connects to the room
3. Logs "Connected to room \<name\>"

That's it — no LLM, no audio, no video. Add your own agent logic to
`agent_worker.py` to build from here.

## Files

| File | Description |
|---|---|
| `agent_worker.py` | The agent entrypoint — runs inside sandboxes |
| `agent_pool.py` | Pool configuration and deployment CLI |
