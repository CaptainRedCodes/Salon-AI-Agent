"""
LiveKit Voice Agent - Hair Salon Receptionist (Production)
===========================================================
Production-ready voice agent with Firebase integration for help request management.
"""

import os
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

from app.knowledge_base import KnowledgeManager
from app.booking_manager import BookingManager
from app.helper import HelpRequestManager
import json
import asyncio

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Assistant(Agent):
    """Production-ready voice assistant for a hair salon."""
    
    def __init__(self, job_context: JobContext):
        # Store job context for use in tools
        self.job_context = job_context

        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Load salon info
        info_path = os.path.join(base_dir, 'json', 'info.json')
        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                self.salon_info = json.load(f)
        except FileNotFoundError:
            print(f"[Error] File not found: {info_path}")
            self.salon_info = {}
        except json.JSONDecodeError as e:
            print(f"[Error] Failed to parse JSON in {info_path}: {e}")
            self.salon_info = {}

        # Load service prices
        price_path = os.path.join(base_dir, 'json', 'price.json')
        try:
            with open(price_path, 'r', encoding='utf-8') as f:
                self.service_prices = json.load(f)
        except FileNotFoundError:
            print(f"[Error] File not found: {price_path}")
            self.service_prices = {}
        except json.JSONDecodeError as e:
            print(f"[Error] Failed to parse JSON in {price_path}: {e}")
            self.service_prices = {}

        self.knowledge_base = KnowledgeManager()
        self.booking_manager = BookingManager()
        self.help_manager = HelpRequestManager()
        
        # Format services with better spacing for natural speech
        services_text = "\n\n".join([
            f"{service.title()}: Price is ${price}"
            for service, price in self.service_prices.items()
        ])
        
        instructions = f"""You are a friendly and professional receptionist at Super Unisex Salon.

        OUR SERVICES AND PRICES:

        {services_text}

        SALON INFORMATION:
        Name: {self.salon_info['name']}
        Address: {self.salon_info['address']}
        Contact: {self.salon_info['contact']}

        Working Hours:
        Monday to Wednesday: 9 AM to 7 PM
        Thursday: Holiday (Closed)
        Friday to Sunday: 9 AM to 7 PM

        YOUR RESPONSIBILITIES:
        1. Greet callers warmly and professionally
        2. Answer questions about our services, prices, and policies using the FAQ above
        3. Check availability and book appointments
        4. Collect necessary information: name, service, date, time, phone number
        5. Handle reasonable, legitimate customer inquiries

        IMPORTANT GUIDELINES:
        - Be conversational and natural in your responses
        - When listing services or prices, pause naturally between each item
        - Check whether the phone number is 10 digits. Confirm with customer if any doubts
        - Confirm all booking details before finalizing
        - Always provide the confirmation number after booking
        - Keep responses concise and to the point
        - Use the get_current_date_and_time tool when you need to know today's date
        - Once booking is confirmed, thank the customer.
        - Not sure about question asked by user, call request help tool

        HANDLING UNUSUAL REQUESTS:
        - If someone asks weird, nonsensical, or clearly unreasonable questions (like "Can I book 100 haircuts?", "Do you cut alien hair?"), politely clarify what they actually need
        - Only use request_help for legitimate questions that aren't covered in the FAQ or knowledge base
        - Do NOT create help tickets for absurd, testing, or joke requests
        - If unsure whether a question is legitimate, try to answer it reasonably first

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
        phone_number: str,
        appointment_date: str,
        appointment_time: str,
    ):
        """
        Book a salon appointment.
        
        Args:
            customer_name: Full name of the customer
            service: Type of service requested
            appointment_date: Date of appointment (e.g., "January 15, 2025")
            appointment_time: Time of appointment (e.g., "2:00 PM")
            phone_number: Customer's phone number
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
                phone_number=phone_number,
                service=service,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                price=price,
            )
            

            confirmation = {
                "confirmation_number": booking["confirmation_number"],
                "customer_name": booking["customer_name"],
                "phone_number": booking["phone_number"],
                "service": booking["service"],
                "price": booking["price"],
                "appointment_date": booking["appointment_date"],
                "appointment_time": booking["appointment_time"],
                "status": "confirmed",
                "message": f"Perfect! Your appointment is confirmed for {booking['service']} on "
                        f"{booking['appointment_date']} at {booking['appointment_time']}."
            }

            
            return confirmation
            
        except Exception as e:
            logger.error(f"Booking failed: {e}")
            return ("I apologize, but I'm having trouble completing your booking right now. "
                   "Let me get assistance from my supervisor to help you with this.")

    @function_tool
    async def check_availability(
        self, context: RunContext, date: str, time: str = ""
    ) -> str:
        """
        Check whether the slot is booked on the given time and date, if not other slots are returned.
        
        Args:
            date: The date to check (e.g., "January 15, 2025")
            time: Optional specific time to check (e.g., "2:00 PM")
        """
        try:
            MAX_BOOKINGS_PER_SLOT = 2
            all_slots = [
                "9:00 AM", "10:00 AM", "11:00 AM", 
                "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM"
            ]

            if time:
                if time not in all_slots:
                    return f"{time} is outside our business hours. Our available times on {date} are: {', '.join(all_slots)}"
                
                count_query = self.booking_manager.db.collection("appointments")\
                    .where("appointment_date", "==", date)\
                    .where("appointment_time", "==", time)\
                    .count()
                
                count_result = count_query.get()
                slot_count = count_result[0].value if count_result else 0

                if slot_count < MAX_BOOKINGS_PER_SLOT:
                    return f"{time} on {date} is available."
                else:
                    available_slots = []
                    for slot in all_slots:
                        c_q = self.booking_manager.db.collection("appointments")\
                            .where("appointment_date", "==", date)\
                            .where("appointment_time", "==", slot)\
                            .count()
                        c_r = c_q.get()
                        if c_r[0].value < MAX_BOOKINGS_PER_SLOT:
                            available_slots.append(slot)

                    if available_slots:
                        return f"{time} is fully booked. Available slots: {', '.join(available_slots)}"
                    else:
                        return f"All slots on {date} are fully booked."

            else:
                available_slots = []
                for slot in all_slots:
                    c_q = self.booking_manager.db.collection("appointments")\
                        .where("appointment_date", "==", date)\
                        .where("appointment_time", "==", slot)\
                        .count()
                    c_r = c_q.get()
                    if c_r[0].value < MAX_BOOKINGS_PER_SLOT:
                        available_slots.append(slot)

                if available_slots:
                    return f"Available appointment times on {date}:\n" + "\n".join(f"• {t}" for t in available_slots)
                else:
                    return f"Unfortunately, we're fully booked on {date}. Would you like to check another date?"

        except Exception as e:
            logger.error(f"Availability check failed: {e}")
            return "I'm having trouble checking availability. Let me get help from my supervisor."


    @function_tool
    async def request_help(
        self, 
        context: RunContext,
        question: str
    ) -> str:
        """
        Request human assistance when the answer isn't available in FAQ or knowledge base.
        Only use this for legitimate customer questions that cannot be answered.
        
        Args:
            question: Customer's legitimate query (string)
        """
        question = question.strip()
        
        # Add detailed logging
        logger.info(f"request_help called with question: {question}")
        
        try:
            question_lower = question.lower()
            
            # Search FAQ first
            faq_answer = None
            try:
                faq_results = self.knowledge_base.search_faq(question_lower)
                if faq_results:
                    faq_answer = faq_results.get('answer')
                    if faq_answer:
                        logger.info(f"Found FAQ answer for: {question}")
                        return faq_answer
            except Exception as e:
                logger.warning(f"FAQ search failed: {e}")

            # Check external Knowledge Base
            try:
                kb_answer = self.knowledge_base.search_knowledge(question_lower)
                if kb_answer:
                    logger.info(f"Found KB answer for: {question}")
                    return kb_answer
            except Exception as e:
                logger.warning(f"KB search failed: {e}")

            # Create help request - only reached if no answer found
            logger.info("No answer found in FAQ/KB, creating help request...")
            
            room_name = None
            if self.job_context and hasattr(self.job_context, 'room') and self.job_context.room:
                room_name = self.job_context.room.name
            
            logger.info(f"Room name: {room_name}")

            customer_context = {
                "timestamp": datetime.now().isoformat(),
                "room_name": room_name,
                "question": question
            }

            request_id = await self.help_manager.create_help_request(
                reason=question,
                room_name=room_name,
                customer_context=customer_context
            )

            logger.info(f"Help request created successfully: {request_id}")

            return (
                f"Let me check with my supervisor about that and get back to you. "
                f"I've noted your question. "
                f"Please hold for a moment while I get the correct information."
            )

        except Exception as e:
            logger.error(f"Failed in request_help: {e}", exc_info=True)
            return (
                "I'm having a technical issue right now. "
                "Please hold on or I can connect you with a supervisor.")

        

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """Entry point for the agent with production configuration."""
    
    try:
        logger.info(f"Starting agent session for room: {ctx.room.name}")
        ctx.log_context_fields = {
            "room": ctx.room.name
        }
        
        # Configure the voice pipeline with proper API keys
        session = AgentSession(
            # Option 1: Use AssemblyAI (requires ASSEMBLYAI_API_KEY in .env)
            stt="assemblyai/universal-streaming:en",
            
            # Option 2: OR use different STT providers (choose one):
            # stt="deepgram/nova-2:en",  # requires DEEPGRAM_API_KEY
            # stt="openai/whisper-1",     # requires OPENAI_API_KEY
            
            llm="google/gemini-2.0-flash",  # requires GOOGLE_API_KEY or GEMINI_API_KEY
            
            # Option 1: Use Cartesia TTS (requires CARTESIA_API_KEY in .env)
            tts="cartesia",
            
            # Option 2: OR use different TTS providers:
            # tts="openai/tts-1",         # requires OPENAI_API_KEY
            # tts="elevenlabs",            # requires ELEVENLABS_API_KEY
            
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
    # Run the agent with production settings
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            initialize_process_timeout=120
        )
    )