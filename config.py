import os
from dotenv import load_dotenv

# Load environment variables early
load_dotenv(override=True)
class AgentConfig:
    """
    Manages environment-based routing between Gemini AI Studio 
    and Vertex AI models dynamically for the Live Translator.
    """
    def __init__(self):
        use_gemini_env = os.getenv("LIVEAGENT_USE_GEMINI", "false").lower()
        self.use_gemini = use_gemini_env in ("true", "1", "yes", "y")

        if self.use_gemini:
            # 1. Sanitize the environment to force Google AI Studio API-Key routing
            os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("GOOGLE_CLOUD_LOCATION", None)
            os.environ.pop("GOOGLE_API_KEY", None)

            # 2. Patch ADK to use v1beta for Gemini API live connections for 3.1 Flash.
            # ADK (as of 1.32.0) still defaults `_live_api_version` to "v1alpha" for AI Studio, 
            # but `gemini-3.1-flash-live-preview` is only served on v1beta.
            from google.adk.models.google_llm import Gemini
            Gemini._live_api_version = "v1beta"

            # Set the AI Studio model
            self.ORCHESTRATOR_MODEL = os.getenv(
                "LIVEAGENT_GEMINI_MODEL", 
                "gemini-3.1-flash-live-preview"
            )
        else:
            # Set the Vertex AI model
            self.ORCHESTRATOR_MODEL = os.getenv(
                "LIVEAGENT_VERTEXAI_MODEL", 
                "gemini-live-2.5-flash-native-audio"
            )
            

# App Configuration
APP_NAME = "despina_multilingual_agent"

# Initialize a singleton configuration object for importing across the app
agent_config = AgentConfig()