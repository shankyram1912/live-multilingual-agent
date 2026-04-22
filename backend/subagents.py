# from google.adk.agents import LlmAgent
# from google.adk.tools import google_search
# import config

# # Flight tools - mock flight database
# def check_flight_availability(destination: str, date: str) -> dict:
#     """Check flight availability and prices."""
#     import time

#     # Mock flight database
#     result = {}
#     destination_lower = destination.lower()
#     date_lower = date.lower()

#     if "japan" in destination_lower or "tokyo" in destination_lower:
#         if "may" in date_lower or "-05-" in date:
#             result = {
#                 "flight": "ANA NH102",
#                 "price": 850,
#                 "currency": "USD",
#                 "seats": 4,
#                 "airline": "ANA",
#                 "departure": "LAX",
#                 "arrival": "NRT",
#                 "duration": "11h 30m",
#                 "class": "Economy"
#             }
#         else:
#             result = {
#                 "flight": "JAL JL006",
#                 "price": 1200,
#                 "currency": "USD",
#                 "seats": 2,
#                 "airline": "JAL",
#                 "departure": "LAX",
#                 "arrival": "NRT",
#                 "duration": "11h 45m",
#                 "class": "Economy"
#             }
#     elif "united" in destination_lower:
#         result = {
#             "flight": "UA837",
#             "price": 920,
#             "currency": "USD",
#             "seats": 8,
#             "airline": "United",
#             "departure": "LAX",
#             "arrival": "NRT",
#             "duration": "12h 15m",
#             "class": "Economy Plus"
#         }
#     else:
#         result = {
#             "flight": "UA100",
#             "price": 450,
#             "currency": "USD",
#             "seats": 10,
#             "airline": "United",
#             "departure": "LAX",
#             "arrival": destination.upper()[:3],
#             "duration": "5h 30m",
#             "class": "Economy"
#         }

#     return result

# # Create Flight Specialist Subagent
# flight_specialist = LlmAgent(
#     name="flight_specialist",
#     model=config.SUBAGENT_MODEL,
#     instruction=config.FLIGHT_SPECIALIST_INSTRUCTION,
#     tools=[check_flight_availability]
# )

# # Create Lifestyle Specialist Subagent
# lifestyle_specialist = LlmAgent(
#     name="lifestyle_specialist",
#     model=config.SUBAGENT_MODEL,
#     instruction=config.LIFESTYLE_SPECIALIST_INSTRUCTION,
#     tools=[google_search]  # Using native Google search tool
# )