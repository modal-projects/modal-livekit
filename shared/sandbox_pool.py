"""
Reusable sandbox pool for maintaining warm LiveKit agent workers on Modal.

Each sandbox runs an agent worker that connects to LiveKit via WebSocket
and waits for job dispatch. LiveKit assigns jobs to available agents —
the pool just ensures enough idle agents are connected.

Lifecycle:
  - Sandboxes are created idle and placed in the pool.
  - When a job is dispatched, the agent worker calls ``activate`` to mark
    the sandbox as active (incrementing its active-call count).
  - When the job ends, the worker calls ``deactivate`` (decrementing).
  - ``maintain_pool`` never terminates active sandboxes. It only removes
    dead sandboxes and trims excess idle ones.

Replenishment works two ways:
  1. **Immediate**: When an agent takes a job, it POSTs to the pool's
     replenish endpoint to create a replacement right away.
  2. **Scheduled**: ``maintain_pool`` runs periodically as a safety net.

Adapted from https://modal.com/docs/examples/sandbox_pool

Usage:
    from shared.sandbox_pool import create_pool_app, PoolConfig

    config = PoolConfig(
        app_name="my-agent-pool",
        sandbox_image=my_image,
    )
    app, run_cli, pool_queue, pool_state = create_pool_app(config)

    # Define add_sandbox_to_queue at module level (see examples)

    if __name__ == "__main__":
        run_cli()
"""

import argparse
import asyncio
import time
from typing import Callable

import modal

from dataclasses import dataclass, field


@dataclass
class PoolConfig:
    app_name: str
    sandbox_image: modal.Image
    sandbox_command: list[str] = field(
        default_factory=lambda: [
            "bash", "-c",
            "python agent_worker.py download-files && python agent_worker.py start",
        ]
    )
    sandbox_secrets: list = field(
        default_factory=lambda: [modal.Secret.from_name("livekit-agent")]
    )
    pool_size: int = 3
    sandbox_timeout_seconds: int = 24 * 60 * 60
    min_remaining_seconds: int = 2 * 60 * 60
    maintenance_interval_minutes: int = 1
    sandbox_region: str = "us-west"
    sandbox_workdir: str = "/app"


def create_pool_app(
    config: PoolConfig,
) -> tuple[modal.App, Callable, modal.Queue, modal.Dict]:
    """
    Build a sandbox pool app from configuration.

    This creates the app with all shared infrastructure (endpoints,
    maintenance, CLI) but does NOT define ``add_sandbox_to_queue`` —
    that function must be defined at module level in each example's
    ``agent_pool.py`` because it references a ``modal.Image`` which
    cannot be captured in a serialized closure.

    Returns:
        ``(app, run_cli, pool_queue, pool_state)``
    """
    app = modal.App(config.app_name)

    pool_queue = modal.Queue.from_name(
        f"{config.app_name}-queue", create_if_missing=True
    ).hydrate()
    pool_state = modal.Dict.from_name(
        f"{config.app_name}-state", create_if_missing=True
    ).hydrate()

    fastapi_image = modal.Image.debian_slim(python_version="3.13").uv_pip_install(
        "fastapi[standard]",
    )

    app_name = config.app_name
    min_remaining = config.min_remaining_seconds
    pool_size = config.pool_size

    # -- HTTP endpoints --

    @app.function(name="replenish", serialized=True, image=fastapi_image, region="us-east")
    @modal.concurrent(max_inputs=1000)
    @modal.fastapi_endpoint(method="POST")
    async def replenish():
        modal.Function.from_name(app_name, "add_sandbox_to_queue").spawn()
        return {"status": "replenishing"}

    @app.function(name="activate", serialized=True, image=fastapi_image, region="us-east")
    @modal.concurrent(max_inputs=1000)
    @modal.fastapi_endpoint(method="POST")
    async def activate(sandbox_id: str):
        current = await pool_state.get.aio(sandbox_id)
        if current is None:
            current = 0
        await pool_state.put.aio(sandbox_id, current + 1)
        return {"active_calls": current + 1}

    @app.function(name="deactivate", serialized=True, image=fastapi_image, region="us-east")
    @modal.concurrent(max_inputs=1000)
    @modal.fastapi_endpoint(method="POST")
    async def deactivate(sandbox_id: str):
        current = await pool_state.get.aio(sandbox_id)
        if current is None:
            current = 0
        new_count = max(0, current - 1)
        await pool_state.put.aio(sandbox_id, new_count)
        return {"active_calls": new_count}

    # -- Maintenance --

    @app.function(name="terminate_sandboxes", serialized=True)
    async def terminate_sandboxes(entries: list[dict]) -> int:
        num_terminated = 0
        for entry in entries:
            try:
                sb = modal.Sandbox.from_id(entry["modal_id"])
                await sb.terminate.aio()
                await sb.detach.aio()
                num_terminated += 1
            except Exception:
                pass
            try:
                await pool_state.pop.aio(entry["key"])
            except KeyError:
                pass
        print(f"Terminated {num_terminated} sandboxes")
        return num_terminated

    @app.function(
        name="maintain_pool",
        serialized=True,
        schedule=modal.Period(minutes=config.maintenance_interval_minutes),
    )
    async def maintain_pool():
        now = time.time()
        dead: list[dict] = []
        active_entries: list[dict] = []
        idle_fresh: list[dict] = []
        idle_expiring: list[dict] = []

        while True:
            entry = await pool_queue.get.aio(block=False)
            if entry is None:
                break

            modal_id = entry["modal_id"]
            sandbox_key = entry["key"]

            try:
                sb = modal.Sandbox.from_id(modal_id)
                alive = await sb.poll.aio() is None
            except Exception:
                alive = False

            if not alive:
                dead.append(entry)
                continue

            active_calls = await pool_state.get.aio(sandbox_key)
            if active_calls is None:
                active_calls = 0

            if active_calls > 0:
                active_entries.append(entry)
            else:
                remaining = entry["expires_at"] - now
                if remaining < min_remaining:
                    idle_expiring.append(entry)
                else:
                    idle_fresh.append(entry)

        for entry in active_entries:
            await pool_queue.put.aio(entry)

        keep_idle = idle_fresh[:pool_size]
        excess_idle = idle_fresh[pool_size:]

        for entry in keep_idle:
            await pool_queue.put.aio(entry)

        to_terminate = dead + idle_expiring + excess_idle
        if to_terminate:
            print(
                f"Terminating {len(to_terminate)} sandboxes "
                f"({len(dead)} dead, {len(idle_expiring)} expiring, "
                f"{len(excess_idle)} excess idle)"
            )
            terminate_sandboxes.spawn(to_terminate)

        needed = pool_size - len(keep_idle)
        if needed > 0:
            print(
                f"Pool: {len(keep_idle)} idle, {len(active_entries)} active "
                f"— adding {needed} to reach target {pool_size} idle"
            )
            add_fn = modal.Function.from_name(app_name, "add_sandbox_to_queue")
            async for _ in add_fn.starmap.aio(() for _ in range(needed)):
                pass

        print(
            f"Pool maintenance complete. "
            f"Target: {pool_size} idle. "
            f"Current: {len(keep_idle)} idle, {len(active_entries)} active"
        )

    # -- CLI helpers (run locally) --

    async def deploy():
        print(f"Deploying {app_name}...")
        await app.deploy.aio()
        print("Done.")
        print("\nRunning initial pool maintenance...")
        await maintain_pool.remote.aio()
        print("Done.")

    async def check():
        now = time.time()
        count = await pool_queue.len.aio()
        print(f"Sandboxes tracked: {count}")

        entries: list[dict] = []
        while True:
            entry = await pool_queue.get.aio(block=False)
            if entry is None:
                break
            entries.append(entry)

        for entry in entries:
            await pool_queue.put.aio(entry)

        for entry in entries:
            sandbox_key = entry["key"]
            modal_id = entry["modal_id"]
            remaining = entry["expires_at"] - now
            remaining_hr = remaining / 3600

            try:
                sb = modal.Sandbox.from_id(modal_id)
                alive = await sb.poll.aio() is None
            except Exception:
                alive = False

            active_calls = await pool_state.get.aio(sandbox_key)
            if active_calls is None:
                active_calls = 0

            if not alive:
                status = "dead"
            elif active_calls > 0:
                status = f"active ({active_calls} calls)"
            elif remaining < min_remaining:
                status = "idle (expiring)"
            else:
                status = "idle"

            print(
                f"  {sandbox_key[:8]}... ({modal_id}): {status} "
                f"({remaining_hr:.1f}h remaining)"
            )

    def run_cli():
        parser = argparse.ArgumentParser(
            description=f"Manage {app_name} sandbox pool"
        )
        parser.add_argument(
            "command",
            choices=["deploy", "check", "maintain"],
            help="Command to execute",
        )
        args = parser.parse_args()

        if args.command == "deploy":
            asyncio.run(deploy())
        elif args.command == "check":
            asyncio.run(check())
        elif args.command == "maintain":
            asyncio.run(maintain_pool.remote.aio())

    return app, run_cli, pool_queue, pool_state
