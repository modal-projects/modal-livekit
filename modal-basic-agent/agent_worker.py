import asyncio
import logging
import os

import httpx
from livekit.agents import AgentServer, JobContext, cli

logger = logging.getLogger("minimal-worker")
logger.setLevel(logging.INFO)

server = AgentServer()

SANDBOX_ID = os.environ.get("SANDBOX_ID")
POOL_REPLENISH_URL = os.environ.get("POOL_REPLENISH_URL")
POOL_ACTIVATE_URL = os.environ.get("POOL_ACTIVATE_URL")
POOL_DEACTIVATE_URL = os.environ.get("POOL_DEACTIVATE_URL")


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    if POOL_ACTIVATE_URL and SANDBOX_ID:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(POOL_ACTIVATE_URL, params={"sandbox_id": SANDBOX_ID})
                logger.info("Sandbox activated")
        except Exception:
            logger.warning("Failed to activate sandbox", exc_info=True)

    async def on_shutdown():
        if POOL_DEACTIVATE_URL and SANDBOX_ID:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        POOL_DEACTIVATE_URL, params={"sandbox_id": SANDBOX_ID}
                    )
                    logger.info("Sandbox deactivated")
            except Exception:
                logger.warning("Failed to deactivate sandbox", exc_info=True)

    ctx.add_shutdown_callback(on_shutdown)

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
    logger.info(f"Connected to room {ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(server)
