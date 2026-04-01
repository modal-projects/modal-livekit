import logging
import asyncio
import httpx
import os

from livekit import api, rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.agents.voice.avatar import DataStreamAudioOutput
from livekit.agents.voice.io import PlaybackFinishedEvent
from livekit.agents.voice.room_io import ATTRIBUTE_PUBLISH_ON_BEHALF
from livekit.plugins import openai

logger = logging.getLogger("avatar-example")
logger.setLevel(logging.INFO)

server = AgentServer()
AVATAR_IDENTITY = "avatar_worker"

POOL_REPLENISH_URL = os.environ.get("POOL_REPLENISH_URL")
AVATAR_DISPATCHER_URL = os.environ.get("AVATAR_DISPATCHER_URL")

async def launch_avatar(ctx: JobContext, avatar_identity: str) -> None:
    """Send HTTP request to the avatar dispatcher to launch an avatar worker."""
    token = (
        api.AccessToken()
        .with_identity(avatar_identity)
        .with_name("Avatar Runner")
        .with_grants(api.VideoGrants(room_join=True, room=ctx.room.name))
        .with_kind("agent")
        .with_attributes({ATTRIBUTE_PUBLISH_ON_BEHALF: ctx.local_participant_identity})
        .to_jwt()
    )

    logger.info("Sending launch request to avatar dispatcher")
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            AVATAR_DISPATCHER_URL,
            json={"room_name": ctx.room.name, "url": ctx._info.url, "token": token},
        )
        response.raise_for_status()
    logger.info("Avatar worker finished")


async def entrypoint(ctx: JobContext):
    
    if POOL_REPLENISH_URL:
        async def replenish():
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(POOL_REPLENISH_URL)
                    logger.info("Pool replenishment triggered")
            except Exception:
                logger.warning("Failed to trigger pool replenishment", exc_info=True)
        asyncio.create_task(replenish())

    await ctx.connect()

    agent = Agent(instructions="Talk to me!")
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(),
        resume_false_interruption=False,
    )

    asyncio.create_task(launch_avatar(ctx, AVATAR_IDENTITY))
    session.output.audio = DataStreamAudioOutput(
        ctx.room,
        destination_identity=AVATAR_IDENTITY,
        wait_remote_track=rtc.TrackKind.KIND_VIDEO,
    )

    await session.start(
        agent=agent,
        room=ctx.room,
    )

    @session.output.audio.on("playback_finished")
    def on_playback_finished(ev: PlaybackFinishedEvent) -> None:
        logger.info(
            "playback_finished",
            extra={
                "playback_position": ev.playback_position,
                "interrupted": ev.interrupted,
            },
        )


if __name__ == "__main__":
    server.rtc_session(entrypoint)
    cli.run_app(server)
