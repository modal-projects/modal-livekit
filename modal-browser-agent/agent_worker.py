import asyncio
import logging
import os

import httpx
from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli
from livekit.plugins.browser import BrowserContext, BrowserSession

logger = logging.getLogger("browser-agent")
logger.setLevel(logging.INFO)

server = AgentServer()

SANDBOX_ID = os.environ.get("SANDBOX_ID")
POOL_REPLENISH_URL = os.environ.get("POOL_REPLENISH_URL")
POOL_ACTIVATE_URL = os.environ.get("POOL_ACTIVATE_URL")
POOL_DEACTIVATE_URL = os.environ.get("POOL_DEACTIVATE_URL")


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
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

    browser_ctx = BrowserContext(dev_mode=False)
    await browser_ctx.initialize()

    page = await browser_ctx.new_page(
        url="https://news.ycombinator.com",
        width=1280,
        height=720,
        framerate=30,
    )

    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_NONE)

    session = BrowserSession(page=page, room=ctx.room)
    await session.start()

    async def cleanup():
        await session.aclose()
        await page.aclose()
        await browser_ctx.aclose()

    ctx.add_shutdown_callback(cleanup)


if __name__ == "__main__":
    cli.run_app(server)
