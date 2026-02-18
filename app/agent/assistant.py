import asyncio
import sys
from datetime import datetime, timezone

from livekit.agents import Agent, RunContext, function_tool, get_job_context
from livekit.agents.llm import ToolError

from app.core.config import SalonDataLoader
from app.core.logging_config import get_logger
from app.models.user import SalonUserData
from app.services.api_client import backend_client
from app.agent.prompts import INSTRUCTIONS

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = get_logger(__name__)


class Assistant(Agent):
    """
    Voice receptionist agent for salon appointment booking.

    Inherits from livekit.agents.Agent so LiveKit can:
    - Automatically register @function_tool methods
    - Route RunContext / userdata properly
    - Handle session lifecycle (on_enter, interruptions, etc.)

    All persistent booking state lives in context.userdata (SalonUserData).
    All data operations go through the FastAPI backend:
        - POST /api/bookings
        - GET  /api/availability
        - POST /api/help-requests
        - GET  /api/knowledge-base/search
    """

    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)

        # Salon info cached at startup — read-only, safe to share across sessions
        self._salon = {
            "name": SalonDataLoader.get_name(),
            "address": SalonDataLoader.get_address(),
            "contact": SalonDataLoader.get_contact(),
            "working_hours": SalonDataLoader.get_working_hours(),
            "services": SalonDataLoader.get_services(),  # dict[str, float]
        }
        logger.info("Assistant initialised")

    async def on_enter(self) -> None:
        """Called by LiveKit when this agent becomes active in a session."""
        self.session.generate_reply(
            instructions="Greet the caller warmly and ask how you can help them today."
        )

    # ------------------------------------------------------------------ #
    #  HELPERS                                                             #
    # ------------------------------------------------------------------ #

    def _userdata(self, context: RunContext) -> SalonUserData:
        """Typed shortcut to session userdata."""
        return context.userdata  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    #  TOOL: get_current_date_and_time                                     #
    # ------------------------------------------------------------------ #

    @function_tool(
        raw_schema={
            "name": "get_current_date_and_time",
            "description": "Return the current date, day of week, and local time. "
            "Call this whenever the customer says 'today', 'tomorrow', 'this Friday', "
            "or any other relative date expression — BEFORE making availability calls. "
            "Returns a human-readable string such as: 'Wednesday, February 18, 2026 at 10:30 AM'",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    async def get_current_date_and_time(self, context: RunContext) -> str:
        """Return the current date, day of week, and local time.

        Call this whenever the customer says 'today', 'tomorrow', 'this Friday',
        or any other relative date expression — BEFORE making availability calls.

        Returns a human-readable string such as:
        'Wednesday, February 18, 2026 at 10:30 AM'
        """
        now = datetime.now(timezone.utc).astimezone()
        result = now.strftime("%A, %B %d, %Y at %I:%M %p")
        logger.debug("get_current_date_and_time → %s", result)
        return f"The current date and time is {result}"

    # ------------------------------------------------------------------ #
    #  TOOL: set_customer_name                                             #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def set_customer_name(self, context: RunContext, name: str) -> str:
        """Store the customer's full name.

        Call as soon as the customer provides their name.
        Do NOT call if the name is already stored.

        Args:
            name: The customer's full name (e.g. 'Priya Sharma')
        """
        ud = self._userdata(context)
        ud.current_booking.customer_name = name.strip()
        logger.info("Stored customer name: %s", name)
        return f"Got it, I've noted your name as {name}."

    # ------------------------------------------------------------------ #
    #  TOOL: set_customer_phone                                            #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def set_customer_phone(self, context: RunContext, phone_number: str) -> str:
        """Store the customer's 10-digit mobile number.

        Call as soon as the customer provides their phone number.
        Do NOT call if a valid phone is already stored.

        Args:
            phone_number: Raw phone input — digits only will be extracted.
                          Must resolve to exactly 10 digits after cleaning.
        """
        clean = "".join(filter(str.isdigit, phone_number))
        if len(clean) != 10:
            raise ToolError(
                "The phone number is not exactly 10 digits. "
                "Ask the customer to repeat it slowly."
            )
        ud = self._userdata(context)
        ud.current_booking.phone_number = clean
        logger.info("Stored phone: %s", clean)
        return (
            f"Got it. I've saved your number as {clean}. "
            "Could you confirm that's correct?"
        )

    # ------------------------------------------------------------------ #
    #  TOOL: select_service                                                #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def select_service(self, context: RunContext, service: str) -> str:
        """Select and store a salon service from the available menu.

        Call this as soon as the customer mentions what service they want.
        Always announce the price after calling this tool.

        Do NOT use for services not in the menu — instead tell the customer
        what IS available.

        Args:
            service: Service name as spoken by the customer
                     (e.g. 'haircut', 'hair coloring', 'facial')
        """
        ud = self._userdata(context)
        services: dict[str, float] = self._salon["services"]
        key = service.lower().strip()

        if key not in services:
            available = ", ".join(s.title() for s in services)
            raise ToolError(
                f"'{service}' is not on our menu. "
                f"Tell the customer our services are: {available}."
            )

        ud.current_booking.service = key
        ud.current_booking.price = services[key]
        logger.info("Service selected: %s @ ₹%s", key, services[key])
        return (
            f"Service set to {key.title()} at ₹{services[key]}. "
            "Ask the customer for their preferred date and time."
        )

    # ------------------------------------------------------------------ #
    #  TOOL: check_availability                                            #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def check_availability(
        self,
        context: RunContext,
        date: str,
        time: str = "",
    ) -> str:
        """Check available appointment slots for a given date (and optionally a time).

        ALWAYS call this BEFORE promising or scheduling any slot.
        Never assume a slot is free without calling this first.

        Args:
            date: Full date string, e.g. 'February 18, 2026' or
                  'Wednesday, February 18, 2026'. Use get_current_date_and_time
                  first if the customer used a relative expression like 'tomorrow'.
            time: Specific time to check, e.g. '10:00 AM'. Leave empty to
                  retrieve all open slots for the day.
        """
        if not date:
            raise ToolError("A date is required to check availability.")

        time_value = time.strip() or None

        # Run async fetch; support graceful interruption
        task: asyncio.Task = asyncio.ensure_future(
            backend_client.check_availability(date, time_value)
        )
        await context.speech_handle.wait_if_not_interrupted([task])

        if context.speech_handle.interrupted:
            task.cancel()
            return None  # Tool silently cancelled; LLM will re-engage

        result = await task

        if not result.get("success"):
            raise ToolError(
                "Availability service is unreachable. "
                "Ask the customer to try a different date or time."
            )

        ud = self._userdata(context)
        ud.availability_checks.append(
            {
                "date": date,
                "time": time_value or "all",
                "timestamp": datetime.now().isoformat(),
            }
        )
        logger.info("Availability checked: %s %s", date, time_value or "all")

        if time_value:
            if result.get("available"):
                return f"{time_value} on {date} is available. Proceed to schedule_appointment."
            alt = result.get("available_slots", [])
            if alt:
                return (
                    f"{time_value} on {date} is taken. "
                    f"Available slots: {', '.join(alt[:3])}. "
                    "Offer these alternatives to the customer."
                )
            return f"{date} is fully booked. Ask the customer to suggest another date."
        else:
            slots = result.get("available_slots", [])
            if slots:
                return (
                    f"Available times on {date}: {', '.join(slots)}. "
                    "Ask the customer which slot they prefer."
                )
            return f"{date} is fully booked. Ask the customer for another date."

    # ------------------------------------------------------------------ #
    #  TOOL: schedule_appointment                                          #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def schedule_appointment(
        self,
        context: RunContext,
        appointment_date: str,
        appointment_time: str,
    ) -> str:
        """Lock in the appointment date and time after availability is confirmed.

        ONLY call this after check_availability has confirmed the slot is open.
        Prerequisites: customer name, phone, and service must already be stored.

        Args:
            appointment_date: Full date string, e.g. 'February 18, 2026'
            appointment_time: Time in AM/PM format, e.g. '10:00 AM'
        """
        ud = self._userdata(context)
        booking = ud.current_booking

        if not booking.customer_name or not booking.phone_number:
            raise ToolError(
                "Customer name or phone is missing. "
                "Collect that information before scheduling."
            )
        if not booking.service:
            raise ToolError(
                "No service selected yet. Ask the customer which service they want first."
            )

        # Re-verify availability to catch race conditions
        result = await backend_client.check_availability(
            appointment_date, appointment_time
        )
        if not result.get("success"):
            raise ToolError(
                "Could not verify availability. Ask the customer to try again."
            )
        if not result.get("available"):
            raise ToolError(
                f"{appointment_time} on {appointment_date} is no longer available. "
                "Offer the customer alternative slots."
            )

        booking.appointment_date = appointment_date
        booking.appointment_time = appointment_time
        ud.conversation_state = "ready_for_confirmation"
        logger.info("Appointment set: %s @ %s", appointment_date, appointment_time)

        return (
            f"Appointment saved for {booking.service.title()} on "
            f"{appointment_date} at {appointment_time}. "
            "Now call get_booking_summary to read the details back to the customer."
        )

    # ------------------------------------------------------------------ #
    #  TOOL: get_booking_summary                                           #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def get_booking_summary(
        self,
        context: RunContext,
        include_price: bool = True,
    ) -> str:
        """Return a complete, formatted booking summary for the customer to review.

        Call this AFTER all booking details are collected and BEFORE calling
        confirm_booking. It is mandatory — never skip this step.

        Args:
            include_price: Whether to include the service price in the summary.
        """
        ud = self._userdata(context)
        booking = ud.current_booking

        missing = []
        if not booking.customer_name:
            missing.append("name")
        if not booking.phone_number:
            missing.append("phone number")
        if not booking.service:
            missing.append("service")
        if not booking.appointment_date:
            missing.append("appointment date")
        if not booking.appointment_time:
            missing.append("appointment time")

        if missing:
            raise ToolError(
                f"Booking is incomplete. Still missing: {', '.join(missing)}. "
                "Collect these before showing the summary."
            )

        service_line = (
            f"{booking.service.title()} (₹{booking.price})"
            if include_price and booking.price
            else booking.service.title()
        )

        summary = (
            f"Here are the booking details:\n"
            f"Name: {booking.customer_name}\n"
            f"Phone: {booking.phone_number}\n"
            f"Service: {service_line}\n"
            f"Date: {booking.appointment_date}\n"
            f"Time: {booking.appointment_time}\n\n"
            f"Read these back to the customer and ask: "
            f"'Does everything look correct?'"
        )

        ud.waiting_for_confirmation = True
        logger.info("Booking summary generated — waiting for customer confirmation")
        return summary

    # ------------------------------------------------------------------ #
    #  TOOL: confirm_booking                                               #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def confirm_booking(
        self,
        context: RunContext,
        customer_confirmed: bool = True,
    ) -> str:
        """Finalise and submit the booking to the backend.

        ONLY call this after the customer has explicitly said 'yes', 'confirm',
        'that's right', or an equivalent approval.
        NEVER call this speculatively or before showing the booking summary.

        Interruptions are disabled because the booking cannot be undone once submitted.

        Args:
            customer_confirmed: Set to True when the customer has given explicit approval.
                                 Never call with False — simply don't call the tool instead.
        """
        if not customer_confirmed:
            return "Understood. Let me know what you'd like to change."

        context.disallow_interruptions()

        ud = self._userdata(context)
        booking = ud.current_booking

        if not ud.waiting_for_confirmation:
            raise ToolError(
                "The booking summary has not been shown yet. "
                "Call get_booking_summary first, then wait for the customer to approve."
            )

        if not booking.is_complete():
            raise ToolError(
                "Booking is incomplete. Cannot confirm — collect missing details first."
            )

        result = await backend_client.create_booking(
            customer_name=str(booking.customer_name),
            phone_number=str(booking.phone_number),
            service=str(booking.service),
            appointment_date=str(booking.appointment_date),
            appointment_time=str(booking.appointment_time),
            price=float(booking.price) if booking.price else 0.0,
        )

        if not result.get("success"):
            error = result.get("error", "")
            if "fully booked" in error.lower():
                raise ToolError(
                    f"{booking.appointment_time} on {booking.appointment_date} "
                    "just became unavailable. Apologise and help the customer pick another slot."
                )
            raise ToolError(
                f"Backend error: {error}. "
                f"Tell the customer to call {self._salon['contact']} to complete the booking."
            )

        confirmation_number = result["confirmation_number"]
        booking.confirmed = True
        ud.conversation_state = "completed"
        logger.info("Booking confirmed: %s", confirmation_number)

        response = (
            f"Booking confirmed!\n"
            f"Confirmation number: {confirmation_number}\n"
            f"Service: {booking.service.title()}\n"
            f"Date: {booking.appointment_date}\n"
            f"Time: {booking.appointment_time}\n\n"
            f"Tell the customer their confirmation number, wish them a great visit, "
            f"and let them know they can call {self._salon['contact']} for any changes."
        )

        ud.reset_booking()
        return response

    # ------------------------------------------------------------------ #
    #  TOOL: modify_booking_detail                                         #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def modify_booking_detail(
        self,
        context: RunContext,
        field: str,
        new_value: str,
    ) -> str:
        """Change a single field in the current booking before confirmation.

        Use this when the customer wants to correct something they already provided.
        After modifying, call get_booking_summary again to present updated details.

        Args:
            field: One of: 'name', 'phone', 'service', 'date', 'time'
            new_value: The replacement value for that field
        """
        ud = self._userdata(context)
        booking = ud.current_booking
        f = field.lower().strip()

        if f in ("name", "customer_name"):
            booking.customer_name = new_value.strip()
            return f"Name updated to {new_value}. Is there anything else to change?"

        if f in ("phone", "phone_number"):
            clean = "".join(filter(str.isdigit, new_value))
            if len(clean) != 10:
                raise ToolError(
                    "The new phone number is not 10 digits. Ask the customer to repeat it."
                )
            booking.phone_number = clean
            return f"Phone updated to {clean}. Is there anything else to change?"

        if f == "service":
            # Delegate to select_service for validation
            services: dict[str, float] = self._salon["services"]
            key = new_value.lower().strip()
            if key not in services:
                available = ", ".join(s.title() for s in services)
                raise ToolError(
                    f"'{new_value}' is not available. Our services: {available}."
                )
            booking.service = key
            booking.price = services[key]
            return (
                f"Service updated to {key.title()} at ₹{services[key]}. "
                "Is there anything else to change?"
            )

        if f == "date":
            booking.appointment_date = new_value
            return f"Date updated to {new_value}. Is there anything else to change?"

        if f == "time":
            booking.appointment_time = new_value
            return f"Time updated to {new_value}. Is there anything else to change?"

        raise ToolError(
            "I can only modify: name, phone, service, date, or time. "
            "Which field does the customer want to change?"
        )

    # ------------------------------------------------------------------ #
    #  TOOL: get_salon_information                                         #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def get_salon_information(
        self,
        context: RunContext,
        info_type: str = "all",
    ) -> str:
        """Retrieve salon details to answer customer questions.

        Use only for questions you cannot answer from the prompt directly.
        Valid info_type values: 'services', 'hours', 'contact', 'location', 'all'

        Args:
            info_type: The category of information requested.
        """
        s = self._salon
        t = info_type.lower().strip()

        if t == "services":
            lines = "\n".join(
                f"- {svc.title()}: ₹{price}" for svc, price in s["services"].items()
            )
            return f"Our services:\n{lines}"

        if t == "hours":
            return f"We are open {s['working_hours']} (closed every Thursday)."

        if t == "contact":
            return f"Customers can reach us at {s['contact']}."

        if t == "location":
            return f"We are located at {s['address']}."

        # "all"
        services_line = ", ".join(svc.title() for svc in s["services"])
        return (
            f"{s['name']}\n"
            f"Location: {s['address']}\n"
            f"Phone: {s['contact']}\n"
            f"Hours: {s['working_hours']} (closed Thursdays)\n"
            f"Services: {services_line}"
        )

    # ------------------------------------------------------------------ #
    #  TOOL: request_help                                                  #
    # ------------------------------------------------------------------ #

    @function_tool()
    async def request_help(self, context: RunContext, question: str) -> str:
        """Answer complex customer questions via knowledge base or supervisor escalation.

        Use ONLY for questions you genuinely cannot answer (e.g. group discounts,
        cancellation policy for special cases, accessibility queries).
        NEVER use for: greetings, basic service/price info, availability, or bookings.

        Flow:
          1. Searches the knowledge base (threshold 0.7)
          2. If no answer found → creates a supervisor help request

        Args:
            question: The customer's question verbatim or closely paraphrased
        """
        logger.info("request_help: %s", question[:80])
        ud = self._userdata(context)
        booking = ud.current_booking

        # 1. Knowledge base lookup
        kb = await backend_client.search_knowledge_base(question, threshold=0.7)
        if kb.get("success") and kb.get("found"):
            logger.info("Answered from knowledge base")
            return kb["answer"]

        # 2. Escalate — build context payload
        booking_ctx = {}
        if booking:
            booking_ctx = {
                "customer_name": booking.customer_name,
                "phone_number": booking.phone_number,
                "service": booking.service,
                "appointment_date": booking.appointment_date,
                "appointment_time": booking.appointment_time,
            }

        try:
            room_name = get_job_context().room.name
        except Exception:
            room_name = None

        result = await backend_client.create_help_request(
            question=question,
            customer_name=str(booking.customer_name or "unknown"),
            customer_phone=str(booking.phone_number or "unknown"),
            booking_context=booking_ctx,
            room_name=room_name,
        )

        logger.info("Help request created: %s", result.get("request_id", "unknown"))

        return (
            "That's a great question — I've flagged it for my supervisor who will follow up "
            "with you shortly. Is there anything else I can help you with in the meantime?"
        )
