from livekit.agents.llm import function_tool
from datetime import datetime, timezone
import sys

from app.core.logging_config import get_logger
from app.core.config import SalonDataLoader
from app.services.api_client import backend_client
from app.models.user import SalonUserData


if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# centralized salon data loader
SALON_SERVICES = SalonDataLoader.get_services()

logger = get_logger(__name__)


class Assistant:
    """
    Voice assistant for salon appointment booking.
    
    All data operations go through the FastAPI backend:
    - Bookings: POST /api/bookings
    - Availability: GET /api/availability
    - Help requests: POST /api/help-requests
    - Knowledge base: GET /api/knowledge-base/search
    """
    
    def __init__(self, session: SalonUserData, ctx):
        """
        Initialize assistant with user-specific context.
        
        Args:
            session: User-specific data model
            ctx: JobContext from LiveKit
        """
        self._ctx = ctx
        self._userdata = session
        
        # Use centralized salon data loader
        self.salon_info = {
            "name": SalonDataLoader.get_name(),
            "address": SalonDataLoader.get_address(),
            "contact": SalonDataLoader.get_contact(),
            "working_hours": SalonDataLoader.get_working_hours(),
            "services": SalonDataLoader.get_services()
        }
        
        logger.info("Assistant initialized (using backend API)")
    
    @function_tool
    async def get_current_date_and_time(
        self,
        format: str = "",
    ) -> str:
        """
        Returns the current date, day of the week, and time in human-readable format.
        Use this when you need to know what day or time it is.
        
        Args:
            format: Optional format preference (not used, for schema compatibility)
        
        Returns:
            str: Current date and time formatted for conversation
        """
        now = datetime.now(timezone.utc).astimezone()
        
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        
        human_readable = f"{day_name}, {date_str} at {time_str}"
        iso_format = now.isoformat()
        
        # Update context
        self._userdata.last_tool_called = "get_current_date_and_time"
        self._userdata.last_tool_result = {
            "day": day_name,
            "date": date_str,
            "time": time_str,
            "human_readable": human_readable,
            "iso": iso_format,
        }
        
        return f"The current date and time is {now.strftime('%A, %B %d, %Y at %I:%M %p')}"
    
    @function_tool
    async def collect_customer_information(
        self,
        customer_name: str = "",
        phone_number: str = "",
    ) -> str:
        """
        Collect and store customer's personal information (name and phone).
        Use this tool FIRST when starting a new booking.
        
        Args:
            customer_name: The customer's full name
            phone_number: The customer's 10-digit phone number
        """
        booking = self._userdata.current_booking
        updated_fields = []

        try:
            # Update name
            if customer_name and customer_name.lower() not in ("unknown", "none", ""):
                booking.customer_name = customer_name.strip()
                updated_fields.append("name")
                logger.info(f"Stored customer name: {customer_name}")

            # Update phone
            if phone_number:
                clean = ''.join(filter(str.isdigit, phone_number))
                if len(clean) != 10:
                    return "I couldn't catch a valid 10-digit phone number. Please repeat it slowly."
                booking.phone_number = clean
                updated_fields.append("phone number")
                logger.info(f"Stored phone number: {clean}")

            self._userdata.last_tool_called = "collect_customer_information"
            self._userdata.last_tool_result = updated_fields

            if updated_fields:
                response = f"Got it! I've saved your {', '.join(updated_fields)}."

                missing = []
                if not booking.customer_name:
                    missing.append("name")
                if not booking.phone_number:
                    missing.append("phone number")

                if missing:
                    response += f" I still need your {', '.join(missing)}."
                else:
                    response += " Now, what service would you like to book?"

                return response

            return "Please provide your name and phone number."

        except Exception as e:
            logger.error("Failed to collect customer info", exc_info=True)
            return "I had trouble saving that information. Could you repeat it?"
    
    @function_tool
    async def select_service(
        self, 
        service: str,
    ) -> str:
        """
        Select a service from available salon services.
        Use this after collecting customer information.
        
        Args:
            service: The name of the salon service (e.g., 'haircut', 'hair coloring')
            
        Returns:
            str: Confirmation with price and next steps
        """
        booking = self._userdata.current_booking
        
        try:
            # Validate customer info exists
            if not booking.customer_name or not booking.phone_number:
                return "I need your name and phone number first before selecting a service."
            
            # Validate and set service
            service_lower = service.lower().strip()
            if service_lower in self.salon_info['services']:
                booking.service = service
                booking.price = self.salon_info['services'][service_lower]
                
                self._userdata.last_tool_called = "select_service"
                self._userdata.last_tool_result = service
                
                logger.info(f"Service selected: {service} at ₹{booking.price}")
                
                return (
                    f"Perfect! {service.title()} costs ₹{booking.price}. "
                    "Now, when would you like to schedule your appointment? "
                    "Please provide a date and time."
                )
            else:
                available = ", ".join([s.title() for s in self.salon_info['services'].keys()])
                return (
                    f"I'm sorry, we don't offer '{service}'. "
                    f"Our available services are: {available}. "
                    "Which one would you like?"
                )
        
        except Exception as e:
            logger.error(f"Service selection failed: {e}", exc_info=True)
            return "I had trouble with that service selection. Could you try again?"
    
    @function_tool
    async def check_availability(
        self, 
        date: str,
        time: str = "",
    ) -> str:
        """
        Check available time slots for a specific date.
        Use this when customer wants to see what times are available.
        
        Args:
            date: The date to check (e.g., 'January 30, 2026', 'tomorrow')
            time: Specific time to check, or empty string for all slots (e.g., '10:00 AM')
            
        Returns:
            str: Available slots or specific time availability
        """
        time_value = time.strip() if time and time.strip() else None
        
        try:
            if not date:
                return "Please provide a date to check availability."
            
            # Log the check
            self._userdata.availability_checks.append({
                "date": date,
                "time": time_value or "all",
                "timestamp": datetime.now().isoformat()
            })
            self._userdata.last_tool_called = "check_availability"
            
            result = await backend_client.check_availability(date, time_value)
            
            if not result["success"]:
                return "I'm having trouble checking availability. Please try again."
            
            # Store result
            self._userdata.last_tool_result = result
            logger.info(f"Availability checked for {date} {time_value or 'all slots'}")
            
            # Format response
            if time_value:
                if result.get("available"):
                    return f"Great news! {time_value} on {date} is available. Would you like to book it?"
                else:
                    alt_slots = result.get("available_slots", [])
                    if alt_slots:
                        slots_str = ", ".join(alt_slots[:3]) 
                        return f"Sorry, {time_value} on {date} is fully booked. Available times: {slots_str}. Would any of these work?"
                    else:
                        return f"Sorry, {date} is fully booked. Would you like to try another date?"
            else:
                available_slots = result.get("available_slots", [])
                if available_slots:
                    slots_str = ", ".join(available_slots)
                    return f"Available times on {date}: {slots_str}. Which one works for you?"
                else:
                    return f"Sorry, {date} is fully booked. Would you like to try another date?"
            
        except Exception as e:
            logger.error(f"Availability check failed: {e}", exc_info=True)
            return "I'm having trouble checking availability right now. Please try again."
        
    @function_tool
    async def schedule_appointment(
        self, 
        appointment_date: str,
        appointment_time: str,
    ) -> str:
        """
        Schedule the appointment with a specific date and time.
        Use this after customer info and service are collected.
        
        Args:
            appointment_date: The date for the appointment (e.g., 'January 30, 2026')
            appointment_time: The time slot (e.g., '10:00 AM')
            
        Returns:
            str: Confirmation or availability status
        """
        booking = self._userdata.current_booking
        try:
            # Validate prerequisites
            if not booking.customer_name or not booking.phone_number:
                return "I need your name and phone number first."
            
            if not booking.service:
                return "Please select a service before scheduling a time."
            
            # Check availability via backend
            result = await backend_client.check_availability(appointment_date, appointment_time)
            
            if not result["success"]:
                return "I'm having trouble checking availability. Let me try again."
            
            if not result.get("available", False):
                return (
                    f"Sorry, {appointment_time} on {appointment_date} is not available. "
                    "Would you like to check available slots for that date?"
                )
            
            # Store the appointment details
            booking.appointment_date = appointment_date
            booking.appointment_time = appointment_time
            
            self._userdata.last_tool_called = "schedule_appointment"
            self._userdata.last_tool_result = {
                "date": appointment_date,
                "time": appointment_time
            }
            
            logger.info(f"Appointment scheduled: {appointment_date} at {appointment_time}")
            
            # Move to confirmation state
            self._userdata.conversation_state = "ready_for_confirmation"
            
            return (
                f"Great! I've scheduled your {booking.service} for {appointment_date} "
                f"at {appointment_time}. Let me summarize everything for confirmation."
            )
        
        except Exception as e:
            logger.error(f"Scheduling failed: {e}", exc_info=True)
            return "I had trouble scheduling that. Could you try again?"
    
    @function_tool
    async def get_booking_summary(
        self,
        include_price: str = "true",
    ) -> str:
        """
        Get a complete summary of the current booking for customer confirmation.
        Use this after all booking details are collected and before final confirmation.
        
        Args:
            include_price: Whether to show price in summary (default: True)
        
        Returns:
            str: Formatted booking summary with all details
        """
        booking = self._userdata.current_booking
        self._userdata.last_tool_called = "get_booking_summary"
        show_price = include_price.lower() in ["true", "yes", "1"]
        
        if not booking.is_complete():
            missing = []
            if not booking.customer_name:
                missing.append("name")
            if not booking.phone_number:
                missing.append("phone number")
            if not booking.service:
                missing.append("service")
            if not booking.appointment_date:
                missing.append("date")
            if not booking.appointment_time:
                missing.append("time")
            
            return f"The booking is incomplete. I still need: {', '.join(missing)}"
        if show_price and booking.price:
            service_line = f"• Service: \n{booking.service} (₹{booking.price})\n"
        else:
            service_line = f"• Service: \n{booking.service}\n"
        summary = (
            f"Let me confirm your booking details:\n"
            f"• Name: \n{booking.customer_name}\n"
            f"• Phone: \n{booking.phone_number}\n"
            f"\n{service_line}\n"
            f"• Date: \n{booking.appointment_date}\n"
            f"• Time: \n{booking.appointment_time}\n\n"
            f"Is everything correct? Say 'yes' to confirm or tell me what needs to be changed."
        )
        
        self._userdata.waiting_for_confirmation = True
        logger.info("Booking summary generated, waiting for confirmation")
        
        return summary
    
    @function_tool
    async def confirm_booking(
        self,
        confirmed: str = "true",
    ) -> str:
        """
        Finalize and confirm the booking after customer approval.
        ONLY use this after getting explicit customer confirmation (e.g., "yes", "correct", "confirm").
        
        This calls the FastAPI backend to create the booking with conflict prevention.
        
        Args:
            confirmed: Confirmation flag (default: True)
        
        Returns:
            str: Final confirmation with booking number
        """
        booking = self._userdata.current_booking
        is_confirmed = confirmed.lower() in ["true", "yes", "1"]
        
        if not is_confirmed:
            return "Okay, let me know what you'd like to change."
        # Validate completeness
        if not booking.is_complete():
            return "Cannot confirm - booking information is incomplete. Let me know what's missing."
        
        if not self._userdata.waiting_for_confirmation:
            return "Please let me show you the booking summary first so you can review it."
        
        try:
            result = await backend_client.create_booking(
                customer_name=str(booking.customer_name),
                phone_number=str(booking.phone_number),
                service=str(booking.service),
                appointment_date=str(booking.appointment_date),
                appointment_time=str(booking.appointment_time),
                price=float(booking.price) if booking.price else 0.0,
            )
            
            if not result["success"]:
                error = result.get("error", "Unknown error")
                
                # Handle slot conflict
                if "fully booked" in error.lower():
                    return (
                        f"I'm sorry, but {booking.appointment_time} on {booking.appointment_date} "
                        "just became unavailable. Let me help you find another time."
                    )
                
                return f"I had trouble confirming: {error}. Please try again."
            
            confirmation_number = result["confirmation_number"]
            
            # Update context
            self._userdata.conversation_state = "completed"
            self._userdata.last_tool_called = "confirm_booking"
            self._userdata.last_tool_result = confirmation_number
            booking.confirmed = True
            
            logger.info(f"Booking confirmed via backend: {confirmation_number}")
            
            response = (
                f"Perfect! Your {booking.service} appointment is confirmed!\n"
                f"Date: \n{booking.appointment_date}\n"
                f"Time: \n{booking.appointment_time}\n"
                f"Confirmation Number: \n{confirmation_number}\n\n"
                f"We look forward to seeing you, {booking.customer_name}!\n"
                f"If you need to make changes, please call us at {self.salon_info['contact']}."
            )
            
            # Reset for next booking
            self._userdata.reset_booking()
            
            return response
            
        except Exception as e:
            logger.error(f"Booking creation failed: {e}", exc_info=True)
            return (
                "I encountered an error while confirming your booking. "
                f"Please call us directly at {self.salon_info['contact']} to complete your booking."
            )
    
    @function_tool
    async def modify_booking_detail(
        self, 
        field: str,
        new_value: str,
    ) -> str:
        """
        Modify a specific detail in the current booking before confirmation.
        Use this when customer wants to change something they already provided.
        
        Args:
            field: The booking field to modify (name, phone, service, date, or time)
            new_value: The new value for that field
            
        Returns:
            str: Confirmation of the change
        """
        booking = self._userdata.current_booking
        field_lower = field.lower()
        
        try:
            if field_lower in ["name", "customer_name"]:
                booking.customer_name = new_value.strip()
                return f"Updated your name to {new_value}. Anything else to change?"
            
            elif field_lower in ["phone", "phone_number"]:
                clean_phone = ''.join(filter(str.isdigit, new_value))
                if len(clean_phone) >= 10:
                    booking.phone_number = clean_phone[-10:]
                    return f"Updated your phone number. Anything else?"
                else:
                    return "Please provide a valid 10-digit phone number."
            
            elif field_lower == "service":
                return await self.select_service(service=new_value)
            
            elif field_lower == "date":
                booking.appointment_date = new_value
                return f"Updated appointment date to {new_value}. Anything else?"
            
            elif field_lower == "time":
                booking.appointment_time = new_value
                return f"Updated appointment time to {new_value}. Anything else?"
            
            else:
                return f"I can modify: name, phone, service, date, or time. Which would you like to change?"
        
        except Exception as e:
            logger.error(f"Modification failed: {e}", exc_info=True)
            return "I had trouble making that change. Could you try again?"
    
    @function_tool
    async def get_salon_information(
        self,
        info_type: str = "all",
    ) -> str:
        """
        Get information about the salon (services, hours, contact, location).
        
        Args:
            info_type: Type of info to retrieve (services, hours, contact, location, or all)
            
        Returns:
            str: Requested salon information
        """
        info_type_lower = info_type.lower().strip()
        
        try:
            if info_type_lower == "services":
                services_list = [
                    f"• {service.title()}: ₹{price}"
                    for service, price in self.salon_info['services'].items()
                ]
                return f"Our services:\n" + "\n".join(services_list)
            
            elif info_type_lower == "hours":
                return f"We're open {self.salon_info['working_hours']}"
            
            elif info_type_lower == "contact":
                return f"You can reach us at {self.salon_info['contact']}"
            
            elif info_type_lower == "location":
                return f"We're located at {self.salon_info['address']}"
            
            else:  # "all"
                services_list = ", ".join([s.title() for s in self.salon_info['services'].keys()])
                return (
                    f"{self.salon_info['name']}\n"
                    f"Location: {self.salon_info['address']}\n"
                    f"Phone: {self.salon_info['contact']}\n"
                    f"Hours: {self.salon_info['working_hours']}\n"
                    f"Services: {services_list}"
                )
        
        except Exception as e:
            logger.error(f"Error getting salon info: {e}", exc_info=True)
            return "I'm having trouble retrieving that information right now."
    
    @function_tool
    async def request_help(
        self, 
        question: str,
    ) -> str:
        """
        Answer customer questions using knowledge base or escalate to supervisor.
        
        Flow:
        1. First searches knowledge base via backend API
        2. If no answer found, creates help request for supervisor
        3. Supervisor sees request in dashboard with customer context
        
        Args:
            question: The customer's question that needs assistance
            
        Returns:
            str: Answer or confirmation of escalation
        """
        logger.info(f"Help requested: {question[:50]}...")
        
        try:
            # Search knowledge base via backend
            kb_result = await backend_client.search_knowledge_base(question, threshold=0.7)
            
            if kb_result["success"] and kb_result.get("found"):
                logger.info("Answered from knowledge base")
                self._userdata.last_tool_called = "request_help"
                self._userdata.last_tool_result = "kb_found"
                return kb_result["answer"]
            
            # Escalate to supervisor via backend
            logger.info("Escalating to supervisor")
            
            # Get customer context
            booking = self._userdata.current_booking
            booking_context = None
            if booking:
                booking_context = {
                    "customer_name": booking.customer_name,
                    "phone_number": booking.phone_number,
                    "service": booking.service,
                    "appointment_date": booking.appointment_date,
                    "appointment_time": booking.appointment_time,
                }
            
            # Create help request via backend
            result = await backend_client.create_help_request(
                question=question,
                customer_name=str(booking.customer_name if booking else "unknown"),
                customer_phone=str(booking.phone_number if booking else "unknown"),
                booking_context=booking_context or {},
                room_name=str(getattr(self._ctx, 'room_name', None)),
            )
            
            self._userdata.last_tool_called = "request_help"
            self._userdata.last_tool_result = {
                "status": "supervisor_notified",
                "request_id": result.get("request_id"),
            }
            
            return (
                "That's a great question! Let me check with my supervisor and get back to you. "
                "I've sent them all your details. They'll reach out to you shortly. "
                "In the meantime, is there anything else I can help with?"
            )
            
        except Exception as e:
            logger.error(f"Error in request_help: {e}", exc_info=True)
            return (
                "I'm having trouble right now. "
                f"Please call us directly at {self.salon_info['contact']} for assistance."
            )
