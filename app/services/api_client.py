import os
import asyncio
from typing import Optional, Dict, Any
import aiohttp

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class BackendClient:
    """
    HTTP client for AI Agent to communicate with FastAPI backend.
    
    The agent uses this instead of direct Firebase calls, allowing:
    - Conflict-free booking (backend handles race conditions)
    - Centralized logging
    - Easy debugging
    - Supervisor dashboard integration
    """
    
    def __init__(self, base_url: str = ""):
        """
        Initialize the backend client.
        
        Args:
            base_url: Backend URL
        """
        self.base_url = base_url or os.getenv("BACKEND_URL", "http://localhost:8000")
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info(f"Backend client initialized: {self.base_url}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        backoff: float = 0.5,
    ) -> Dict[str, Any]:
        """Make HTTP request to backend with retry logic."""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        last_error = None
        for attempt in range(retries):
            try:
                async with session.request(
                    method,
                    url,
                    json=data,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    result = await response.json()
                    
                    if response.status >= 400:
                        error_detail = result.get("detail", "Unknown error")
                        logger.error(f"Backend error: {response.status} - {error_detail}")
                        return {"success": False, "error": error_detail, "status": response.status}
                    
                    return {"success": True, "data": result, "status": response.status}
                    
            except aiohttp.ClientError as e:
                last_error = str(e)
                logger.warning(f"Backend connection error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(backoff * (2 ** attempt))
            except Exception as e:
                logger.error(f"Backend request error: {e}")
                return {"success": False, "error": str(e), "status": 0}
        
        logger.error(f"Backend request failed after {retries} attempts")
        return {"success": False, "error": last_error or "Request failed", "status": 0}
    
    async def create_booking(
        self,
        customer_name: str,
        phone_number: str,
        service: str,
        appointment_date: str,
        appointment_time: str,
        price: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Create a new booking via backend.
        """
        data = {
            "customer_name": customer_name,
            "phone_number": phone_number,
            "service": service,
            "appointment_date": appointment_date,
            "appointment_time": appointment_time,
            "price": price,
        }
        
        result = await self._request("POST", "/api/bookings", data=data)
        
        if result["success"]:
            booking = result["data"]
            return {
                "success": True,
                "confirmation_number": booking.get("confirmation_number"),
                "booking": booking,
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to create booking"),
            }
    
    async def check_availability(
        self,
        date: str,
        time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check slot availability for a date.
        
        Args:
            date: The date to check (e.g., "January 30, 2026")
            time: Optional specific time to check (e.g., "10:00 AM")
        """
        params = {"date": date}
        if time:
            params["time"] = time
        
        result = await self._request("GET", "/api/availability", params=params)
        
        if result["success"]:
            data = result["data"]
            return {"success": True, **data}
        else:
            return {"success": False, "error": result.get("error")}
    
    async def cancel_booking(
        self,
        confirmation_number: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel a booking by confirmation number."""
        params = {}
        if reason:
            params["reason"] = reason
        
        result = await self._request(
            "DELETE",
            f"/api/bookings/{confirmation_number}",
            params=params,
        )
        
        return {
            "success": result["success"],
            "error": result.get("error") if not result["success"] else None,
        }

    
    async def search_knowledge_base(
        self,
        query: str,
        threshold: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Search knowledge base for similar questions.
        
        The agent should call this FIRST before escalating.
        """
        params = {"query": query, "threshold": threshold}
        result = await self._request("GET", "/api/knowledge-base/search", params=params)
        
        if result["success"]:
            data = result["data"]
            if data.get("found"):
                return {
                    "success": True,
                    "found": True,
                    "answer": data["answer"],
                    "question": data.get("question"),
                    "score": data.get("score"),
                }
            return {"success": True, "found": False}
        
        return {"success": False, "found": False, "error": result.get("error")}
    
    
    async def create_help_request(
        self,
        question: str,
        customer_name: str = "",
        customer_phone: str = "",
        booking_context: Optional[dict] = None,
        room_name: str = "",
    ) -> Dict[str, Any]:
        """
        Escalate a question to the supervisor.
        
        The agent calls this when:
        1. Knowledge base search returns no results
        2. Customer needs specialized help
        """
        data = {
            "question": question,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "booking_context": booking_context or {},
            "room_name": room_name,
        }
        
        result = await self._request("POST", "/api/help-requests", data=data)
        
        if result["success"]:
            return {
                "success": True,
                "request_id": result["data"]["id"],
            }
        
        return {"success": False, "error": result.get("error")}
        
    async def health_check(self) -> bool:
        """Check if backend is healthy."""
        result = await self._request("GET", "/health")
        return result["success"] and result.get("data", {}).get("status") == "healthy"


# Singleton instance

backend_client = BackendClient() #circular import