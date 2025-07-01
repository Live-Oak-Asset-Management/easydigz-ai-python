from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import os
import json
import re
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langfuse import get_client, observe
import logging

# Initialize Langfuse
langfuse = get_client()
prompt_obj = langfuse.get_prompt("real_estate_content_generation", label="production")
prompt_template = prompt_obj.prompt  # or .content, depending on SDK version

app = FastAPI()

class QuestionSection(BaseModel):
    section: str
    questions: list[list[str]]  # List of [question, answer] pairs

class ContentRequest(BaseModel):
    agent_answers: list[QuestionSection]

# Prompt template (reuse your enhanced prompt)

# Initialize LangChain's OpenAI wrapper
llm = ChatOpenAI(
    openai_api_key="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",
    model="gpt-3.5-turbo",
    temperature=0.7,
    max_tokens=1500
)

@observe(name="build_prompt")
def build_prompt(agent_answers):
    """Build the complete prompt from agent answers"""
    prompt = prompt_template
    for section in agent_answers:
        prompt += f"\n## {section.section}\n"
        for q, a in section.questions:
            prompt += f"- {q}\n{a}\n"
    
    return prompt

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
    
    return cleaned_text

@observe
@app.post("/generate-content")
def generate_content(request: ContentRequest):
    """Generate real estate content using LLM"""
    with langfuse.start_as_current_span(
        name="llm_generation",
        input={"request": request.dict()},
        metadata={"model": "gpt-3.5-turbo"}
    ) as span:
        # Build the prompt
        prompt = build_prompt(request.agent_answers)
        
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)