"""
Sandbox pool that maintains warm agent workers connected to LiveKit.

Each sandbox runs `agent_worker.py start`, which connects to LiveKit via WebSocket
and waits for job dispatch. LiveKit assigns jobs to available agents — we just need
to keep enough idle agents in the pool.

Replenishment works two ways:
  1. **Immediate**: When an agent's entrypoint fires (job assigned), it calls
     `add_sandbox_to_queue.spawn()` to create a replacement right away.
  2. **Scheduled**: `maintain_pool` runs periodically to clean up dead/expired
     sandboxes and top up the pool as a safety net.

Adapted from https://modal.com/docs/examples/sandbox_pool

Usage:
    python agent_pool.py deploy    # Deploy app and run initial pool maintenance
    python agent_pool.py check     # Show current pool status
    python agent_pool.py maintain  # Manually trigger pool maintenance
"""

import argparse
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("avatar-agent-pool")

THIS_DIR = Path(__file__).parent.absolute()

sandbox_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(
        "livekit-agents[openai,silero,deepgram,cartesia,turn-detector]~=1.4",
    )
    .add_local_dir(str(THIS_DIR), remote_path="/app")
)

# Pool configuration
POOL_SIZE = 3
SANDBOX_TIMEOUT_SECONDS = 30 * 60  # 30 minutes
MIN_REMAINING_SECONDS = 5 * 60  # need at least 5 min left to be useful
POOL_MAINTENANCE_SCHEDULE = modal.Period(minutes=1)

pool_queue = modal.Queue.from_name(
    "avatar-agent-pool-queue", create_if_missing=True
)

image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(
        "fastapi[standard]",
    )
)

@dataclass
class SandboxReference:
    id: str
    expires_at: int


def is_still_good(sr: SandboxReference) -> bool:
    """Check if a sandbox is still running with enough time remaining."""
    if sr.expires_at < time.time() + MIN_REMAINING_SECONDS:
        return False
    try:
        sb = modal.Sandbox.from_id(sr.id)
        return sb.poll() is None
    except Exception:
        return False


@app.function(
    retries=3,
    region="us-east",
    min_containers=1,
)
@modal.concurrent(max_inputs=20)
def add_sandbox_to_queue() -> None:
    sandbox_app = modal.App.lookup(
        "avatar-agent-pool-sandboxes", create_if_missing=True
    )

    sb = modal.Sandbox.create(
        "python", "agent_worker.py", "start",
        app=sandbox_app,
        image=sandbox_image,
        workdir="/app",
        secrets=[modal.Secret.from_name("livekit-agent")],
        timeout=SANDBOX_TIMEOUT_SECONDS,
        region="us-west",
    )
    expires_at = int(time.time()) + SANDBOX_TIMEOUT_SECONDS

    time.sleep(5)
    if sb.poll() is not None:
        raise Exception("Agent worker sandbox failed to start")

    pool_queue.put(SandboxReference(id=sb.object_id, expires_at=expires_at))
    sb.detach()


@app.function(
    image=image,
    region="us-east",
)
@modal.concurrent(max_inputs=1000)
@modal.fastapi_endpoint(method="POST")
def replenish():
    """HTTP endpoint that triggers creation of a new sandbox."""
    add_sandbox_to_queue.spawn()
    return {"status": "replenishing"}


@app.function()
def terminate_sandboxes(sandbox_ids: list[str]) -> int:
    num_terminated = 0
    for sid in sandbox_ids:
        try:
            sb = modal.Sandbox.from_id(sid)
            sb.terminate()
            sb.detach()
            num_terminated += 1
        except Exception:
            pass
    print(f"Terminated {num_terminated} sandboxes")
    return num_terminated


@app.function(schedule=POOL_MAINTENANCE_SCHEDULE)
def maintain_pool():
    to_terminate: list[str] = []
    good_sandboxes: list[SandboxReference] = []

    while True:
        sr = pool_queue.get(block=False)
        if sr is None:
            break
        if is_still_good(sr):
            good_sandboxes.append(sr)
        else:
            to_terminate.append(sr.id)

    for sr in good_sandboxes:
        pool_queue.put(sr)

    if to_terminate:
        print(f"Removing {len(to_terminate)} dead/expiring sandboxes")
        terminate_sandboxes.spawn(to_terminate)

    current_size = len(good_sandboxes)
    diff = POOL_SIZE - current_size

    if diff > 0:
        print(f"Pool: {current_size}/{POOL_SIZE}, adding {diff}")
        for _ in add_sandbox_to_queue.starmap(() for _ in range(diff)):
            pass
    elif diff < 0:
        print(f"Pool: {current_size}/{POOL_SIZE}, removing {-diff}")
        excess = []
        for _ in range(-diff):
            sr = pool_queue.get(block=False)
            if sr:
                excess.append(sr.id)
        if excess:
            terminate_sandboxes.spawn(excess)

    print(f"Pool maintenance complete. Target: {POOL_SIZE}")


# -- Local CLI commands --


def deploy():
    print("Deploying the agent pool...")
    app.deploy()
    print("Done.")

    print("\nRunning initial pool maintenance...")
    maintain_pool.remote()
    print("Done.")


def check():
    count = pool_queue.len()
    print(f"Sandboxes in queue: {count}")

    for sr in pool_queue.iterate():
        seconds_left = sr.expires_at - time.time()
        expires_str = datetime.fromtimestamp(sr.expires_at).isoformat()
        status = "alive" if is_still_good(sr) else "dead/expiring"
        print(
            f"  Sandbox '{sr.id}': {status}, "
            f"expires {expires_str} ({int(seconds_left)}s remaining)"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage agent worker sandbox pool")
    parser.add_argument(
        "command",
        choices=["deploy", "check", "maintain"],
        help="Command to execute",
    )
    args = parser.parse_args()

    if args.command == "deploy":
        deploy()
    elif args.command == "check":
        check()
    elif args.command == "maintain":
        maintain_pool.remote()
