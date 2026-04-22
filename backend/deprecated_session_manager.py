import asyncio
import json
import time
import logging
import traceback
import sys

from fastapi import WebSocket, WebSocketDisconnect

from google.genai import types
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode

from agents import despina_agent
from logger import log_queue, log_tool_start, log_tool_complete
import config

logger = logging.getLogger(__name__)

# Mapping of tool names to subagent names
TOOL_TO_SUBAGENT = {
    # "consult_flight_specialist": "Flight Specialist",
    # "consult_lifestyle_specialist": "Lifestyle Specialist"
}

class SessionManager:
    def __init__(self, websocket: WebSocket, session: Session, app_name: str, user_id: str, session_id: str):
        self.websocket = websocket
        self.session = session
        self.app_name = app_name
        self.user_id = user_id
        self.session_id = session_id
        
        self.runner = InMemoryRunner(app_name, agent=despina_agent)
        
        self.live_request_queue = None
        self.input_task = None
        self.log_task = None        

        # Simplified timing variables
        self.user_input_end_time = None  # When last user byte received
        self.first_tool_start_time = None  # When first tool execution started
        self.last_tool_end_time = None  # When last tool execution ended
        self.current_tool_start_times = {}  # Track individual tool start times

        # State flags
        self.has_new_user_input = False
        self.response_in_progress = False
        self.waiting_for_tools = False  # Track if we're waiting for tool completion
        self.ttfb_recorded = False  # Track if we've already recorded TTFB for this turn
        self.tool_call_seen = False  # Track if we've seen a tool call this turn
        self.vad_silence_duration_ms = 1000  # Default fallback - actual value comes from frontend

    async def start(self):
        """Starts the ADK Live session and manages the bi-directional stream."""
        log_task = None
        try:
            # 1. Wait for initial setup message from client
            setup_msg = await self.websocket.receive_text()
            setup_data = json.loads(setup_msg)
            logger.info("Initial setup received: {setup_data}")

            # Extract settings
            setup_config = setup_data.get("setup", {})
            voice_name = setup_config.get("voice_name", "Despina")
            vad_settings = setup_config.get("vad_settings", {})
            self.vad_silence_duration_ms = vad_settings.get("silence_duration_ms", 1000)
            logger.info("VAD silence duration set to {self.vad_silence_duration_ms}ms")

            # Create Live Request Queue
            self.live_request_queue = LiveRequestQueue()

            # Configure Speech Config
            speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            )

            # Configure Run Settings
            # RunConfig with transcription enabled
            response_modalities = ["AUDIO"]

            run_config = RunConfig(
                response_modalities=response_modalities,
                speech_config=speech_config,
                streaming_mode=StreamingMode.BIDI,
                output_audio_transcription=types.AudioTranscriptionConfig(), 
                input_audio_transcription=types.AudioTranscriptionConfig(),
                realtime_input_config=types.RealtimeInputConfig(
                    turn_coverage=types.TurnCoverage.TURN_INCLUDES_ALL_INPUT
                )
            )

            # 2. Start the Runner (returns an async generator of events)
            live_events = self.runner.run_live(
                run_config=run_config,
                session=self.session,
                live_request_queue=self.live_request_queue
            )

            # 3. Start concurrent input listening
            # Start input loop
            self.input_task = asyncio.create_task(self.receive_from_client())

            # Start log streaming loop
            log_task = asyncio.create_task(self.stream_logs())

            # 5. Process AI output events
            # Process output events
            async for event in live_events:
                await self.process_event(event)

            # If loop ends, cancel tasks
            self.input_task.cancel()
            log_task.cancel()
        
        except WebSocketDisconnect:
            logger.info(f"Client {self.user_id} disconnected normally.")
        except Exception as e:
            logger.error(f"Session error: {e}")
            traceback.print_exc()
            await self.websocket.close()
        finally:
            # Bulletproof Teardown
            logger.info("Initiating session teardown...")
            if self.input_task:
                self.input_task.cancel()
            if self.log_task:
                self.log_task.cancel()
            if self.live_request_queue:
                self.live_request_queue.close()
                logger.info("LiveRequestQueue closed safely.")

    async def process_event(self, event):
        """Process different types of events from the ADK Live stream."""
        try:
            is_partial = getattr(event, "partial", False)

            # Log every event type for debugging
            event_types = []
            if getattr(event, "tool_call", None):
                event_types.append("tool_call")
            if getattr(event, "content", None):
                event_types.append("content")
                # Check if content has function_calls
                content = getattr(event, "content", None)
                if content and hasattr(content, 'parts'):
                    for part in content.parts:
                        if hasattr(part, 'function_call'):
                            event_types.append("content_has_function_call")
                            break
            if getattr(event, "tool_response", None):
                event_types.append("tool_response")
            if getattr(event, "server_content", None):
                event_types.append("server_content")
            if hasattr(event, 'function_calls'):
                event_types.append("has_function_calls")
            if hasattr(event, 'get_function_calls'):
                event_types.append("has_get_function_calls_method")

            if event_types:
                sys.stderr.write(f"[EVENT] Types: {', '.join(event_types)}, Partial: {is_partial}\n")
                sys.stderr.flush()

            # IMPORTANT: Check for tool calls in multiple ways
            # Method 1: Direct tool_call attribute
            tool_call = getattr(event, "tool_call", None)
            if tool_call:
                # Set the flag IMMEDIATELY when we detect a tool call
                if not self.waiting_for_tools:
                    self.waiting_for_tools = True
                    self.tool_call_seen = True
                    sys.stderr.write(f"[TOOL] Tool call detected via tool_call attribute\n")
                    sys.stderr.flush()
                await self.handle_tool_call(tool_call)

            # Method 2: Check get_function_calls() method if it exists
            if hasattr(event, 'get_function_calls') and callable(getattr(event, 'get_function_calls')):
                function_calls = event.get_function_calls()
                if function_calls:
                    if not self.waiting_for_tools:
                        self.waiting_for_tools = True
                        self.tool_call_seen = True
                        sys.stderr.write(f"[TOOL] Function calls detected via get_function_calls(): {len(function_calls)} calls\n")
                        sys.stderr.flush()
                    # Process these function calls
                    for fc in function_calls:
                        await self.handle_tool_call_from_function(fc)

            # Handle server_content events (for transcriptions and turn completion)
            server_content = getattr(event, "server_content", None)
            if server_content:
                await self.handle_server_content(server_content, is_partial=is_partial)
            else:
                # Fallback: Check if event itself has transcription attributes (flattened structure)
                await self.handle_server_content(event, is_partial=is_partial)

            # Handle content events (model output with audio/text)
            content = getattr(event, "content", None)
            if content:
                # Method 3: Check for function calls within content parts
                if hasattr(content, 'parts') and content.parts:
                    for part in content.parts:
                        if hasattr(part, 'function_call') and part.function_call is not None:
                            if not self.waiting_for_tools:
                                self.waiting_for_tools = True
                                self.tool_call_seen = True
                                sys.stderr.write(f"[TOOL] Function call found in content part\n")
                                sys.stderr.flush()
                            # Handle this function call
                            await self.handle_tool_call_from_function(part.function_call)

                await self.handle_content(content)

            # Handle tool responses (our simulated subagent responses)
            tool_response = getattr(event, "tool_response", None)
            if tool_response:
                await self.handle_tool_response(tool_response)

        except Exception as e:
            print(f"Error processing event: {e}")

    async def handle_server_content(self, server_content, is_partial=False):
        """Handle server content events for transcriptions."""
        # Check for streaming user transcription
        input_transcription = getattr(server_content, "input_audio_transcription", None)
        if not input_transcription:
             input_transcription = getattr(server_content, "input_transcription", None)

        if input_transcription and hasattr(input_transcription, 'text') and input_transcription.text:
            # CRITICAL: First user transcription means new user speech detected
            # Reset timing flags here (server's VAD has detected actual speech, not noise)
            if not self.has_new_user_input:
                self.user_input_end_time = time.time()
                self.has_new_user_input = True
                self.ttfb_recorded = False
                sys.stderr.write(f"[USER_SPEECH] User speech detected, reset timing at {self.user_input_end_time}\n")
                sys.stderr.flush()

            # print(f"User streaming transcript: {input_transcription.text}")
            await self.websocket.send_text(json.dumps({
                "type": "transcript_partial",
                "text": input_transcription.text,
                "role": "user"
            }))

        # Check for agent transcription (output_transcription on event)
        output_transcription = getattr(server_content, "output_audio_transcription", None)
        if not output_transcription:
            output_transcription = getattr(server_content, "output_transcription", None)

        if output_transcription and hasattr(output_transcription, 'text') and output_transcription.text:
            # Determine type based on is_partial flag
            msg_type = "transcript_partial" if is_partial else "transcript"
            # print(f"Agent transcript ({msg_type}): {output_transcription.text}")
            await self.websocket.send_text(json.dumps({
                "type": msg_type,
                "text": output_transcription.text,
                "role": "agent"
            }))

        # Check for turn completion with transcriptions
        turn_complete = getattr(server_content, "turn_complete", None)
        if turn_complete:
            sys.stderr.write(f"[TURN] Turn complete. Resetting state.\n")
            sys.stderr.flush()

            # CRITICAL FIX: Record TTFB on turn_complete if we haven't yet
            # This handles the race condition where tool completes but log_queue
            # entry hasn't been processed before turn_complete arrives
            if not self.ttfb_recorded and self.user_input_end_time and self.has_new_user_input:
                current_time = time.time()
                vad_offset = self.vad_silence_duration_ms / 1000.0
                adjusted_start_time = self.user_input_end_time - vad_offset
                total_latency = current_time - adjusted_start_time

                tool_execution_time = 0
                if self.first_tool_start_time and self.tool_call_seen:
                    # Estimate tool end time as current time
                    tool_execution_time = current_time - self.first_tool_start_time

                sys.stderr.write(f"[TTFB] Recording on turn_complete (tool_call_seen={self.tool_call_seen})\n")
                sys.stderr.write(f"[TTFB] Total latency: {total_latency:.3f}s (Tool time: {tool_execution_time:.3f}s)\n")
                sys.stderr.flush()

                await self.websocket.send_text(json.dumps({
                    "type": "ttfb",
                    "duration": total_latency
                }))
                self.ttfb_recorded = True

            self.response_in_progress = False
            # Reset timing and state for next turn
            # IMPORTANT: Don't reset user_input_end_time, has_new_user_input, or ttfb_recorded here!
            # These should ONLY be reset when we actually receive new user input
            # This prevents agent continuation turns from overwriting the tool-turn TTFB
            self.first_tool_start_time = None
            self.last_tool_end_time = None
            self.waiting_for_tools = False
            self.tool_call_seen = False
            # DO NOT reset ttfb_recorded here - only reset on new user input!
            self.current_tool_start_times.clear()

            # User input transcription
            input_transcription = getattr(turn_complete, "input_audio_transcription", None)
            if input_transcription and hasattr(input_transcription, 'text') and input_transcription.text:
                # print(f"User transcript: {input_transcription.text}")
                # Send user transcript to frontend
                await self.websocket.send_text(json.dumps({
                    "type": "transcript",
                    "text": input_transcription.text,
                    "role": "user"
                }))

            # Agent output transcription (complete)
            output_transcription = getattr(turn_complete, "output_audio_transcription", None)
            if output_transcription and hasattr(output_transcription, 'text') and output_transcription.text:
                # print(f"Agent transcript: {output_transcription.text}")
                await self.websocket.send_text(json.dumps({
                    "type": "transcript",
                    "text": output_transcription.text,
                    "role": "agent"
                }))

        # Check for model_turn (streaming transcriptions)
        model_turn = getattr(server_content, "model_turn", None)
        if model_turn:
            parts = getattr(model_turn, "parts", [])
            for part in parts:
                if hasattr(part, 'text') and part.text:
                    # Streaming agent transcript
                    # print(f"Agent streaming transcript: {part.text}")
                    await self.websocket.send_text(json.dumps({
                        "type": "transcript_partial",
                        "text": part.text,
                        "role": "agent"
                    }))

    async def handle_content(self, content):
        """Handle content events (audio and text)."""
        role = "agent"
        if hasattr(content, "role") and content.role == "user":
            role = "user"

        parts = getattr(content, "parts", [])
        if parts:
            for part in parts:
                has_content = False

                # Handle audio data
                if hasattr(part, 'inline_data') and part.inline_data:
                    if hasattr(part.inline_data, 'data') and part.inline_data.data:
                        has_content = True
                        await self.websocket.send_bytes(part.inline_data.data)

                # Handle text content (this might be transcription or direct text)
                if hasattr(part, 'text') and part.text:
                    has_content = True
                    # Send as text message (this supplements transcription)
                    await self.websocket.send_text(json.dumps({
                        "text": part.text,
                        "role": role
                    }))

                # TTFB Recording Logic:
                # - Only record TTFB once per turn (check ttfb_recorded flag)
                # - For standard responses: record immediately on first content
                # - For tool responses: record after tools complete
                if has_content and role == "agent" and self.has_new_user_input and not self.ttfb_recorded:
                    # If NO tools were called, record TTFB immediately (standard response)
                    # If tools WERE called, wait for them to complete
                    if not self.tool_call_seen:
                        # Standard response - no tools involved
                        if self.user_input_end_time:
                            current_time = time.time()
                            vad_offset = self.vad_silence_duration_ms / 1000.0
                            adjusted_start_time = self.user_input_end_time - vad_offset
                            total_latency = current_time - adjusted_start_time

                            sys.stderr.write(f"[TTFB] Recording for STANDARD response (no tools)\n")
                            sys.stderr.write(f"[TTFB] Total latency: {total_latency:.3f}s\n")
                            sys.stderr.flush()

                            await self.websocket.send_text(json.dumps({
                                "type": "ttfb",
                                "duration": total_latency
                            }))
                            self.ttfb_recorded = True
                            self.has_new_user_input = False
                            self.response_in_progress = True
                    elif self.waiting_for_tools:
                        # Tool response - wait for tools to complete
                        sys.stderr.write(f"[TTFB] Content received but waiting for tools to complete\n")
                        sys.stderr.flush()
                    # If tool_call_seen but not waiting_for_tools, the tool already completed

    async def handle_tool_call_from_function(self, fc):
        """Handle a single function call."""
        # Return early if fc is None
        if fc is None:
            sys.stderr.write(f"[WARNING] handle_tool_call_from_function called with None\n")
            sys.stderr.flush()
            return

        tool_name = fc.name if hasattr(fc, 'name') else "Unknown Tool"
        sys.stderr.write(f"[DEBUG] Tool call: {tool_name}\n")
        sys.stderr.flush()

        # Map tool name to subagent name
        subagent_name = TOOL_TO_SUBAGENT.get(tool_name, tool_name)

        # Extract arguments and convert to plain dict for JSON serialization
        args = {}
        if hasattr(fc, 'args') and fc.args:
            # Convert to plain dict if it's a special object
            args = dict(fc.args) if not isinstance(fc.args, dict) else fc.args
        elif hasattr(fc, 'parameters') and fc.parameters:
            args = dict(fc.parameters) if not isinstance(fc.parameters, dict) else fc.parameters

        # Track start time for this specific tool
        current_time = time.time()
        self.current_tool_start_times[tool_name] = current_time

        # Track the first tool start time
        if self.first_tool_start_time is None:
            self.first_tool_start_time = current_time
            sys.stderr.write(f"[TOOL] First tool execution started at {self.first_tool_start_time}\n")
            sys.stderr.flush()

        # Send subagent start event to frontend
        try:
            message = json.dumps({
                "type": "subagent_start",
                "agent": subagent_name,
                "args": args
            })
            await self.websocket.send_text(message)
            sys.stderr.write(f"[DEBUG] Sent subagent_start: {subagent_name}\n")
            sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"[ERROR] Failed to send subagent_start: {e}\n")
            sys.stderr.flush()

        print(f"Subagent {subagent_name} started with args: {args}")

    async def handle_tool_call(self, tool_call):
        """Handle tool call events (our simulated subagent calls)."""
        # print(f"Tool call: {tool_call}")
        function_calls = getattr(tool_call, "function_calls", [])

        for fc in function_calls:
            tool_name = fc.name if hasattr(fc, 'name') else "Unknown Tool"

            # Map tool name to subagent name
            subagent_name = TOOL_TO_SUBAGENT.get(tool_name, tool_name)

            # Extract arguments
            args = {}
            if hasattr(fc, 'args'):
                args = fc.args
            elif hasattr(fc, 'parameters'):
                args = fc.parameters

            # Track start time for this specific tool
            current_time = time.time()
            self.current_tool_start_times[tool_name] = current_time

            # Track the first tool start time
            if self.first_tool_start_time is None:
                self.first_tool_start_time = current_time
                sys.stderr.write(f"[TOOL] First tool execution started at {self.first_tool_start_time}\n")
                sys.stderr.flush()

            # Send subagent start event to frontend
            await self.websocket.send_text(json.dumps({
                "type": "subagent_start",
                "agent": subagent_name,
                "args": args
            }))

            print(f"Subagent {subagent_name} started with args: {args}")

    async def handle_tool_response(self, tool_response):
        """Handle tool response events (our simulated subagent responses)."""
        # print(f"Tool response: {tool_response}")
        function_responses = getattr(tool_response, "function_responses", [])

        for fr in function_responses:
            tool_name = fr.name if hasattr(fr, 'name') else "Unknown Tool"

            # Map tool name to subagent name
            subagent_name = TOOL_TO_SUBAGENT.get(tool_name, tool_name)

            # Extract result
            result = None
            if hasattr(fr, 'response'):
                result = fr.response
            elif hasattr(fr, 'result'):
                result = fr.result

            # Calculate duration
            duration = 0.5  # Default
            current_time = time.time()
            if tool_name in self.current_tool_start_times:
                duration = current_time - self.current_tool_start_times[tool_name]
                del self.current_tool_start_times[tool_name]

            # Track the last tool end time
            self.last_tool_end_time = current_time

            # Check if all tools have completed
            if not self.current_tool_start_times:  # No more tools running
                self.waiting_for_tools = False
                sys.stderr.write(f"[TOOL] All tools completed at {self.last_tool_end_time}\n")
                sys.stderr.flush()

                # After tools complete, record TTFB if we haven't yet
                if not self.ttfb_recorded and self.user_input_end_time and self.has_new_user_input:
                    current_time = time.time()
                    vad_offset = self.vad_silence_duration_ms / 1000.0
                    adjusted_start_time = self.user_input_end_time - vad_offset
                    total_latency = current_time - adjusted_start_time

                    tool_execution_time = 0
                    if self.first_tool_start_time and self.last_tool_end_time:
                        tool_execution_time = self.last_tool_end_time - self.first_tool_start_time

                    sys.stderr.write(f"[TTFB] Recording AFTER tool completion\n")
                    sys.stderr.write(f"[TTFB] Total latency: {total_latency:.3f}s (Tool time: {tool_execution_time:.3f}s)\n")
                    sys.stderr.flush()

                    await self.websocket.send_text(json.dumps({
                        "type": "ttfb",
                        "duration": total_latency
                    }))
                    self.ttfb_recorded = True
                    self.has_new_user_input = False

            # Format result for display
            if isinstance(result, dict):
                result_str = json.dumps(result, indent=2)
            else:
                result_str = str(result)

            # Send subagent complete event to frontend
            await self.websocket.send_text(json.dumps({
                "type": "subagent_complete",
                "agent": subagent_name,
                "result": result_str,
                "duration": duration
            }))

            print(f"Subagent {subagent_name} completed in {duration:.2f}s")

            # Special handling for flight data - check if result contains flight information
            if tool_name in ["consult_flight_specialist", "check_flight_availability_subagent"]:
                # Parse result for flight data if it's a string response
                if isinstance(result, str) and any(keyword in result.lower() for keyword in ["flight", "price", "airline"]):
                    # Extract flight details from the response (if structured)
                    # For now, just signal that flight data was discussed
                    pass  # The subagent response will contain the flight details in text form

    async def receive_from_client(self):
        """Receives audio/text from the WebSocket client and pushes to LiveRequestQueue."""
        try:
            while True:
                message = await self.websocket.receive()

                if "bytes" in message:
                    # Raw audio bytes - just send them, don't reset timing here
                    # Timing will be reset when we get actual user transcription from server's VAD
                    self.live_request_queue.send_realtime(
                        types.Blob(data=message["bytes"], mime_type="audio/pcm;rate=16000")
                    )

                elif "text" in message:
                    data = json.loads(message["text"])
                    if "text" in data:
                        # Use send_content for text - timing will be reset on user turn completion
                        self.live_request_queue.send_content(
                            types.Content(parts=[types.Part(text=data["text"])])
                        )

        except Exception as e:
            print(f"ERROR: Client receive loop failed: {e}")
            if self.live_request_queue:
                self.live_request_queue.close()

    async def stream_logs(self):
        """Streams logs from the queue to the websocket."""
        try:
            while True:
                log_entry = await log_queue.get()

                # Check if this is a tool completion event
                if log_entry.get("type") == "subagent_complete":
                    # Tool has completed! Use the timestamp from the log entry
                    tool_completion_time = log_entry.get("timestamp", time.time())
                    self.last_tool_end_time = tool_completion_time
                    self.waiting_for_tools = False
                    sys.stderr.write(f"[TOOL] Tool completed (via log_queue): {log_entry.get('agent')} at {tool_completion_time}\n")
                    sys.stderr.flush()

                    # Record TTFB now that tool is complete
                    if not self.ttfb_recorded and self.user_input_end_time and self.has_new_user_input:
                        # Use the tool completion time (not current time!) for accurate TTFB
                        vad_offset = self.vad_silence_duration_ms / 1000.0
                        adjusted_start_time = self.user_input_end_time - vad_offset
                        total_latency = tool_completion_time - adjusted_start_time

                        tool_execution_time = 0
                        if self.first_tool_start_time and self.last_tool_end_time:
                            tool_execution_time = self.last_tool_end_time - self.first_tool_start_time

                        sys.stderr.write(f"[TTFB] Recording after tool completion (via log_queue)\n")
                        sys.stderr.write(f"[TTFB] user_input_end: {self.user_input_end_time}, tool_complete: {tool_completion_time}\n")
                        sys.stderr.write(f"[TTFB] Total latency: {total_latency:.3f}s (Tool time: {tool_execution_time:.3f}s)\n")
                        sys.stderr.flush()

                        await self.websocket.send_text(json.dumps({
                            "type": "ttfb",
                            "duration": total_latency
                        }))
                        self.ttfb_recorded = True
                        self.has_new_user_input = False

                # Send the log entry to the frontend
                await self.websocket.send_text(json.dumps(log_entry))
                log_queue.task_done()
        except asyncio.CancelledError:
            pass