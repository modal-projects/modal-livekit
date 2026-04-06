"""
Sandbox pool for the minimal agent worker.

Maintains warm sandboxes that connect to LiveKit and log when
a job is assigned. No dispatcher or avatar — just the bare
agent lifecycle on Modal.

Usage:
    python -m modal-basic-agent.agent_pool deploy
    python -m modal-basic-agent.agent_pool check
    python -m modal-basic-agent.agent_pool maintain
"""

from pathlib import Path

import modal

from shared.sandbox_pool import PoolConfig, create_pool_app

THIS_DIR = Path(__file__).parent.absolute()

sandbox_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install("livekit-agents~=1.4")
    .add_local_dir(str(THIS_DIR), remote_path="/app")
)

config = PoolConfig(
    app_name="basic-agent-pool",
    sandbox_image=sandbox_image,
)

app, run_cli = create_pool_app(config)

if __name__ == "__main__":
    run_cli()
