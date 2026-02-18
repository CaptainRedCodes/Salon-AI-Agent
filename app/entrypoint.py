from dotenv import load_dotenv

from livekit.agents import JobContext, WorkerOptions, cli, AgentSession
from livekit.plugins import silero, groq, cartesia
from livekit.plugins.turn_detector.english import EnglishModel

from app.models.user import SalonUserData
from app.agent.assistant import Assistant
from app.core.config import settings

load_dotenv()


async def entrypoint(ctx: JobContext):
    """
    LiveKit Agent entrypoint.

    Handles voice interactions for salon appointment booking.
    All data operations go through the FastAPI backend.
    """
    await ctx.connect()

    # VAD: reuse across sessions if already loaded in this worker process
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        vad = silero.VAD.load()
        ctx.proc.userdata["vad"] = vad

    # Per-session user state — passed as userdata so every tool can access it via context.userdata inside RunContext
    userdata = SalonUserData()

    session = AgentSession[SalonUserData](
        userdata=userdata,
        vad=vad,
        stt=groq.STT(
            model=settings.stt,
            language="en",
        ),
        llm=groq.LLM(
            model=settings.llm,
            temperature=0.5,
        ),
        tts=cartesia.TTS(),
        turn_detection=EnglishModel(),
        preemptive_generation=True,
    )

    await session.start(
        agent=Assistant(),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        ),
    )