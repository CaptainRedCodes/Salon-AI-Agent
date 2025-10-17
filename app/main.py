"""
LiveKit Voice Agent - Hair Salon Receptionist
==============================================
A simple voice agent for a hair salon that can:
- Answer questions about services
- Book appointments
- Request help when needed
"""

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import openai, deepgram, silero
from datetime import datetime
import os

# Load environment variables
load_dotenv(".env")

class SalonAssistant(Agent):
    """Voice assistant for a hair salon."""

    def __init__(self):

         # Dictionary for booking logic
        self.service_prices = {
            "haircut": 40,
            "hair coloring": 80,
            "highlights": 120,
            "blow dry": 30,
            "hair treatment": 60
        }

        super().__init__(
            instructions=f"""You are a friendly receptionist at Hair Salon.

Our services and prices are:
{self.service_prices}

Your responsibilities:
1. Greet callers warmly
2. Answer questions about our services and prices
3. Book appointments for customers
4. If you don't know something or need human assistance, use the request_help tool

Keep responses natural and conversational. Be helpful and professional."""
        )

       

        # Track bookings [dummy will connect to db later]
        self.bookings = []

    @function_tool
    async def get_current_date_and_time(self, context: RunContext) -> str:
        """Get the current date and time."""
        current_datetime = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return f"The current date and time is {current_datetime}"

    @function_tool
    async def book_appointment(
        self,
        context: RunContext,
        customer_name: str,
        service: str,
        appointment_date: str,
        appointment_time: str,
        phone_number: str = ""
    ) -> str:
        """Book a salon appointment."""

        # Lookup service price
        service_prices = self.service_prices
        service_lower = service.lower()
        price = service_prices.get(service_lower, 0)

        if price == 0:
            return ("I'm sorry, '{0}' is not a recognized service. "
                    "Our services are: Haircut, Hair Coloring, Highlights, Blow Dry, and Hair Treatment."
                    ).format(service)

        # Create booking
        booking = {
            "confirmation_number": f"SA{len(self.bookings) + 1001}",
            "customer_name": customer_name,
            "service": service,
            "date": appointment_date,
            "time": appointment_time,
            "phone": phone_number,
            "price": price
        }

        self.bookings.append(booking)

        result = f"✓ Appointment confirmed!\n\n"
        result += f"Confirmation #: {booking['confirmation_number']}\n"
        result += f"Customer: {booking['customer_name']}\n"
        result += f"Service: {booking['service']} (${booking['price']})\n"
        result += f"Date: {booking['date']}\n"
        result += f"Time: {booking['time']}\n"
        if phone_number:
            result += f"Phone: {booking['phone']}\n"
        result += "\nWe'll see you then! Please arrive 5 minutes early."

        return result


    @function_tool
    async def check_availability(
        self, 
        context: RunContext, 
        date: str,
        time: str = ""
    ) -> str:
        """Check if appointment slots are available.

        Args:
            date: Date to check (e.g., 'January 15, 2025')
            time: Specific time to check (optional, e.g., '2:00 PM')
        """
        # Simple mock availability
        available_times = [
            "9:00 AM", "10:00 AM", "11:00 AM", 
            "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM"
        ]
        
        if time:
            # Check specific time
            is_available = time in available_times
            if is_available:
                return f"Yes, {time} on {date} is available!"
            else:
                return f"Sorry, {time} on {date} is not available. Available times are: {', '.join(available_times)}"
        else:
            # Show all available times
            return f"Available appointment times on {date}:\n" + "\n".join(f"- {t}" for t in available_times)

    @function_tool
    async def request_help(
        self, 
        context: RunContext, 
        reason: str
    ) -> str:
        """Request human assistance when you don't know the answer.

        Args:
            reason: Brief explanation of why help is needed
        """
        #right now its dummy        
        return f"I've notified our staff about your inquiry: '{reason}'. Someone will assist you shortly. Please hold for just a moment."


async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Configure the voice pipeline with the essentials
    session = AgentSession(
        stt="assemblyai/universal-streaming:en",
        llm="google/gemini-2.0-flash",
        tts="cartesia",
        vad=silero.VAD.load(),
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=SalonAssistant()
    )

    # Generate initial greeting
    await session.generate_reply(
        instructions="Greet the user warmly and ask how you can help."
    )

if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))