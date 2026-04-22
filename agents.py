from google.adk.agents import LlmAgent
import config

# REFERENCE CODE FOR FUTURE MULTI AGENT IMPL
# from tools import consult_flight_specialist, consult_lifestyle_specialist

# Define Root Agent (Despina) with wrapper tools for Live API
despina_agent = LlmAgent(
    name="Despina",
    model=config.ORCHESTRATOR_MODEL,
    instruction=config.DESPINA_INSTRUCTION,
    tools=[]  # Wrapper tools for subagents
    # tools=[consult_flight_specialist, consult_lifestyle_specialist]  # Wrapper tools for subagents
)