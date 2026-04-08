"""
Sandbox pool for the minimal agent worker.

Usage:
    python -m modal-basic-agent.agent_pool deploy
    python -m modal-basic-agent.agent_pool check
    python -m modal-basic-agent.agent_pool maintain
"""

import asyncio
import time
import uuid
from pathlib import Path

import modal

from shared.sandbox_pool import PoolConfig, create_pool_app

THIS_DIR = Path(__file__).parent.absolute()

sandbox_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install("livekit-agents~=1.4")
    .add_local_dir(str(THIS_DIR), remote_path="/app")
)

shared_image = modal.Image.debian_slim(python_version="3.13").add_local_python_source("shared")

config = PoolConfig(
    app_name="basic-agent-pool",
    sandbox_image=sandbox_image,
)

app, run_cli, pool_queue, pool_state = create_pool_app(config)


@app.function(image=shared_image, retries=3, region="us-east", min_containers=1)
@modal.concurrent(max_inputs=20)
async def add_sandbox_to_queue() -> None:
    sandbox_app = modal.App.lookup(
        f"{config.app_name}-sandboxes", create_if_missing=True
    )

    sandbox_key = str(uuid.uuid4())

    env = {
        "SANDBOX_ID": sandbox_key,
        "POOL_REPLENISH_URL": await modal.Function.from_name(config.app_name, "replenish").get_web_url.aio(),
        "POOL_ACTIVATE_URL": await modal.Function.from_name(config.app_name, "activate").get_web_url.aio(),
        "POOL_DEACTIVATE_URL": await modal.Function.from_name(config.app_name, "deactivate").get_web_url.aio(),
    }

    sb = await modal.Sandbox.create.aio(
        *config.sandbox_command,
        app=sandbox_app,
        image=sandbox_image,
        workdir=config.sandbox_workdir,
        secrets=config.sandbox_secrets,
        timeout=config.sandbox_timeout_seconds,
        region=config.sandbox_region,
        env=env,
    )

    await asyncio.sleep(5)
    if sb.poll() is not None:
        raise Exception("Agent worker sandbox failed to start")

    expires_at = int(time.time()) + config.sandbox_timeout_seconds
    await pool_state.put.aio(sandbox_key, 0)
    await pool_queue.put.aio(
        {"key": sandbox_key, "modal_id": sb.object_id, "expires_at": expires_at}
    )
    sb.detach()


if __name__ == "__main__":
    run_cli()
