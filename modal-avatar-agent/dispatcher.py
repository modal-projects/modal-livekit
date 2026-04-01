import asyncio
import logging
import os
import sys
from pathlib import Path

import modal
from pydantic import BaseModel

app = modal.App(name="avatar-dispatcher")
image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "livekit-agents[openai,silero,deepgram,cartesia,turn-detector]~=1.4",
        "opencv-python",
        "fastapi[standard]",
        "pydantic",
    )
)

logger = logging.getLogger("avatar-dispatcher")
logging.basicConfig(level=logging.INFO)

THIS_DIR = Path(__file__).parent.absolute()


@app.cls(
    image=image,
    gpu="A100-40GB",
    cpu=2.0,
    memory=1024,
    secrets=[modal.Secret.from_name("livekit-agent")],
    min_containers=3,
    buffer_containers=3,
    region="us-west",
)
class AvatarDispatcher:

    @modal.method()
    async def launch(self, room_name: str, url: str, token: str) -> None:
        """Launch an avatar worker subprocess and block until it completes."""
        cmd = [sys.executable, str(THIS_DIR / "avatar_runner.py")]
        env = os.environ.copy()
        env["LIVEKIT_URL"] = url
        env["LIVEKIT_TOKEN"] = token
        env["LIVEKIT_ROOM"] = room_name

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=sys.stdout, stderr=sys.stderr, env=env
            )
            logger.info(f"Launched avatar worker for room: {room_name}")
            returncode = await proc.wait()
            logger.info(f"Avatar worker for room {room_name} exited with code {returncode}")
        except Exception:
            logger.exception(f"Avatar worker for room {room_name} failed")
            raise


class LaunchRequest(BaseModel):
    room_name: str
    url: str
    token: str


@app.function(
    image=image,
    region="us-east",
    min_containers=1
)
@modal.concurrent(max_inputs=1000)
@modal.fastapi_endpoint(method="POST")
async def launch_avatar(req: LaunchRequest):
    """HTTP endpoint that spawns an avatar worker and returns immediately."""
    await AvatarDispatcher().launch.spawn.aio(room_name=req.room_name, url=req.url, token=req.token)
    return {"status": "launched", "room_name": req.room_name}
