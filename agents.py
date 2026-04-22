from google.adk.agents import LlmAgent
import config

from tools import travel_risk_assessment

# Define Root Agent (Despina) with wrapper tools for Live API
despina_agent = LlmAgent(
    name="Despina",
    model=config.ORCHESTRATOR_MODEL,
    instruction=config.DESPINA_INSTRUCTION,
    tools=[travel_risk_assessment]  # Wrapper tools for subagents
)