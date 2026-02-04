# Swarm Versonalities

Compare baseline (single LLM call) vs Swarm Versonalities workflow using the Groq API.

## Setup

```bash
pip install -r requirements.txt
export GROQ_API_KEY="your-groq-api-key"
streamlit run app.py
```

## Usage

Enter a task, click **Run Comparison** to see baseline vs swarm (Planner → Analyst → Builder → Critic → Builder → Editor) side by side.
