"""
Sandbox pool for the avatar agent.

Maintains warm agent workers connected to LiveKit, each capable of
launching an avatar via the dispatcher when a job is assigned.

Usage:
    python -m modal-avatar-agent.agent_pool deploy
    python -m modal-avatar-agent.agent_pool check
    python -m modal-avatar-agent.agent_pool maintain
"""

from pathlib import Path

import modal

from shared.agent_pool import PoolConfig, create_pool_app

THIS_DIR = Path(__file__).parent.absolute()

sandbox_image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_pip_install(
        "livekit-agents[openai,silero,deepgram,cartesia,turn-detector]~=1.4",
    )
    .add_local_dir(str(THIS_DIR), remote_path="/app")
)


def get_extra_sandbox_env() -> dict[str, str]:
    """Look up the avatar dispatcher URL at sandbox creation time."""
    dispatcher = modal.Cls.from_name("avatar-dispatcher", "AvatarDispatcher")()
    return {"AVATAR_DISPATCHER_URL": dispatcher.launch_avatar_api.get_web_url()}


config = PoolConfig(
    app_name="avatar-agent-pool",
    sandbox_image=sandbox_image,
)

app, run_cli = create_pool_app(config, sandbox_env_setup=get_extra_sandbox_env)

if __name__ == "__main__":
    run_cli()
