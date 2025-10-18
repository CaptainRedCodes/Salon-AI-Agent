"""
LiveKit Voice Agent - Hair Salon Receptionist (Production)
===========================================================
Production-ready voice agent with Firebase integration for help request management.
"""

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RunContext,
    cli,
    metrics,
)
from livekit.agents.llm import function_tool
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from datetime import datetime
import logging

from booking_manager import BookingManager
from db import FirebaseManager
from helper import HelpRequestManager


load_dotenv("../.env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


#saloonAssistant
class Assistant(Agent):
    """Production-ready voice assistant for a hair salon."""

    def __init__(self, job_context: JobContext):
        # Store job context for use in tools
        self.job_context = job_context
        
        self.service_prices = {
            "haircut": 40,
            "hair coloring": 80,
            "highlights": 120,
            "blow dry": 30,
            "hair treatment": 60
        }
        
        self.help_manager = HelpRequestManager()
        self.booking_manager = BookingManager()
        
        services_text = "\n".join([
            f"- {service.title()}: ${price}"
            for service, price in self.service_prices.items()
        ])
        
        instructions = f"""You are a friendly and professional receptionist at Hair Salon.

                        OUR SERVICES AND PRICES:
                        {services_text}

                        YOUR RESPONSIBILITIES:
                        1. Greet callers warmly and professionally
                        2. Answer questions about our services, prices, and policies
                        3. Check availability and book appointments
                        4. Collect necessary information: name, service, date, time
                        5. If you don't know something or need human assistance, use the request_help tool immediately

                        IMPORTANT GUIDELINES:
                        - Be conversational and natural in your responses
                        - Confirm all booking details before finalizing
                        - Always provide the confirmation number after booking
                        - If a caller asks about something you're unsure about, request help rather than guessing
                        - Keep responses concise and to the point
                        - Use the get_current_date_and_time tool when you need to know today's date
                        - Once Booking is confirmed thank the User.

                        TONE: Friendly, professional, and helpful"""

        super().__init__(instructions=instructions)
        
        logger.info("SalonAssistant initialized successfully")


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
    ) -> str:
        """
        Book a salon appointment.
        
        Args:
            customer_name: Full name of the customer
            service: Type of service requested
            appointment_date: Date of appointment (e.g., "January 15, 2025")
            appointment_time: Time of appointment (e.g., "2:00 PM")
        """
        try:
            service_lower = service.lower()
            price = self.service_prices.get(service_lower)
            
            if price is None:
                available_services = ", ".join([s.title() for s in self.service_prices.keys()])
                return (f"I'm sorry, '{service}' is not a recognized service. "
                       f"Our services are: {available_services}. "
                       f"Which one would you like to book?")
            
            # Create booking in Firebase
            booking = await self.booking_manager.create_booking(
                customer_name=customer_name,
                service=service,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                price=price,
            )
            
            # Format confirmation message
            result = f"Perfect! Your appointment is confirmed.\n\n"
            result += f"Confirmation Number: {booking['confirmation_number']}\n"
            result += f"Customer: {booking['customer_name']}\n"
            result += f"Service: {booking['service']} (${booking['price']})\n"
            result += f"Date: {booking['appointment_date']}\n"
            result += f"Time: {booking['appointment_time']}\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Booking failed: {e}")
            return ("I apologize, but I'm having trouble completing your booking right now. "
                   "Let me get assistance from my supervisor to help you with this.")

    @function_tool
    async def check_availability(
        self, 
        context: RunContext, 
        date: str,
        time: str = ""
    ) -> str:
        """
        Check if appointment slots are available.

        Args:
            date: Date to check (e.g., "January 15, 2025")
            time: Specific time to check (optional, e.g., "2:00 PM")
        """
        try:
            existing_bookings = await self.booking_manager.get_bookings_by_date(date)
            booked_times = [booking['appointment_time'] for booking in existing_bookings]
            
            all_slots = [
                "9:00 AM", "10:00 AM", "11:00 AM", 
                "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM"
            ]
            
            # Calculate available times
            available_times = [slot for slot in all_slots if slot not in booked_times]
            
            if time:
                # Check specific time
                if time in available_times:
                    return f"Great news! {time} on {date} is available. Would you like to book this time?"
                elif time in booked_times:
                    return f"I'm sorry, {time} on {date} is already booked. Available times are: {', '.join(available_times)}"
                else:
                    return f"{time} is outside our business hours. Our available times on {date} are: {', '.join(available_times)}"
            else:
                if available_times:
                    return f"Available appointment times on {date}:\n" + "\n".join(f"• {t}" for t in available_times)
                else:
                    return f"Unfortunately, we're fully booked on {date}. Would you like to check another date?"
                    
        except Exception as e:
            logger.error(f"Availability check failed: {e}")
            return "I'm having trouble checking availability. Let me get help from my supervisor."

    @function_tool
    async def request_help(
        self, 
        context: RunContext,  # Changed from JobContext to RunContext
        reason: str
    ) -> str:
        """
        Request human assistance when you don't know the answer or need supervisor help.

        Args:
            reason: Brief explanation of why help is needed (what the customer is asking about)
        """
        try:
            # Access JobContext from self
            room_name = self.job_context.room.name if self.job_context and self.job_context.room else None
            
            customer_context = {
                "timestamp": datetime.now().isoformat(),
                "room_name": room_name,
            }
            
            # Create help request in Firebase
            request_id = await self.help_manager.create_help_request(
                reason=reason,
                room_name=room_name,
                customer_context=customer_context
            )
            
            logger.info(f"########### Help request created: {request_id} #######")
            
            # Return customer-facing message
            return (f"Let me check with my supervisor about that and get back to you. "
                   f"I've noted your question: '{reason}'. "
                   f"Please hold for just a moment while I get the information you need.")
            
        except Exception as e:
            logger.error(f"Failed to create help request: {e}")
            return ("I apologize, but I'm having a technical issue. "
                   "Could you please call back in a few minutes, or I can have a supervisor call you back?")
        

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """Entry point for the agent with production configuration."""
    
    try:
        logger.info(f"Starting agent session for room: {ctx.room.name}")
        ctx.log_context_fields = {
            "room": ctx.room.name
        }
        
        # Configure the voice pipeline
        session = AgentSession(
            stt="assemblyai/universal-streaming:en",
            llm="google/gemini-2.0-flash",           
            tts="cartesia",
            turn_detection=MultilingualModel(),                       
            vad=ctx.proc.userdata["vad"],
            preemptive_generation=True
        )                   
        
        usage_collector = metrics.UsageCollector()

        @session.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics)
            usage_collector.collect(ev.metrics)

        async def log_usage():
            summary = usage_collector.get_summary()
            logger.info(f"Usage: {summary}")

        ctx.add_shutdown_callback(log_usage)
        
        # Start the session - pass ctx to Assistant
        await session.start(
            room=ctx.room,
            agent=Assistant(ctx)  # Pass JobContext here
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
    # Run the agent with production settings
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        )
    )