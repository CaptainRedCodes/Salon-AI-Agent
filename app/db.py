import os
import logging
import firebase_admin
from firebase_admin import credentials, firestore, db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FirebaseManager:
    """Manages Firebase connections and operations."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not FirebaseManager._initialized:
            self._initialize_firebase()
            FirebaseManager._initialized = True
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK."""
        try:
            if not firebase_admin._apps:
                cred_path = r"C:\Users\svmra\OneDrive\Documents\projects\FrontDesk\saloon-ai-agent-firebase-adminsdk-fbsvc-5d98757c45.json"
                if cred_path and os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    logger.info("Firebase initialized with service account file")
                else:
                    firebase_admin.initialize_app()
                    logger.info("Firebase initialized with default credentials")
                
                self.db = firestore.client()
                logger.info("Firestore client initialized successfully")
            else:
                self.db = firestore.client()
                logger.info("Using existing Firebase app")
                
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    
    def get_firestore_client(self):
        """Get Firestore client instance."""
        return self.db
