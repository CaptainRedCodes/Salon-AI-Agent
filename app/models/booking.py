from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class CustomerDetail(BaseModel):
    """Customer information model."""
    customer_name: Optional[str] = Field(default=None, description="Customer's full name")
    phone_number: Optional[str] = Field(default=None, description="Customer's 10-digit phone number")


class CollectCustomerInformationArgs(BaseModel):
    """Args for collect_customer_information tool."""
    customer_name: Optional[str] = Field(
        default=None, 
        description="The customer's full name"
    )
    phone_number: Optional[str] = Field(
        default=None, 
        description="The customer's 10-digit phone number"
    )

class BookingCreate(BaseModel):
    customer_name: Optional[str] = None
    service: Optional[str] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    price: Optional[float] = None
    phone_number: Optional[str] = None

    @field_validator("phone_number")
    def validate_phone(cls, v):
        if v:
            clean = ''.join(filter(str.isdigit, v))
            if len(clean) != 10:
                raise ValueError("Phone number must be exactly 10 digits")
            return clean
        return v

class BookingUpdate(BaseModel):
    customer_name: Optional[str] = Field(None, description="Customer's full name")
    phone_number: Optional[str] = Field(None, description="Customer's 10-digit phone number")
    service: Optional[str] = Field(None, description="Service name (must match available services)")
    appointment_date: Optional[str] = Field(None, description="Date for appointment")
    appointment_time: Optional[str] = Field(None, description="Time for appointment")

    @field_validator("phone_number")
    def validate_phone(cls, v):
        if v:
            clean = ''.join(filter(str.isdigit, v))
            if len(clean) != 10:
                raise ValueError("Phone number must be exactly 10 digits")
            return clean
        return v

class BookingView(BaseModel):
    id: str = Field(..., description="Firestore document ID")
    confirmation_number: str = Field(..., description="Generated booking ID")
    customer_name: str
    service: str
    appointment_date: str
    appointment_time: str
    phone_number: Optional[str]
    price: float
    status: str
    created_at: datetime
    updated_at: datetime
    cancelled: bool
    cancellation_reason: Optional[str]

class BookingResponse(BaseModel):
    """Response after booking is created."""
    id: str
    confirmation_number: str
    customer_name: str
    service: str
    appointment_date: str
    appointment_time: str
    phone_number: str
    price: Optional[float]
    status: str
    created_at: datetime
    cancelled: bool = False


class BookingContext(BaseModel):
    """Context for current booking in progress"""
    customer_name: Optional[str] = None
    phone_number: Optional[str] = None
    service: Optional[str] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    price: Optional[float] = None
    confirmed: bool = False

    def is_complete(self) -> bool:
        """Check if all required fields are present"""
        return all([
            self.customer_name,
            self.phone_number,
            self.service,
            self.appointment_date,
            self.appointment_time
        ])

    def get_summary(self) -> str:
        """Get a summary of the current booking"""
        if not self.is_complete():
            return "Incomplete booking information"

        return (
            f"Customer: {self.customer_name}\n"
            f"Phone: {self.phone_number}\n"
            f"Service: {self.service}\n"
            f"Date: {self.appointment_date}\n"
            f"Time: {self.appointment_time}\n"
            f"Price: ₹{self.price}"
        )
    