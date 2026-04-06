"""
Sandbox pool for the browser agent.

Maintains warm sandboxes running a browser-capture agent that opens
a web page and publishes its content to a LiveKit room.

Usage:
    python -m modal-browser-agent.agent_pool deploy
    python -m modal-browser-agent.agent_pool check
    python -m modal-browser-agent.agent_pool maintain
"""

from pathlib import Path

import modal

from shared.sandbox_pool import PoolConfig, create_pool_app

THIS_DIR = Path(__file__).parent.absolute()

sandbox_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(
        "livekit-agents~=1.4",
        "livekit-plugins-browser",
    )
    .run_commands("playwright install --with-deps chromium")
    .add_local_dir(str(THIS_DIR), remote_path="/app")
)

config = PoolConfig(
    app_name="browser-agent-pool",
    sandbox_image=sandbox_image,
)

app, run_cli = create_pool_app(config)

if __name__ == "__main__":
    run_cli()
