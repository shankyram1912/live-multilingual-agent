import json
import logging

logger = logging.getLogger(__name__)

def travel_risk_assessment(country_code: str) -> str:
    """
    Call this tool whenever the user specifically raised questions on safety bulletins or travel advisories to a specific country.
    
    Args:
        country_code: The 2-letter ISO 3166-1 alpha-2 country code (e.g., 'JP', 'FR', 'BR').
    """
    
    print("\n" + "="*50)
    print(f"🛠️ TOOL CALL STARTING: travel_risk_assessment - {country_code}")
    print("="*50 + "\n", flush=True)
    
    # Clean the input to ensure it matches the index keys
    code = country_code.strip().upper()
    
    # 30-Country Hardcoded Index
    advisories = {
        # --- VERY SAFE ---
        "JP": {"level": "VERY SAFE", "description": "Consistently ranks among the safest countries globally. Very low violent crime rates, though travelers should remain aware of natural disaster protocols (earthquakes/typhoons)."},
        "IS": {"level": "VERY SAFE", "description": "Extremely low crime rate. The primary risks are related to unpredictable weather and rugged natural terrain. Always check local weather alerts."},
        "CH": {"level": "VERY SAFE", "description": "Highly secure environment with excellent infrastructure and medical facilities. Standard situational awareness is sufficient."},
        "SG": {"level": "VERY SAFE", "description": "Strict enforcement of laws results in an exceptionally safe environment for travelers. Street crime is incredibly rare."},
        "NZ": {"level": "VERY SAFE", "description": "Safe destination with a stable political environment. Main risks are environmental; exercise caution during extreme adventure sports."},
        "FI": {"level": "VERY SAFE", "description": "Very low crime rates and high societal trust. Winters can be harsh, requiring proper preparation."},
        "DK": {"level": "VERY SAFE", "description": "A very safe destination. Petty crime like pickpocketing is the only minor concern in busy tourist areas."},
        "NO": {"level": "VERY SAFE", "description": "Excellent safety record. Exercise standard precautions and be prepared for extreme weather in northern regions."},
        "IE": {"level": "VERY SAFE", "description": "Generally very safe. Travelers should exercise normal precautions against petty theft in crowded areas of Dublin."},
        "AT": {"level": "VERY SAFE", "description": "High levels of safety and security. Occasional petty crime in major cities is the primary concern."},

        # --- MOSTLY SAFE ---
        "US": {"level": "MOSTLY SAFE", "description": "Generally safe for travel. Exercise increased caution due to varying levels of crime across different states and major urban centers."},
        "GB": {"level": "MOSTLY SAFE", "description": "Safe overall. Exercise standard precautions. Be vigilant against pickpocketing in tourist-heavy areas of London."},
        "FR": {"level": "MOSTLY SAFE", "description": "Mostly safe, but tourists are frequently targeted by pickpockets in Paris. Be aware of occasional large-scale demonstrations that can disrupt travel."},
        "DE": {"level": "MOSTLY SAFE", "description": "Generally safe. Exercise normal precautions. Be aware of petty crime at major transit hubs and during large festivals."},
        "IT": {"level": "MOSTLY SAFE", "description": "Mostly safe. Pickpocketing and bag snatching are common in major tourist cities (Rome, Florence, Milan)."},
        "ES": {"level": "MOSTLY SAFE", "description": "Generally safe, but street crime (pickpocketing, passport theft) is very common in tourist areas of Barcelona and Madrid."},
        "PT": {"level": "MOSTLY SAFE", "description": "Safe destination. Standard precautions apply. Watch for pickpockets on public transport in Lisbon and Porto."},
        "AU": {"level": "MOSTLY SAFE", "description": "Very safe regarding crime, but travelers must exercise high caution regarding harsh environmental conditions, wildlife, and ocean safety."},
        "CA": {"level": "MOSTLY SAFE", "description": "Safe travel destination. Standard precautions apply. Weather conditions in winter can present severe hazards."},
        "NL": {"level": "MOSTLY SAFE", "description": "Generally safe. Bicycle theft and minor pickpocketing are the most common issues in Amsterdam."},

        # --- LESS SAFE ---
        "MX": {"level": "LESS SAFE", "description": "Exercise increased caution due to crime and kidnapping. Risk varies heavily by state; stick to well-known tourist corridors and avoid nighttime highway travel."},
        "BR": {"level": "LESS SAFE", "description": "High levels of violent and street crime, especially in major cities like Rio de Janeiro and São Paulo. Avoid favelas and remain highly vigilant."},
        "ZA": {"level": "LESS SAFE", "description": "Significant risk of violent crime. Avoid walking at night, do not display valuables, and use trusted transportation services."},
        "CO": {"level": "LESS SAFE", "description": "Exercise increased caution due to crime, terrorism, and kidnapping. Avoid specific rural areas and remain vigilant in major cities."},
        "PE": {"level": "LESS SAFE", "description": "Increased risk of crime, including armed robbery, and occasional civil unrest. Use registered taxis and avoid traveling alone at night."},
        "EG": {"level": "LESS SAFE", "description": "Exercise increased caution due to terrorism. Stick to major tourist areas and follow guidance from local security authorities."},
        "PH": {"level": "LESS SAFE", "description": "Exercise increased caution due to crime, terrorism, and civil unrest. Specific southern regions carry extreme risk; major tourist islands are generally safer but require vigilance."},
        "TR": {"level": "LESS SAFE", "description": "Exercise increased caution due to terrorism and arbitrary detentions. Avoid areas near the Syrian border."},
        "TH": {"level": "LESS SAFE", "description": "Exercise increased caution due to political instability and occasional violence. Be extremely wary of traffic accidents and common tourist scams."},
        "IN": {"level": "LESS SAFE", "description": "Exercise increased caution due to crime and terrorism. Women should exercise heightened vigilance due to specific safety concerns. Traffic conditions are hazardous."}
    }

    # Fetch the assessment or return the default fallback
    if code in advisories:
        result = advisories[code]
        result["country_code"] = code
        result = json.dumps(result)
    else:
        result = json.dumps({
            "country_code": code,
            "level": "No Information Available",
            "description": "Please advise the user to check their local government travel website."
        })
        
    print("\n" + "="*50)
    print(f"🛠️ TOOL CALL FINSHED: Tool Response - {result}")    
    print("="*50 + "\n", flush=True)
    
    return result