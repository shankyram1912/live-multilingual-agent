"""
Wrapper tools for Live API to interact with subagents.
The Live API requires tools, so we create tools, some of which may be internally delegate to subagents.
"""

import time
import asyncio
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from google.adk.runners import InMemoryRunner
from logger import log_tool_start, log_tool_complete

# REFERENCE CODE FOR FUTURE MULTI AGENT IMPL
#from subagents import flight_specialist, lifestyle_specialist

from google.genai import types

def _run_subagent_sync(agent, query: str, app_name: str) -> str:
    """
    Runs a subagent synchronously in a separate thread.
    This is necessary because asyncio.run() cannot be called from a running event loop.
    """
    try:
        # Create a fresh runner for this execution
        # We use app_name="agents" to match the LlmAgent origin and avoid warnings,
        # or we can accept the mismatch. The user requested a robust fix, so let's try to be clean.
        # However, if we use "agents" for all, we rely on unique session IDs (which create_session handles).
        runner = InMemoryRunner(app_name=app_name, agent=agent)
        
        # Build tool map
        tool_map = {}
        if hasattr(agent, 'tools') and agent.tools:
            for tool in agent.tools:
                # Handle both FunctionTool wrappers and raw callables
                if hasattr(tool, 'fn'):
                    tool_map[tool.name] = tool.fn
                elif callable(tool):
                    tool_map[tool.__name__] = tool
                elif hasattr(tool, 'name'):
                     # Generic tool object
                     tool_map[tool.name] = tool

        async def _run():
            # Create session
            session = await runner.session_service.create_session(
                app_name=app_name,
                user_id="user_123"
            )
            
            # Initial message
            current_message = types.Content(
                role="user",
                parts=[types.Part(text=query)]
            )

            final_response_text = ""
            
            # Turn loop (limit to 5 turns to prevent infinite loops)
            for _ in range(5):
                tool_responses = []
                has_tool_call = False
                
                async for event in runner.run_async(
                    user_id="user_123",
                    session_id=session.id,
                    new_message=current_message
                ):
                    # Accumulate text
                    if event.content and event.content.role == "model" and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                final_response_text += part.text
                    
                    # Handle Tool Calls
                    function_calls = event.get_function_calls()
                    if function_calls:
                        has_tool_call = True
                        for fc in function_calls:
                            tool_name = fc.name
                            tool_args = fc.args
                            tool_id = fc.id
                            
                            if tool_name in tool_map:
                                try:
                                    # Execute tool
                                    func = tool_map[tool_name]
                                    result = func(**tool_args)
                                    
                                    # Create response part
                                    tool_responses.append(types.Part(
                                        function_response=types.FunctionResponse(
                                            name=tool_name,
                                            id=tool_id,
                                            response={"result": str(result)}
                                        )
                                    ))
                                except Exception as e:
                                    print(f"Error executing tool {tool_name}: {e}")
                                    tool_responses.append(types.Part(
                                        function_response=types.FunctionResponse(
                                            name=tool_name,
                                            id=tool_id,
                                            response={"error": str(e)}
                                        )
                                    ))
                            else:
                                print(f"Tool {tool_name} not found in tool_map")
                                tool_responses.append(types.Part(
                                    function_response=types.FunctionResponse(
                                        name=tool_name,
                                        id=tool_id,
                                        response={"error": f"Tool {tool_name} not found"}
                                    )
                                ))

                # If no tool calls, we are done
                if not has_tool_call:
                    break
                
                # If we have tool responses, continue the loop with them
                if tool_responses:
                    current_message = types.Content(
                        role="tool",
                        parts=tool_responses
                    )
                    # Add separator if there was previous text
                    if final_response_text:
                        final_response_text += "\n"
                else:
                    break

            return final_response_text if final_response_text else "No information available."

        return asyncio.run(_run())
    except Exception as e:
        print(f"Error in subagent execution ({app_name}): {e}")
        raise e

# REFERENCE CODE FOR FUTURE MULTI AGENT IMPL

# async def consult_flight_specialist(destination: str, date: str) -> str:
#     """
#     Consults the Flight Specialist subagent for flight information.
#     This is a wrapper tool for the Live API to delegate to the Flight Specialist subagent.

#     Args:
#         destination: The destination city or airport.
#         date: The travel date (can be descriptive like "May" or specific like "2024-05-20").

#     Returns:
#         The Flight Specialist's response with flight information.
#     """
#     start_time = time.time()
#     log_tool_start("Flight Specialist", {"destination": destination, "date": date})

#     try:
#         query = f"Find flights to {destination} for {date}"
#         # Use asyncio.to_thread to run the sync subagent loop without blocking the main loop
#         result = await asyncio.to_thread(_run_subagent_sync, flight_specialist, query, "agents")
#     except Exception as e:
#         print(f"Error consulting Flight Specialist: {e}")
#         result = f"I couldn't get flight information for {destination} on {date} at the moment. Error: {str(e)}"

#     duration = time.time() - start_time
#     log_tool_complete("Flight Specialist", result, duration)

#     return result


# async def consult_lifestyle_specialist(query: str) -> str:
#     """
#     Consults the Lifestyle Specialist for destination/weather info.
#     """
#     start_time = time.time()
#     log_tool_start("Lifestyle Specialist", {"query": query})

#     try:
#         # Use asyncio.to_thread to run the sync subagent loop without blocking the main loop
#         result = await asyncio.to_thread(_run_subagent_sync, lifestyle_specialist, query, "agents")
#     except Exception as e:
#         print(f"Error consulting Lifestyle Specialist: {e}")
#         result = f"Error: {str(e)}"

#     duration = time.time() - start_time
#     log_tool_complete("Lifestyle Specialist", result, duration)

#     return result


# # Alternative synchronous implementation using mock data if ADK runners fail
# def consult_flight_specialist_fallback(destination: str, date: str) -> Dict[str, Any]:
#     """Fallback flight specialist using direct tool calls."""
#     from subagents import check_flight_availability

#     start_time = time.time()
#     log_tool_start("Flight Specialist", {"destination": destination, "date": date})

#     result = check_flight_availability(destination, date)

#     duration = time.time() - start_time
#     log_tool_complete("Flight Specialist", result, duration)

#     return result