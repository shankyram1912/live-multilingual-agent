import os
from dotenv import load_dotenv

import logging

logger = logging.getLogger(__name__)

# Load environment variables early
load_dotenv(override=True)

class AgentConfig:
    """
    Manages environment-based routing between Gemini AI Studio 
    and Vertex AI models dynamically for the Live Translator.
    """
    def __init__(self):
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "false":
            
            logger.info("Need to route to GEMINI API (Google AI Studio).")
            
            self.ORCHESTRATOR_MODEL = os.getenv(
                "LIVEAGENT_GEMINI_MODEL", 
                "gemini-3.1-flash-live-preview"
            )            
            
            self.IS_VERTEX_AI_LIVE_API = False
            
        else:
            logger.info("Need to route to VERTEX AI API.")
            
            self.ORCHESTRATOR_MODEL = os.getenv(
                "LIVEAGENT_VERTEXAI_MODEL", 
                "gemini-live-2.5-flash-native-audio"
            )
            
            self.IS_VERTEX_AI_LIVE_API = True

# App Configuration
APP_NAME = "despina_multilingual_agent"

# Initialize a singleton configuration object for importing across the app
agent_config = AgentConfig()