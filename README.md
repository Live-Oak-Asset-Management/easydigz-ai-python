# Real Estate Content Generator

This project is a FastAPI-based backend for generating high-quality, SEO-optimized real estate website content using LLMs. It integrates with [Langfuse](https://langfuse.com/) for prompt management, tracing, and LLM-as-a-judge evaluation.

---

## Features
- Generate structured, SEO-friendly real estate content in JSON format
- Prompts are managed in the Langfuse dashboard (no hardcoded prompts)
- Section-by-section LLM-as-a-judge scoring and reasoning
- Full traceability and evaluation in the Langfuse dashboard

---

## Setup Instructions

### 1. Clone the Repository
```sh
git clone <your-repo-url>
cd real_estate
```

### 2. Create and Activate a Virtual Environment
```sh
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```sh
pip install -r requirements.txt
```

### 4. Set Environment Variables
Create a `.env` file or set these variables in your environment:
```
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com  # or your self-hosted URL
OPENAI_API_KEY=your_openai_api_key
```

---

## Running the App
```sh
uvicorn app:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

---

## Prompt Management with Langfuse

langfuse Credentials:-
ID- tarun.khurana@ideafoundation.co.in
Password- Tarun@1173

---

### Add or Update Prompts
1. Log in to your [Langfuse dashboard](https://cloud.langfuse.com/).
2. Go to the **Prompts** section under real_estate.
3. Click **Create Prompt** to add a new prompt, or select an existing one to edit.
4. Use a clear name (e.g., `real_estate_content_generation`) and label (e.g., `production`).
5. Paste your prompt template in the content field.
6. Save. Your app will now use the latest version of the prompt from Langfuse.

### Fetching Prompts in Code
The app fetches prompts dynamically from Langfuse using the SDK:
```python
prompt_obj = langfuse.get_prompt("real_estate_content_generation", label="production")
prompt_template = prompt_obj.prompt
```

---

## Tracing and LLM-as-a-Judge Evaluation with Langfuse

### How Tracing Works
- Every API call creates a trace in Langfuse.
- Each major step (prompt build, LLM call, JSON parse, etc.) is tracked as a span.
- Section scores (e.g., home page, about us, etc.) are logged with `span.score()`.

### Viewing Traces
1. Go to your [Langfuse dashboard](https://cloud.langfuse.com/).
2. Select your project and environment.
3. Open the **Traces** tab to see all recent traces.
4. Click a trace to view details, including input, output, spans, and scores.

### LLM-as-a-Judge Scores
- Each section (home page, carousel, about us, etc.) is evaluated by the LLM and scored.
- Scores and reasons are visible in the **Scores** or **Evaluations** panel of each trace.
- You can set up custom evaluators in Langfuse to automate and analyze these scores.

---

## Useful Links
- [Langfuse Documentation](https://langfuse.com/docs)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---
Input Example:

{
  "agent_answers": [
    {
      "section": "Location & Market Information",
      "questions": [
        {
          "question": "What geographic area(s) do you primarily serve?",
          "answer": "Durham, Raleigh, Chapel Hill, Cary, Morrisville, Hillsborough and the surrounding areas in NC; and Philadelphia, PA and the surrounding areas."
        },
        {
          "question": "Is there a specific neighborhood or area where you have particular expertise?",
          "answer": "Downtown Durham"
        },
        {
          "question": "What are 3-5 unique selling points about your local market that buyers/sellers should know?",
          "answer": "1) Now is a great time to purchase a home due to sellers getting nervous about the economy and the days on market average is getting longer. 2) If you're looking to sell your home, having an experienced Realtor like myself is very important, along with pricing your home very well to sell in this market and top notch marketing to get your home in front of potential buyers. 3) Purchasing your own home is the number 1 investment anyone can make in America, because you are locking in your mortgage payment versus paying rent which goes up every year, you are building up equity with your monthly mortgage payments while having the home value increase over time, and if you have to move you could rent out."
        },
        {
          "question": "What types of properties are most common in your area?",
          "answer": "Single-family homes, condos, luxury estates, etc."
        }
      ]
    },
    {
      "section": "Agent/Broker Specialization",
      "questions": [
        {
          "question": "What property types do you specialize in?",
          "answer": "Residential, commercial, luxury, investment, etc."
        },
        {
          "question": "Do you focus on a particular transaction type?",
          "answer": "First-time buyers, relocations, downsizing, etc."
        },
        {
          "question": "What special certifications or designations do you hold?",
          "answer": "NAR, ABR, CNE"
        },
        {
          "question": "How many years of experience do you have in real estate?",
          "answer": "22 years"
        }
      ]
    },
    {
      "section": "Unique Value Proposition",
      "questions": [
        {
          "question": "What makes your services different from other brokers in your area?",
          "answer": "Preventive defense strategies, personalized solutions, advanced technology, and selfless service."
        },
        {
          "question": "What specific problems do you solve for your clients?",
          "answer": "Anticipate and solve transaction challenges, provide expert guidance, and ensure smooth closings."
        },
        {
          "question": "What is your approach to client relationships?",
          "answer": "Building lasting relationships as a trusted advisor and friend."
        },
        {
          "question": "Do you have any specific systems or processes that benefit your clients?",
          "answer": "Proactive transaction management, advanced marketing, and technology-driven solutions."
        }
      ]
    },
    {
      "section": "Personal Brand Elements",
      "questions": [
        {
          "question": "How would you describe your personal brand in 3-5 adjectives?",
          "answer": "Experienced, dedicated, proactive, trustworthy, client-focused."
        },
        {
          "question": "What tone best represents your communication style?",
          "answer": "Professional, friendly, direct."
        },
        {
          "question": "Do you have any personal interests or community involvement that shapes your business?",
          "answer": "Community volunteer, local events supporter."
        },
        {
          "question": "What client testimonials best represent the value you provide?",
          "answer": "Charles made the process seamless and stress-free!"
        }
      ]
    },
    {
      "section": "Business Goals",
      "questions": [
        {
          "question": "What is your primary goal for your website?",
          "answer": "Lead generation, branding, information resource."
        },
        {
          "question": "What specific actions do you want visitors to take on your site?",
          "answer": "Contact me, sign up for property search, schedule a consultation."
        },
        {
          "question": "Which lead generation methods have worked best for you in the past?",
          "answer": "Referrals, online marketing, open houses."
        },
        {
          "question": "What types of clients are you most interested in attracting?",
          "answer": "Serious buyers and sellers in the Triangle and Philadelphia markets."
        }
      ]
    }
  ]
}