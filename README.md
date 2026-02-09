# Salon AI Agent

A sophisticated, voice-activated AI receptionist for salon appointment bookings. Built with **LiveKit**, **FastAPI**, and **Generative AI**, this agent handles real-time voice conversations to schedule appointments, answer questions, and manage customer data.

## Features

- **Natural Voice Interface**: Real-time, low-latency concurrent voice conversation using LiveKit.
- **Smart Scheduling**: Checks availability in real-time and books appointments with conflict prevention.
- **Context Awareness**: Remembers customer details (name, phone) throughout the conversation.
- **Robust Error Handling**: Gracefully handles invalid inputs, unavailable slots, and connection issues.
- **Human Handoff**: Escalates complex queries to a supervisor dashboard when the AI cannot help.
- **Knowledge Base**: RAG-powered FAQ system to answer general questions about the salon.
- **Modern Backend**: Fast and async API built with FastAPI and Firebase Firestore.

## Tech Stack

- **Voice/Real-time**: [LiveKit](https://livekit.io/) (Agents Framework)
- **Backend API**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database**: Firebase Firestore
- **Vector DB**: [Qdrant](https://qdrant.tech/) (for Knowledge Base)
- **STT (Speech-to-Text)**: Deepgram / Silero VAD
- **LLM (Intelligence)**: Llama 3 (via Groq)
- **TTS (Text-to-Speech)**: Cartesia

## Getting Started

### Prerequisites

- Python 3.10+
- [LiveKit Cloud](https://cloud.livekit.io/) project (or local instance)
- Firebase Admin credentials (service account JSON)
- API Keys for: Groq, Cartesia, Qdrant

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/salon-ai-agent.git
   cd salon-ai-agent
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file in the root directory:
   ```env
   # LiveKit Configuration
   LIVEKIT_URL=wss://your-project.livekit.cloud
   LIVEKIT_API_KEY=your_api_key
   LIVEKIT_API_SECRET=your_api_secret

   # AI Providers
   GROQ_API_KEY=your_groq_key
   Cartesia_API_KEY=your_cartesia_key
   
   # Database & Knowledge Base
   FIREBASE_CREDENTIALS_PATH=./saloon-ai-agent-firebase-adminsdk.json
   QDRANT_URL=your_qdrant_url
   QDRANT_API_KEY=your_qdrant_key
   
   # App Config
   BACKEND_URL=http://localhost:8000
   ```

### Running the Application

This project requires two processes running simultaneously: the FastAPI backend and the LiveKit Agent worker.

**1. Start the Backend API**
This handles the database, business logic, and booking management.
```bash
uvicorn app.main:app --reload --port 8000
```
*API Documentation will be available at http://localhost:8000/docs*

**2. Start the AI Agent**
This connects to LiveKit and handles the voice interactions.
```bash
python app/entrypoint.py start
```

### Testing the Agent
1. Go to the [LiveKit Agents Playground](https://agents-playground.livekit.io/).
2. Connect to your LiveKit instance.
3. You should see your agent online. Click "Connect" to start a voice call!

## Project Structure

```
├── app/
│   ├── agent/                 # LiveKit Agent Logic
│   │   ├── assistant.py       # Main Assistant Class & Tools
│   │   ├── prompts.py         # System Instructions & Prompts
│   ├── api/                   # FastAPI Routes
│   │   ├── routes/            # Endpoints (bookings, help, dashboard)
│   ├── core/                  # Config & Database setup
│   ├── models/                # Pydantic Models (Data Structures)
│   ├── services/              # Business Logic (Booking, Availability)
│   ├── utils/                 # Helper functions
│   ├── main.py                # FastAPI Entry Point
│   └── entrypoint.py          # LiveKit Agent Entry Point
├── data/                      # Static data (info.json)
├── requirements.txt           # Project Dependencies
└── README.md                  # Project Documentation
```

## Key API Endpoints

- **POST** `/api/bookings`: Create a new appointment.
- **GET** `/api/bookings/availability`: Check time slots.
- **POST** `/api/help-requests`: Submit a user question for human review.
- **GET** `/api/dashboard`: Context for the admin dashboard.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
