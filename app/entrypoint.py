
from livekit.agents import JobContext, WorkerOptions, cli, Agent, AgentSession
from livekit.plugins import silero, groq, cartesia
from livekit.agents import AgentServer
from livekit.agents.llm import FunctionTool, RawFunctionTool, ProviderTool

from app.models.user import SalonUserData
from app.agent.assistant import Assistant
from app.agent.prompts import INSTRUCTIONS
from app.core.config import settings
from dotenv import load_dotenv

server = AgentServer()

load_dotenv()



@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """
    LiveKit Agent entrypoint.
    
    Handles voice interactions for salon appointment booking.
    All data operations go through the FastAPI backend.
    """
    await ctx.connect()
    
    # Initialize user session data
    userdata = SalonUserData()
    assistant_instance = Assistant(session=userdata, ctx=ctx)
    
    # available tools for the agent
    tools: list[FunctionTool | RawFunctionTool | ProviderTool] = [
    assistant_instance.get_current_date_and_time,
    assistant_instance.modify_booking_detail,
    assistant_instance.get_booking_summary,
    assistant_instance.get_salon_information,
    assistant_instance.check_availability,
    assistant_instance.request_help,
    assistant_instance.collect_customer_information,
    assistant_instance.select_service,
    assistant_instance.schedule_appointment,
    assistant_instance.confirm_booking,
]

    # Create the agent
    agent = Agent(
        instructions=INSTRUCTIONS,
        tools=tools,
    )

    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        vad = silero.VAD.load()
        ctx.proc.userdata["vad"] = vad


    session = AgentSession(
        vad=vad,
        stt=groq.STT(
            model=settings.stt,
            language="en"
        ),
        llm=groq.LLM(
            model=settings.llm,
            temperature=0.5,
        ),
        tts=cartesia.TTS()
    )
    
    # Start the session
    await session.start(agent=agent, room=ctx.room)
    
    # Generate initial greeting
    await session.generate_reply(
        instructions="ask how you can help them today."
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        ),
    )