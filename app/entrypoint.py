
from dotenv import load_dotenv
from livekit.agents import (
    JobContext,
    JobProcess,
    AgentSession,
    MetricsCollectedEvent,
    metrics
)
from livekit import agents
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import logging
import asyncio

from .agent import Assistant, SalonUserData

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """Entry point for the agent with production configuration."""
    
    try:
        logger.info(f"Starting agent session for room: {ctx.room.name}")
        ctx.log_context_fields = {
            "room": ctx.room.name
        }
        
        session = AgentSession(
            stt="assemblyai/universal-streaming:en",
            llm="google/gemini-2.0-flash",
            tts="cartesia",
            turn_detection=MultilingualModel(),                       
            vad=ctx.proc.userdata["vad"],
            preemptive_generation=True
        )                   
        
        session.userdata = SalonUserData()
        usage_collector = metrics.UsageCollector()

        @session.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics)
            usage_collector.collect(ev.metrics)

        async def log_usage():
            summary = usage_collector.get_summary()
            logger.info(f"Usage: {summary}")

        ctx.add_shutdown_callback(log_usage)
        
        # Start the session
        await session.start(
            room=ctx.room,
            agent=Assistant(ctx)
        )
        
        # Generate initial greeting
        await session.generate_reply(
            instructions="Greet the caller warmly and ask how you can help them today."
        )
        await ctx.connect()
        
        logger.info("Agent session started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start agent session: {e}")
        raise


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            initialize_process_timeout=120
        )
    )