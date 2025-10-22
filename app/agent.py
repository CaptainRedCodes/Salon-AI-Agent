
from dataclasses import dataclass, field
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    JobContext,
    RunContext,
)
from livekit.agents.llm import function_tool
from datetime import datetime, timezone
import logging

from app.knowledge_base import KnowledgeManager
from app.booking_manager import BookingManager
from app.helper import HelpRequestManager
from app.model import SalonUserData
from app.information import SALON_INFO,SALON_SERVICES,INSTRUCTIONS
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
    """Context-aware voice assistant for a hair salon."""
    
    def __init__(self, job_context: JobContext):
        self.job_context = job_context
        self.salon_info = SALON_INFO
        self.service_prices = SALON_SERVICES

        self.knowledge_base = KnowledgeManager()
        self.booking_manager = BookingManager()
        self.help_manager = HelpRequestManager()
        
        super().__init__(instructions=INSTRUCTIONS)
                    
        logger.info("Context-aware SalonAssistant initialized successfully")

    @function_tool
    async def get_current_date_and_time(self,context: RunContext[SalonUserData]) -> str:
        """
        Returns the current date, day of the week, and time in human-readable format for the AI agent.
        Updates the agent's context with last tool called and result.
        """
        # Get current UTC time and convert to local timezone
        now = datetime.now(timezone.utc).astimezone()
        
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        
        human_readable = f"{day_name}, {date_str} at {time_str}"
        iso_format = now.isoformat()

        if getattr(context, "userdata", None):
            context.userdata.last_tool_called = "get_current_date_and_time"
            context.userdata.last_tool_result = {
                "day": day_name,
                "date": date_str,
                "time": time_str,
                "human_readable": human_readable,
                "iso": iso_format
            }

        return f"The current date and time is {human_readable}"

    @function_tool
    async def update_booking_context(
        self,
        context: RunContext[SalonUserData],
        customer_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        service: Optional[str] = None,
        appointment_date: Optional[str] = None,
        appointment_time: Optional[str] = None
    ) -> str:
        """
        Update the booking context with customer information.
        Call this whenever you collect a piece of booking information.
        
        Args:
            customer_name: Customer's full name
            phone_number: Customer's 10-digit phone number
            service: Service name (must match available services)
            appointment_date: Date for appointment
            appointment_time: Time for appointment
        """
        try:
            booking = context.userdata.current_booking
            updated_fields = []
            
            # Update provided fields
            if customer_name:
                booking.customer_name = customer_name
                updated_fields.append("name")
            
            if phone_number:
                # Validate phone number
                clean_phone = ''.join(filter(str.isdigit, phone_number))
                if len(clean_phone) != 10:
                    context.userdata.validation_errors.append(
                        f"Invalid phone number: {phone_number} (must be 10 digits)"
                    )
                    return "Phone number must be exactly 10 digits. Please provide a valid 10-digit phone number."
                booking.phone_number = clean_phone
                updated_fields.append("phone")
            
            if service:
                service_lower = service.lower()
                if service_lower in self.service_prices:
                    booking.service = service
                    booking.price = self.service_prices[service_lower]
                    updated_fields.append("service")
                else:
                    available_services = ", ".join([s.title() for s in self.service_prices.keys()])
                    return f"'{service}' is not available. Our services are: {available_services}"
            
            if appointment_date:
                # Check if Thursday
                try:
                    date_obj = datetime.strptime(appointment_date, "%B %d, %Y")
                    if date_obj.strftime("%A") == "Thursday":
                        return "We're closed on Thursdays. Please choose another day (we're open Monday-Wednesday and Friday-Sunday)."
                except:
                    pass  # If parsing fails, still store the date
                
                booking.appointment_date = appointment_date
                updated_fields.append("date")
            
            if appointment_time:
                booking.appointment_time = appointment_time
                updated_fields.append("time")
            
            # Update context state
            context.userdata.last_tool_called = "update_booking_context"
            context.userdata.last_tool_result = updated_fields
            
            if booking.is_complete():
                context.userdata.conversation_state = "ready_for_confirmation"
                return f"Great! I've updated: {', '.join(updated_fields)}. I now have all your information. Let me summarize everything for you."
            else:
                missing = []
                if not booking.customer_name: missing.append("name")
                if not booking.phone_number: missing.append("phone number")
                if not booking.service: missing.append("service")
                if not booking.appointment_date: missing.append("date")
                if not booking.appointment_time: missing.append("time")
                
                return f"I've updated: {', '.join(updated_fields)}. I still need: {', '.join(missing)}."
        
        except Exception as e:
            logger.error(f"Context update failed: {e}")
            return "I had trouble saving that information. Could you repeat it?"

    @function_tool
    async def get_booking_summary(self, context: RunContext[SalonUserData]) -> str:
        """
        Get a summary of the current booking information collected so far.
        Use this before asking for final confirmation.
        """
        booking = context.userdata.current_booking
        
        context.userdata.last_tool_called = "get_booking_summary"
        
        if not booking.is_complete():
            missing = []
            if not booking.customer_name: missing.append("name")
            if not booking.phone_number: missing.append("phone number")
            if not booking.service: missing.append("service")
            if not booking.appointment_date: missing.append("date")
            if not booking.appointment_time: missing.append("time")
            
            return f"Booking is incomplete. Still need: {', '.join(missing)}"
        
        summary = (
            f"Here's what I have:\n"
            f"Name: {booking.customer_name}\n"
            f"Phone: {booking.phone_number}\n"
            f"Service: {booking.service} (${booking.price})\n"
            f"Date: {booking.appointment_date}\n"
            f"Time: {booking.appointment_time}\n\n"
            f"Does everything look correct?"
        )
        
        context.userdata.waiting_for_confirmation = True
        return summary

    @function_tool
    async def book_appointment(self, context: RunContext[SalonUserData]) -> str:
        """
        Book the appointment using information stored in context.
        Only call this after customer has confirmed all details.
        The booking information will be automatically pulled from the context.
        """
        try:
            booking = context.userdata.current_booking
            
            if not booking.is_complete():
                return "Cannot book - missing required information. Please provide all details first."
            
            if not context.userdata.waiting_for_confirmation:
                return "Please let me summarize the booking details for confirmation first."
            
            if not booking.customer_name:
                return "Cannot book - customer name is required."
            if not booking.service:
                return "Cannot book - service is required."
            if not booking.phone_number:
                return "Cannot book - phone number is required."
            if not booking.appointment_date or not booking.appointment_time:
                return "Cannot book - appointment date and time is required."
            if not booking.price:
                return "Cannot book - price is required."
            
            booking_obj = await self.booking_manager.create_booking(
                customer_name=booking.customer_name,
                phone_number=booking.phone_number,
                service=booking.service,
                appointment_date=booking.appointment_date,
                appointment_time=booking.appointment_time,
                price=booking.price,
            )
            
            confirmation_number = booking_obj["confirmation_number"]
            
            # Update context
            context.userdata.conversation_state = "completed"
            context.userdata.last_tool_called = "book_appointment"
            context.userdata.last_tool_result = confirmation_number
            booking.confirmed = True
            
            result = (
                f"Perfect! Your appointment is confirmed for {booking.service} "
                f"on {booking.appointment_date} at {booking.appointment_time}. "
                f"Your confirmation number is {confirmation_number}. "
                f"We'll see you then!"
            )
            
            # Reset for next booking
            context.userdata.reset_booking()
            
            return result
            
        except Exception as e:
            logger.error(f"Booking failed: {e}")
            context.userdata.retry_count += 1
            return (
                "I apologize, but I'm having trouble completing your booking right now. "
                "Let me get assistance from my supervisor to help you with this."
            )

    @function_tool
    async def check_availability(
        self, 
        context: RunContext[SalonUserData], 
        date: str, 
        time: str = ""
    ) -> str:
        """
        Check slot availability for a given date and optionally time.
        Stores the check in context for reference.
        
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
            
            # Track this check in context
            context.userdata.availability_checks.append({
                "date": date,
                "time": time,
                "timestamp": datetime.now().isoformat()
            })
            context.userdata.last_tool_called = "check_availability"

            if time:
                if time not in all_slots:
                    return f"{time} is outside our business hours. Available times on {date}: {', '.join(all_slots)}"
                
                count_query = self.booking_manager.db.collection("appointments")\
                    .where("appointment_date", "==", date)\
                    .where("appointment_time", "==", time)\
                    .count()
                
                count_result = count_query.get()
                slot_count = count_result[0].value if count_result else 0

                if slot_count < MAX_BOOKINGS_PER_SLOT:
                    context.userdata.last_tool_result = "available"
                    return f"{time} on {date} is available."
                else:
                    # Find alternatives
                    available_slots = []
                    for slot in all_slots:
                        c_q = self.booking_manager.db.collection("appointments")\
                            .where("appointment_date", "==", date)\
                            .where("appointment_time", "==", slot)\
                            .count()
                        c_r = c_q.get()
                        if c_r[0].value < MAX_BOOKINGS_PER_SLOT:
                            available_slots.append(slot)

                    context.userdata.last_tool_result = {"booked": time, "alternatives": available_slots}
                    
                    if available_slots:
                        return f"{time} is fully booked. Available slots on {date}: {', '.join(available_slots)}"
                    else:
                        return f"All slots on {date} are fully booked."
            else:
                # Check all slots for the date
                available_slots = []
                for slot in all_slots:
                    c_q = self.booking_manager.db.collection("appointments")\
                        .where("appointment_date", "==", date)\
                        .where("appointment_time", "==", slot)\
                        .count()
                    c_r = c_q.get()
                    if c_r[0].value < MAX_BOOKINGS_PER_SLOT:
                        available_slots.append(slot)

                context.userdata.last_tool_result = available_slots

                if available_slots:
                    slots_formatted = "\n".join(f"• {t}" for t in available_slots)
                    return f"Available times on {date}:\n{slots_formatted}"
                else:
                    return f"Unfortunately, we're fully booked on {date}. Would you like to check another date?"

        except Exception as e:
            logger.error(f"Availability check failed: {e}")
            return "I'm having trouble checking availability. Let me get help from my supervisor."

    @function_tool
    async def request_help(
        self, 
        context: RunContext[SalonUserData],
        question: str
    ) -> str:
        """
        Request human assistance for questions not covered in FAQ/knowledge base.
        Uses context to provide better information to support team.
        
        Args:
            question: Customer's legitimate query
        """
        question = question.strip()
        
        # Track in context
        context.userdata.add_query(question)
        context.userdata.last_tool_called = "request_help"
        
        logger.info(f"Help requested: {question}")
        
        try:
            question_lower = question.lower()
            
            # Check FAQ first
            try:
                faq_results = await self.knowledge_base.search_faq(question_lower)
                if faq_results:
                    faq_answer = faq_results.get('answer')
                    if faq_answer:
                        logger.info(f"Found FAQ answer for: {question}")
                        context.userdata.last_tool_result = "faq_found"
                        return faq_answer
            except Exception as e:
                logger.warning(f"FAQ search failed: {e}")

            # Check Knowledge Base
            try:
                kb_answer = await self.knowledge_base.search_knowledge(question_lower)
                if kb_answer:
                    logger.info(f"Found KB answer for: {question}")
                    context.userdata.last_tool_result = "kb_found"
                    return kb_answer
            except Exception as e:
                logger.warning(f"KB search failed: {e}")

            # Create help request with context
            room_name = None
            if self.job_context and hasattr(self.job_context, 'room') and self.job_context.room:
                room_name = self.job_context.room.name

            customer_context = {
                "timestamp": datetime.now().isoformat(),
                "room_name": room_name,
                "booking_progress": {
                    "customer_name": context.userdata.current_booking.customer_name,
                    "service": context.userdata.current_booking.service,
                    "appointment_date": context.userdata.current_booking.appointment_date,
                    "appointment_time": context.userdata.current_booking.appointment_time,
                    "is_complete": context.userdata.current_booking.is_complete()
                },
                "conversation_state": context.userdata.conversation_state,
                "previous_queries": context.userdata.previous_queries[-3:] if context.userdata.previous_queries else []
            }

            request_id = await self.help_manager.create_help_request(
                reason=question,
                room_name=room_name,
                customer_context=customer_context
            )

            logger.info(f"Help request created: {request_id}")
            context.userdata.last_tool_result = f"help_requested:{request_id}"

            return (
                f"Let me check with my supervisor about that and get back to you. "
                f"I've noted your question. "
                f"Please hold for a moment while I get the correct information."
            )

        except Exception as e:
            logger.error(f"Failed in request_help: {e}", exc_info=True)
            return (
                "I'm having a technical issue right now. "
                "Please hold on or I can connect you with a supervisor."
            )