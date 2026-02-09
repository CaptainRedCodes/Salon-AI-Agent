from pydantic import BaseModel, Field
from typing import Optional


class GetDateTimeArgs(BaseModel):
    """Args for get_current_date_and_time tool."""
    format: Optional[str] = Field(
        default=None, 
        description="Optional format preference for the date/time response"
    )


class SelectServiceArgs(BaseModel):
    """Args for select_service tool."""
    service: str = Field(
        ..., 
        description="The name of the salon service to select (e.g., 'haircut', 'hair coloring')"
    )


class CheckAvailabilityArgs(BaseModel):
    """Args for check_availability tool."""
    date: str = Field(
        ..., 
        description="The date to check availability for (e.g., 'January 30, 2026', 'tomorrow')"
    )
    time: str = Field(
        default="unknown", 
        description="Optional specific time slot to check (e.g., '10:00 AM')"
    )


class ScheduleAppointmentArgs(BaseModel):
    """Args for schedule_appointment tool."""
    appointment_date: str = Field(
        ..., 
        description="The date for the appointment (e.g., 'January 30, 2026')"
    )
    appointment_time: str = Field(
        ..., 
        description="The time slot for the appointment (e.g., '10:00 AM')"
    )


class GetBookingSummaryArgs(BaseModel):
    """Args for get_booking_summary tool."""
    include_price: Optional[bool] = Field(
        default=True, 
        description="Whether to include the price in the booking summary"
    )


class ConfirmBookingArgs(BaseModel):
    """Args for confirm_booking tool."""
    confirmed: bool = Field(
        default=True, 
        description="Whether the customer confirms the booking"
    )


class ModifyBookingDetailArgs(BaseModel):
    """Args for modify_booking_detail tool."""
    field: str = Field(
        ..., 
        description="The booking field to modify (name, phone, service, date, or time)"
    )
    new_value: str = Field(
        ..., 
        description="The new value for the specified field"
    )


class GetSalonInfoArgs(BaseModel):
    """Args for get_salon_information tool."""
    info_type: str = Field(
        default="all", 
        description="Type of information to retrieve (services, hours, contact, location, or all)"
    )


class RequestHelpArgs(BaseModel):
    """Args for request_help tool."""
    question: str = Field(
        ..., 
        description="The customer's question that needs human assistance"
    )
