from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import openai
import os
import json
import re
import csv
import langfuse
import logging
import pandas as pd
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langfuse import get_client, observe, Langfuse


from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class QuestionAnswer(BaseModel):
    question: str
    answer: str

class Question(BaseModel):
    question: str
    answer: str
    
class QuestionSection(BaseModel):
    section: str
    questions: list[QuestionAnswer]

class ContentRequest(BaseModel):
    agent_answers: list[QuestionSection]

class Section(BaseModel):
    section: str
    questions: List[Question]

class EmailGenerator(BaseModel):
    agent_answers: List[Section]


# === Load DataFrame ===
import json

JSON_INPUT_PATH = r"data/easy_templates_csv_variables.json"
with open(JSON_INPUT_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)  # data is a list of dicts with 'stage' and 'content'

# Initialize LangChain's OpenAI wrapper
llm = ChatOpenAI(
    openai_api_key=os.getenv("OPENAI_API_KEY"),  # Use environment variable instead
    model="gpt-4o-mini",
    temperature=0.7,
    max_tokens=1500
)

@observe(name="build_agent_prompt")
def build_agent_prompt(agent_answers):
    """Build the complete prompt from agent answers"""
    prompt = prompt_template
    for section in agent_answers:
        prompt += f"\n## {section.section}\n"
        for qa in section.questions:
            prompt += f"- {qa.question}\n{qa.answer}\n"
    
    return prompt

def build_prompt(original_html, stage, agent_context=None):
    print(f"[build_prompt] Building prompt for stage: {stage}")
    print(f"[build_prompt] Original HTML length: {len(original_html)} characters")
    print(f"[build_prompt] Agent context provided: {agent_context is not None}")
    
    if agent_context is None:
        print("[build_prompt] WARNING: Using default agent context (fallback)")
        agent_context = YOUR_DEFAULT_AGENT_CONTEXT  # fallback

    try:
        # Fetch prompt template from Langfuse
        print("[build_prompt] Fetching prompt template from Langfuse")
        prompt_obj = langfuse_client.get_prompt("personalize_email_prompt", label="production")
        prompt_template = prompt_obj.prompt  # or .content, depending on SDK version
        print(f"[build_prompt] Successfully fetched prompt template, length: {len(prompt_template)}")

        # Render the prompt with variables
        print("[build_prompt] Rendering prompt with variables")
        rendered_prompt = prompt_template.format(
            original_html=original_html,
            stage=stage,
            agent_context=agent_context
        )
        print(f"[build_prompt] Successfully rendered prompt, final length: {len(rendered_prompt)}")
        return rendered_prompt
    except Exception as e:
        print(f"[build_prompt] ERROR building prompt for stage {stage}: {str(e)}")
        raise

# Initialize Langfuse
langfuse = get_client()
prompt_obj = langfuse.get_prompt("real_estate_content_generation", label="production")
prompt_template = prompt_obj.prompt  # or .content, depending on SDK version

langfuse_client = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

@observe(name="clean_json")
def clean_json(text):
    """Clean and format JSON response"""
    # Remove code fences
    if text.strip().startswith('```'):
        text = text.split('```')[1]
    # Remove any stray control characters (like \1)
    text = re.sub(r'\\[0-9]+,?', '', text)
    # Remove trailing commas before } or ]
    text = re.sub(r',([ \t\r\n]*[}\]])', r'\1', text)
    
    cleaned_text = text.strip()
    # Try to add a closing brace if missing
    if cleaned_text.count('{') > cleaned_text.count('}'):
        cleaned_text += '}'
    return cleaned_text

@observe
@app.post("/generate-content")
def generate_content(request: ContentRequest):
    """Generate real estate content using LLM"""
    with langfuse.start_as_current_span(
        name="llm_generation",
        input={"request": request.dict()},
        metadata={"model": "gpt-4o-mini"}
    ) as span:
        print("request.agent_answers-->",request.agent_answers)
        # Build the prompt
        prompt = build_agent_prompt(request.agent_answers)
        
        # Use LangChain to call the LLM
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content=prompt)
        ]
        
        response = llm(messages)
        content = response.content
        
        span.update(
            output={"raw_response": content[:500] + "..." if len(content) > 500 else content},
            metadata={"response_length": len(content)}
        )
        
        # Clean and parse JSON
        cleaned_content = clean_json(content)
        print("LLM Output:\n", cleaned_content)
        result = json.loads(cleaned_content)
        
        span.update(
            output={"parsed_successfully": True, "result_keys": list(result.keys())},
            metadata={"cleaned_content_length": len(cleaned_content)}
        )
        
        # Score the generation (optional - you can customize this)
        span.score(name="correctness", value=1.0, comment="Content generated successfully")
        
        section_scoring_functions = {
            "home_page": score_home_page,
            "three_steps_carousel": score_three_steps_carousel,
            "about_us_page": score_about_us_page,
            "contact_us_page": score_contact_us_page,
            "global_settings": score_global_settings,
            "call_to_action": score_call_to_action,
        }

        scores = {}
        for section, scoring_func in section_scoring_functions.items():
            if section in result:
                score, reason = scoring_func(llm, result[section])
                scores[section] = {"score": score, "reason": reason}
                span.score(name=section, value=score, comment=reason)
        
        langfuse.flush()
        
        return {
            "status": "ok",
            "result": "success",
            "data": result,
            "scores": scores
        }

@app.post("/generate-email")
async def post_agent_questionnaire(agent_questionnaire: EmailGenerator):
    print("[generate-email] Starting email generation process")
    print(f"[generate-email] Agent questionnaire sections count: {len(agent_questionnaire.agent_answers)}")
    
    custom_agent_context = agent_questionnaire.dict()
    personalized_emails = []

    print(f"[generate-email] Total email templates to process: {len(data)}")

    # Start a single Langfuse span for the batch (or do one per row if you prefer)
    span = langfuse_client.start_span(
        name="agent_questionnaire_batch",
        input={"questionnaire": custom_agent_context}
    )
    try:
        for idx, row in enumerate(data):
            sample_html = row['template']
            stage = row['stage']
            print(f"[generate-email] Processing template {idx + 1}/{len(data)} - Stage: {stage}")
            print(f"[generate-email] Template length: {len(sample_html)} characters")
            
            prompt = build_prompt(sample_html, stage, agent_context=custom_agent_context)
            print(f"[generate-email] Built prompt length: {len(prompt)} characters for stage: {stage}")
            
            try:
                print(f"[generate-email] Calling OpenAI API for stage: {stage}")
                client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                output = response.choices[0].message.content.strip()
                print(f"[generate-email] Successfully generated email for stage: {stage}, output length: {len(output)}")
                
                personalized_emails.append({
                    "row": idx,
                    "stage": stage,
                    "personalized_email": output
                })
            except Exception as e:
                print(f"[generate-email] ERROR generating email for stage {stage}: {str(e)}")
                personalized_emails.append({
                    "row": idx,
                    "stage": stage,
                    "error": str(e)
                })
        
        print(f"[generate-email] Completed processing all templates. Success count: {len([e for e in personalized_emails if 'error' not in e])}")
        print(f"[generate-email] Error count: {len([e for e in personalized_emails if 'error' in e])}")
        
        span.update(output=personalized_emails)
        return JSONResponse(content={"personalized_emails": personalized_emails})
    except Exception as e:
        print(f"[generate-email] FATAL ERROR in email generation: {str(e)}")
        span.update(output=str(e), level="ERROR")
        raise
    finally:
        span.end()
        print("[generate-email] Email generation process completed")

# === Call OpenAI ===
def personalize_content(html, stage):
    print(f"[personalize_content] Starting personalization for stage: {stage}")
    print(f"[personalize_content] Input HTML length: {len(html)} characters")
    
    prompt = build_prompt(html, stage)
    print(f"[personalize_content] Built prompt for personalization, length: {len(prompt)}")
    
    span = langfuse_client.start_span(name="personalize_email", input=prompt)
    try:
        print(f"[personalize_content] Calling OpenAI API for personalization - stage: {stage}")
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        output = response.choices[0].message.content.strip()
        print(f"[personalize_content] Successfully personalized content for stage {stage}, output length: {len(output)}")
        
        span.update(output=output)
        return output
    except Exception as e:
        print(f"[personalize_content] ERROR personalizing content for stage {stage}: {str(e)}")
        span.update(output=str(e), level="ERROR")
        print(f"⚠️ LLM Error: {e}")
        return html  # fallback to original
    finally:
        span.end()

# === Apply Personalization ===
def personalize_row(row):
    try:
        original_html = row.get('template', '')
        stage = row.get('Stage')  # Default to 'Unknown' if not present
        if not isinstance(original_html, str) or not original_html.strip():
            raise ValueError("Empty template")
        personalized_html = personalize_content(original_html, stage)
        return personalized_html
    except Exception as e:
        print(f"skipped row: {e}")
        return row['template']  # fallback to original content
    
def score_home_page(llm, content):
    return score_section_with_llm(llm, "home_page", content)

def score_three_steps_carousel(llm, content):
    return score_section_with_llm(llm, "three_steps_carousel", content)

def score_about_us_page(llm, content):
    return score_section_with_llm(llm, "about_us_page", content)

def score_contact_us_page(llm, content):
    return score_section_with_llm(llm, "contact_us_page", content)

def score_global_settings(llm, content):
    return score_section_with_llm(llm, "global_settings", content)

def score_call_to_action(llm, content):
    return score_section_with_llm(llm, "call_to_action", content)

def score_section_with_llm(llm, section_name, section_content):
    eval_prompt = f"""Evaluate the following section for quality, completeness, and clarity. Give a score from 0.0 to 1.0 and a short reason.

Section ("{section_name}"):
{json.dumps(section_content, indent=2)}

Respond in this JSON format:
{{"score": float, "reason": string}}"""
    eval_result = llm([HumanMessage(content=eval_prompt)])
    try:
        parsed = json.loads(eval_result.content.strip())
        return parsed.get("score", 1.0), parsed.get("reason", "No reason provided")
    except Exception as e:
        return 1.0, f"Failed to parse reason: {str(e)}"

class EzSearchRequest(BaseModel):
    query: str

@app.post("/ezSearch")
async def ez_search(request: EzSearchRequest):
    try:
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        property_search_tool = {
            "type": "function",
            "function": {
                "name": "property_search",
                "description": "Search for properties based on various filters",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "The address for the property search e.g. 1404 Willow Street, NC"
                        },
                        "filters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "minBeds": {"type": "integer", "description": "Minimum number of bedrooms "},
                                "maxBeds": {"type": "integer", "description": "Maximum number of bedrooms"},
                                "minBaths": {"type": "integer", "description": "Minimum number of bathrooms"},
                                "maxBaths": {"type": "integer", "description": "Maximum number of bathrooms"},
                                "minPrice": {"type": "integer", "description": "Minimum price"},
                                "maxPrice": {"type": "integer", "description": "Maximum price"},
                                "minSqft": {"type": "integer", "description": "Minimum square footage"},
                                "maxSqft": {"type": "integer", "description": "Maximum square footage"},
                                "propertySubType": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "Single Family Residence",
                                            "Apartment",
                                            "Cabin",
                                            "Condominium",
                                            "Duplex",
                                            "Farm",
                                            "Manufactured On Land",
                                            "Quadruplex",
                                            "Ranch",
                                            "Townhouse",
                                            "Triplex"
                                        ]
                                    },
                                    "description": "Property subtype e.g. Single family home, Quadruplex"
                                },
                                "poolFeatures": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "Above Ground Pool",
                                            "Hot Tub",
                                            "In Ground Pool",
                                            "Swimming Pool Com/Fee",
                                            "Swim Pool/Priv",
                                            "Swim Pool/Priv. Com",
                                            "Heated Pool",
                                            "Salt Water Pool",
                                            "Indoor Pool"
                                        ]
                                    },
                                    "description": "Types of pools available in the listing i.e Hot Tub. Please note 'priv' means private and 'com' means community"
                                },
                                "parkingFeatures": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "Carport",
                                            "Attached",
                                            "Driveway",
                                            "Garage",
                                            "Garage Faces Front",
                                            "Assigned Spaces",
                                            "Attached",
                                            "Covered Parking",
                                            "Circular Drive",
                                            "Driveway",
                                            "Detached",
                                            "Parking Lot",
                                            "Street Parking",
                                            "No Parking"
                                        ]
                                    },
                                    "description": "Parking features e.g. Driveway"
                                },
                                "interiorFeatures": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "10Ft+ Ceiling",
                                            "2nd Kitchen",
                                            "9 Ft Ceiling",
                                            "Apt/Suite",
                                            "Automation",
                                            "Bookshelves",
                                            "Butler’s Pantry",
                                            "Cable TV Available",
                                            "Cathedral Ceiling",
                                            "Ceiling Fan",
                                            "Central Vac Finished",
                                            "Central Vac Prewired",
                                            "Coffered Ceiling",
                                            "Distributed Audio",
                                            "DSL Available",
                                            "Garage Shop",
                                            "Granite Counter Tops",
                                            "Heated Floors",
                                            "Intercom Finished",
                                            "Intercom Prewired",
                                            "Lighting Control",
                                            "Interior Needs Repair",
                                            "Paneling",
                                            "Pantry",
                                            "Plaster Wall",
                                            "Quartz Counter Tops",
                                            "Radon Mitigation Instld",
                                            "Radon Mitigation Ready",
                                            "Second Laundry",
                                            "Security System Finished",
                                            "Security System Prewired",
                                            "Skylight(s)",
                                            "Smoke Alarm",
                                            "Solid Surface Counter Top",
                                            "Tile Countertops",
                                            "Tray Ceiling",
                                            "Walk in Closet",
                                            "Wet Bar"
                                        ]
                                    },
                                    "description": "Features within the listing such as intercom and heated floors"
                                },
                                "accessibilityFeatures": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "36 in + Doorways",
                                            "48 in + Doorways",
                                            "Accessible Doors",
                                            "Aging in Place",
                                            "Barrier Free",
                                            "Chair Lift",
                                            "Elevator",
                                            "Universal Access",
                                            "Accessible Kitchen",
                                            "Level Flooring",
                                            "Levered Door",
                                            "Main Floor Laundry",
                                            "Near Public Transit",
                                            "Roll Up Counters",
                                            "Roll Windows",
                                            "Serviced By Bus Line",
                                            "Sliding/RotKitCab",
                                            "Wheelchair Entry",
                                            "Wheelchair Full Bath",
                                            "Wheelchair Half Bath",
                                            "Wheelchair Ramp"
                                        ],
                                        "description": "Accessibility features such as the ability ot have a wheelchair ramp or roll up counters"
                                    }
                                },
                                "waterfrontFeatures": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "Bay/Harbor",
                                            "Beach Sandy",
                                            "Beach Rocky",
                                            "Beach Grassy",
                                            "Boat House",
                                            "Boat Slip",
                                            "Buoy Installed",
                                            "Buoy Permit Available",
                                            "Buoy Permit Obtained",
                                            "Dock Community",
                                            "Dock Floating",
                                            "Dock Multi – Slip",
                                            "Dock Permit Available",
                                            "Dock Permit Obtained",
                                            "Dock Private Installed",
                                            "Dock Shared",
                                            "Dock Single Slip",
                                            "No Motor watercraft",
                                            "On Cove",
                                            "Pier",
                                            "Public Boat Ramp < 1 mile",
                                            "Publ. Boat Ramp 2-3 miles",
                                            "Swimming not permitted",
                                            "Water Front",
                                            "Water View"
                                        ],
                                        "description": "Waterfront charateristics of the listing"
                                    }
                                },
                                "waterSewer": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "City Sewer",
                                            "City Water",
                                            "Community Sewer",
                                            "Community Water",
                                            "County Sewer",
                                            "County Water",
                                            "Public",
                                            "Sand Filter",
                                            "Septic Tank",
                                            "Well",
                                            "No Water/Sewer"
                                        ],
                                        "description": "Water and sewer features of the listing"
                                    }
                                },
                                "minLotSize": {"type": "integer", "description": "Minimum lot size, always return the value in acers, i.e 0.1"},
                                "maxLotSize": {"type": "integer", "description": "Maximum lot size, always return value in acers, i.e 0.1"},
                                "minGarageSpaces": {"type": "integer", "description": "Minimum number of garage spaces"},
                                "maxGarageSpaces": {"type": "integer", "description": "Maximum number of garage spaces"},
                                "features": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of desired features e.g. backyard"
                                }
                            },
                            "required": [
                                "minBeds",
                                "maxBeds",
                                "minBaths",
                                "maxBaths",
                                "minPrice",
                                "maxPrice",
                                "minSqft",
                                "maxSqft",
                                "propertySubType",
                                "poolFeatures",
                                "parkingFeatures",
                                "interiorFeatures",
                                "accessibilityFeatures",
                                "waterfrontFeatures",
                                "waterSewer",
                                "minLotSize",
                                "maxLotSize",
                                "minGarageSpaces",
                                "maxGarageSpaces",
                                "features"
                            ]
                        }
                    },
                    "required": ["address", "filters"]
                },
                "strict": True
            }
        }

        system_prompt = (
            "You convert natural-language house search requests into a strict JSON matching the property_search function schema. "
            "Rules: "
            "1) Always return ONLY the function arguments JSON, valid per the schema. "
            "2) Do NOT fabricate values. Infer only from the user's input or use safe defaults described below. "
            "3) Address handling: If the user provides a location (address, city, neighborhood, ZIP, state), set address to that string. "
            "If NO location is given, set address to an empty string (\"\"). Never invent or use example addresses. "
            "4) When the user specifies exact counts (e.g., \"6 bedroom\"), set minBeds and maxBeds to that same value. Likewise for bathrooms and garage spaces. "
            "5) **STRICTLY:** Do not use any default values. unless the user explicitly asks for it."
            "6) Map style/type words to the closest propertySubType enum. Examples: single family -> Single Family Residence; ranch -> Ranch; condo -> Condominium; townhouse -> Townhouse; apartment -> Apartment; duplex -> Duplex; triplex -> Triplex; quadruplex -> Quadruplex; cabin -> Cabin; farm -> Farm; manufactured -> Manufactured On Land. "
            "7) Pools: if user asks for a pool, choose an appropriate poolFeatures value (e.g., \"In Ground Pool\" if unspecified). If no pool mentioned, return an empty array. "
            "8) Parking/garage: map \"parking\" or \"garage\" counts to minGarageSpaces/maxGarageSpaces. For parking features like driveway/garage/carport, add to parkingFeatures if explicitly mentioned. Otherwise leave empty. "
            "9) Interior/accessibility/waterfront/waterSewer/features: include only if clearly requested; otherwise return empty arrays. "
            "10) Never add fields outside the schema; adhere to enums exactly. "
            "13) DO not use any default values. unless the user explicitly asks for it."
            "12) Always return a valid JSON which is part of the property_search function added as OPEN API specification. "
            "13)Stick always to the response from property_search function only!"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.query}
            ],
            tools=[property_search_tool],
            tool_choice={"type": "function", "function": {"name": "property_search"}},
            temperature=0
        )

        choice = response.choices[0]
        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            # Fallback: try to parse raw content as JSON
            raw = choice.message.content or "{}"
            try:
                parsed = json.loads(clean_json(raw))
            except Exception:
                raise HTTPException(status_code=422, detail="Model did not return a tool call or valid JSON")
            return JSONResponse(content=parsed)

        # Extract the first tool call arguments
        args_text = tool_calls[0].function.arguments or "{}"
        parsed_args = json.loads(clean_json(args_text))
        return JSONResponse(content=parsed_args)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class FilterSearchRequest(BaseModel):
    query: str

@app.post("/filterSearch")
async def filter_search_endpoint(request: FilterSearchRequest):
    try:
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        filter_search_tool = {
            "type": "function",
            "function": {
                "name": "filter_search",
                "description": "Perform a filter-based search for properties or items using defined criteria",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fieldName": {
                            "type": "string",
                            "description": "The field to apply the filter on. Must be one of the valid field names.",
                            "enum": [
                                "AboveGradeFinishedArea",
                                "GarageSpaces",
                                "LotSizeAcres",
                                "BedsTotal",
                                "PublicRemarks",
                                "PostalCode",
                                "UnparsedAddress",
                                "BathroomsTotalDecimal",
                                "HighSchool",
                                "MiddleOrJuniorSchool",
                                "ElementarySchool",
                                "HorseAmenities.Other",
                                "WaterfrontFeatures.Creek",
                                "WaterfrontFeatures.Stream",
                                "WaterfrontFeatures.Lake",
                                "WaterfrontFeatures.River Front",
                                "WaterfrontFeatures.Beach Access",
                                "WaterfrontFeatures.Canal Front",
                                "WaterfrontFeatures.Ocean Front",
                                "ArchitecturalStyle.Bungalow",
                                "ArchitecturalStyle.A-Frame",
                                "ArchitecturalStyle.Contemporary",
                                "ArchitecturalStyle.Williamsburg",
                                "ArchitecturalStyle.Cape Cod",
                                "ArchitecturalStyle.Farm House",
                                "ArchitecturalStyle.Colonial",
                                "ArchitecturalStyle.Warehouse",
                                "ArchitecturalStyle.Georgian",
                                "ArchitecturalStyle.Tudor",
                                "ArchitecturalStyle.Spanish",
                                "ArchitecturalStyle.Victorian",
                                "ArchitecturalStyle.Rustic",
                                "ArchitecturalStyle.Craftsman",
                                "ArchitecturalStyle.Deck House",
                                "ArchitecturalStyle.Log Home",
                                "ArchitecturalStyle.French Province",
                                "ArchitecturalStyle.Charleston",
                                "ArchitecturalStyle.Modernist",
                                "ArchitecturalStyle.Cottage",
                                "ArchitecturalStyle.Geodesic",
                                "ArchitecturalStyle.National Historic Designation",
                                "ArchitecturalStyle.Local Historic Designation",
                                "ArchitecturalStyle.State Historic Designation",
                                "ArchitecturalStyle.Log",
                                "PoolFeatures.Private",
                                "PoolFeatures.Swimming Pool Com/Fee",
                                "PoolFeatures.None",
                                "PoolFeatures.Association",
                                "PoolFeatures.Fenced",
                                "PoolFeatures.Above Ground",
                                "PoolFeatures.Tile",
                                "PoolFeatures.Outdoor Pool",
                                "PoolFeatures.Pool/Spa Combo",
                                "PoolFeatures.Gunite",
                                "PoolFeatures.Filtered",
                                "PoolFeatures.Gas Heat",
                                "PoolFeatures.Indoor",
                                "PoolFeatures.Waterfall",
                                "ParkingFeatures.Garage",
                                "ParkingFeatures.Covered",
                                "ParkingFeatures.Concrete",
                                "ParkingFeatures.Driveway",
                                "ParkingFeatures.Attached",
                                "ParkingFeatures.Off Street",
                                "ParkingFeatures.Circular Driveway",
                                "ParkingFeatures.Assigned",
                                "ParkingFeatures.Parking Lot",
                                "ParkingFeatures.On Street",
                                "ParkingFeatures.Basement",
                                "ParkingFeatures.None",
                                "ParkingFeatures.Garage Door Opener",
                                "ParkingFeatures.Garage Faces Side",
                                "ParkingFeatures.Garage Faces Front",
                                "ParkingFeatures.Garage Faces Rear",
                                "ParkingFeatures.Electric Vehicle Charging Station(s)",
                                "ParkingFeatures.Carport",
                                "ParkingFeatures.Parking Pad",
                                "ParkingFeatures.Gravel",
                                "ParkingFeatures.Asphalt",
                                "ParkingFeatures.Workshop in Garage",
                                "ParkingFeatures.Inside Entrance",
                                "ParkingFeatures.Detached",
                                "ParkingFeatures.Unpaved",
                                "ParkingFeatures.Paved",
                                "ParkingFeatures.Shared Driveway",
                                "ParkingFeatures.Additional Parking",
                                "ParkingFeatures.Other",
                                "ParkingFeatures.Lighted",
                                "ParkingFeatures.Kitchen Level",
                                "ParkingFeatures.Oversized",
                                "ParkingFeatures.Private",
                                "ParkingFeatures.Common",
                                "ParkingFeatures.Guest",
                                "ParkingFeatures.Secured",
                                "ParkingFeatures.Deeded",
                                "ParkingFeatures.On Site",
                                "ParkingFeatures.Storage",
                                "ParkingFeatures.Attached Carport",
                                "ParkingFeatures.Alley Access",
                                "ParkingFeatures.No Garage",
                                "ParkingFeatures.Deck",
                                "ParkingFeatures.Drive Through",
                                "ParkingFeatures.Detached Carport",
                                "GarageSpaces",
                                "PropertyClass",
                                "PropertySubType",
                                "YearBuilt",
                                "MlsStatus",
                                "ListPrice"
                            ]
                        },
                        "operator": {
                            "type": "string",
                            "description": "The operator to use for filtering.",
                            "enum": [
                                ":=",
                                ":!=",
                                ":",
                                ":>",
                                ":<",
                                ":>=",
                                ":<=",
                                ":=true",
                                ":=false"
                            ]
                        },
                        "value": {
                            "type": "string",
                            "description": "The value to filter by. This must match the type of the field specified in 'fieldName'."
                        }
                    },
                    "additionalProperties": False,
                    "required": ["fieldName", "operator", "value"]
                },
                "strict": True
            }
        }

        system_prompt = (
            "You convert natural-language filter requests into a strict JSON matching the filter_search function schema. "
            "Output ONLY the function arguments JSON. Do not add extra keys. "
            "Field selection: Choose fieldName strictly from the enum; never invent fields. "
            "Numeric interpretation for fields [BedsTotal, BathroomsTotalDecimal, GarageSpaces, LotSizeAcres, AboveGradeFinishedArea, YearBuilt, ListPrice]: "
            "- 'at least N', 'N+', 'N or more' => operator :>= and value N. "
            "- 'more than N' => operator :> and value N. "
            "- 'at most N', 'up to N', 'N or less' => operator :<= and value N. "
            "- 'less than N' => operator :< and value N. "
            "- 'exactly N' or 'N <field>' with no qualifier => operator := and value N. "
            "Formatting: value must be a plain number string with no commas, units, or words. Use integers for integer fields; decimals only when appropriate (BathroomsTotalDecimal or lot size decimals). "
            "Strictness: Never loosen constraints. If the user asks for 4+ bedrooms, do not return any operator/value that could include 3. "
            "Examples: "
            "- 'at least 4 bedrooms' => {\"fieldName\":\"BedsTotal\",\"operator\":\":>=\",\"value\":\"4\"}. "
            "- '3 bathrooms' => {\"fieldName\":\"BathroomsTotalDecimal\",\"operator\":\":=\",\"value\":\"3\"}. "
            "- 'priced under 500000' => {\"fieldName\":\"ListPrice\",\"operator\":\":<\",\"value\":\"500000\"}. "
            "Adhere exactly to the filter_search schema and enums."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.query}
            ],
            tools=[filter_search_tool],
            tool_choice={"type": "function", "function": {"name": "filter_search"}},
            temperature=0
        )

        choice = response.choices[0]
        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            raw = choice.message.content or "{}"
            try:
                parsed = json.loads(clean_json(raw))
            except Exception:
                raise HTTPException(status_code=422, detail="Model did not return a tool call or valid JSON")
            return JSONResponse(content=parsed)

        args_text = tool_calls[0].function.arguments or "{}"
        parsed_args = json.loads(clean_json(args_text))
        return JSONResponse(content=parsed_args)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)