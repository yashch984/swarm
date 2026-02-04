import streamlit as st
import os
from groq import Groq

MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """You are part of a Swarm Versonalities v1 workflow. Follow these rules strictly:

1. Use exactly ONE versonality at a time
2. Do NOT skip roles in the sequence
3. Planner: Create a plan but do NOT solve the task
4. Analyst: Analyze requirements but do NOT draft output
5. Builder: Create the actual output
6. Critic: Review and provide feedback but do NOT rewrite
7. Editor: Produce the final clean artifact

Current role will be specified in each message."""

def call_api(messages):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )
    return response.choices[0].message.content

def run_baseline(task):
    messages = [{"role": "user", "content": task}]
    return call_api(messages)

def run_swarm(task):
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Planner
    conversation.append({"role": "user", "content": f"Role: PLANNER\n\nTask: {task}\n\nCreate a plan for completing this task. Do NOT solve it."})
    planner_response = call_api(conversation)
    conversation.append({"role": "assistant", "content": planner_response})
    
    # Analyst
    conversation.append({"role": "user", "content": "Role: ANALYST\n\nAnalyze the requirements and plan. Do NOT draft any output."})
    analyst_response = call_api(conversation)
    conversation.append({"role": "assistant", "content": analyst_response})
    
    # Builder (first pass)
    conversation.append({"role": "user", "content": "Role: BUILDER\n\nCreate the actual output based on the plan and analysis."})
    builder1_response = call_api(conversation)
    conversation.append({"role": "assistant", "content": builder1_response})
    
    # Critic
    conversation.append({"role": "user", "content": "Role: CRITIC\n\nReview the output and provide feedback. Do NOT rewrite it."})
    critic_response = call_api(conversation)
    conversation.append({"role": "assistant", "content": critic_response})
    
    # Builder (second pass)
    conversation.append({"role": "user", "content": "Role: BUILDER\n\nRevise the output based on the critic's feedback."})
    builder2_response = call_api(conversation)
    conversation.append({"role": "assistant", "content": builder2_response})
    
    # Editor
    conversation.append({"role": "user", "content": "Role: EDITOR\n\nProduce the final clean artifact. Output ONLY the final result, no meta-commentary."})
    editor_response = call_api(conversation)
    
    return editor_response

st.set_page_config(page_title="Swarm Versonalities — Baseline vs Swarm", layout="wide")

st.title("Swarm Versonalities — Baseline vs Swarm")

task = st.text_area("Task", height=150, placeholder="Enter your task here...")

if st.button("Run Comparison"):
    if not task.strip():
        st.error("Please enter a task")
    elif not os.environ.get("GROQ_API_KEY"):
        st.error("GROQ_API_KEY environment variable not set")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Baseline")
            with st.spinner("Running baseline..."):
                baseline_result = run_baseline(task)
            st.markdown(baseline_result)
        
        with col2:
            st.subheader("Swarm Versonalities")
            with st.spinner("Running swarm..."):
                swarm_result = run_swarm(task)
            st.markdown(swarm_result)
