import streamlit as st
import sys
import os
import re
import asyncio
import json
import base64

# Handle Google credentials for Render deployment
def setup_google_credentials():
    """Setup Google credentials from environment variables"""
    try:
        # Check if credentials are provided as base64 encoded JSON
        creds_base64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
        if creds_base64:
            # Decode and write to temporary file
            creds_json = base64.b64decode(creds_base64).decode('utf-8')
            creds_path = '/tmp/service-account.json'
            with open(creds_path, 'w') as f:
                f.write(creds_json)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
            return True
        
        # Check if credentials file path is provided
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if creds_path and os.path.exists(creds_path):
            return True
            
        return False
    except Exception as e:
        st.error(f"Error setting up Google credentials: {e}")
        return False

# Setup credentials
credentials_available = setup_google_credentials()

# Ensure parent directory is in sys.path for package imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import your agents (with error handling for deployment)
try:
    from agents.reddit_scout.agent import (
        search_coin_id,
        get_coin_details,
        get_crypto_community_insights,
        get_token_smart_money_flow,
        get_native_asset_smart_money_flow,
        get_crypto_rumors_and_news,
        root_agent,
    )
    AGENTS_AVAILABLE = True
except ImportError as e:
    st.error(f"Warning: Could not import agents. Running in demo mode. Error: {e}")
    AGENTS_AVAILABLE = False

st.set_page_config(page_title="Crypto Chatbot", page_icon="🪙", layout="centered")
st.title("🪙 Crypto Chatbot")

# Show deployment status
if not credentials_available:
    st.warning("⚠️ Google Cloud credentials not found. App running in limited mode.")
if not AGENTS_AVAILABLE:
    st.warning("⚠️ Agent modules not available. Some features may be limited.")

st.write("Ask me anything about crypto coins, sentiment, rumors, smart money flow, or just chat!")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Chat input
user_input = st.chat_input("Type your question about any coin or just say hi...")

def detect_intent_and_coin(message):
    message = message.lower()
    coin = None
    # Try to extract coin name/symbol after common phrases
    match = re.search(r"(?:price|sentiment|rumors?|news|smart money|about|for|of|on)\s+([a-zA-Z0-9\- ]+)", message)
    if match:
        coin = match.group(1).strip()
    else:
        # fallback: last word if it looks like a coin
        tokens = message.split()
        if tokens and tokens[-1].isalpha() and len(tokens[-1]) > 2:
            coin = tokens[-1]
    # Intent detection
    if "price" in message or "market cap" in message or "details" in message or "coingecko" in message:
        return "price", coin
    if "sentiment" in message or "community" in message or "twitter" in message or "feel" in message or "opinion" in message:
        return "sentiment", coin
    if "rumor" in message or "news" in message or "announcement" in message or "leak" in message or "speculation" in message:
        return "rumor", coin
    if "smart money" in message or "nansen" in message or "flow" in message or "inflow" in message or "outflow" in message:
        return "smart_money", coin
    if "tell me about" in message or "what's up with" in message or "whats up with" in message or "overview" in message or "summary" in message or "all info" in message or "everything" in message:
        return "full_report", coin
    # fallback: if just a coin name
    if coin:
        return "full_report", coin
    return "unknown", None

# Helper: Run root_agent for general conversation
async def run_root_agent(user_message):
    if not AGENTS_AVAILABLE or not credentials_available:
        return "Sorry, the full agent functionality is not available in this deployment. Please check the setup."
    
    try:
        # Minimal context for a single-turn conversation
        from google.adk.agents.invocation_context import InvocationContext
        from google.adk.sessions.session import Session
        from google.genai import types
        
        class DummySessionService:
            def get(self, *args, **kwargs):
                return Session(id="dummy", app_name="crypto_chatbot", user_id="user")
        
        session = Session(id="dummy", app_name="crypto_chatbot", user_id="user")
        ctx = InvocationContext(
            invocation_id="dummy-invocation",
            agent=root_agent,
            user_content=types.Content(role="user", parts=[types.Part.from_text(user_message)]),
            session=session,
            session_service=DummySessionService(),
        )
        
        response_text = None
        async for event in root_agent.run_async(ctx):
            if event.content and event.content.parts:
                # Only show the first final response
                if event.content.role == "model" and event.content.parts[0].text:
                    response_text = event.content.parts[0].text
                    break
        return response_text or "[No response from agent]"
    except Exception as e:
        return f"Error running agent: {str(e)}"

# Fallback responses for when agents aren't available
def get_fallback_response(intent, coin):
    if intent == "price":
        return f"📊 I'd normally fetch live price data for {coin.upper()}, but the full API functionality isn't available in this deployment. Please ensure Google ADK is properly configured."
    elif intent == "sentiment":
        return f"🎭 I'd analyze community sentiment for {coin.upper()}, but the sentiment analysis service isn't available in this deployment."
    elif intent == "rumor":
        return f"📰 I'd search for latest rumors and news about {coin.upper()}, but the news service isn't available in this deployment."
    elif intent == "smart_money":
        return f"💰 I'd analyze smart money flow for {coin.upper()}, but the blockchain analysis service isn't available in this deployment."
    elif intent == "full_report":
        return f"📋 I'd provide a complete report for {coin.upper()}, but the full service suite isn't available in this deployment."
    else:
        return "Hello! I'm a crypto chatbot. The full functionality requires proper Google ADK setup with credentials."

# Main chat logic
if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    intent, coin = detect_intent_and_coin(user_input)
    response = ""
    
    if not AGENTS_AVAILABLE or not credentials_available:
        if coin and intent != "unknown":
            response = get_fallback_response(intent, coin)
        else:
            response = "Hello! The full chatbot functionality requires Google ADK setup. Currently running in limited mode."
    elif not coin and intent != "unknown":
        response = "Sorry, I couldn't figure out which coin you're asking about. Please specify the coin name or symbol."
    elif intent == "unknown":
        # Use root_agent for general conversation
        with st.spinner("Thinking..."):
            response = asyncio.run(run_root_agent(user_input))
    else:
        try:
            coin_id = search_coin_id(coin)
            if not coin_id:
                response = f"Sorry, I couldn't find '{coin}' on CoinGecko. Please check the name or symbol."
            else:
                if intent == "price":
                    details = get_coin_details(coin_id)
                    response = details.get("result") if details.get("status") == "success" else details.get("result", "Error fetching price info.")
                elif intent == "sentiment":
                    sentiment = get_crypto_community_insights(coin)
                    response = sentiment.get("result") if sentiment.get("status") == "success" else sentiment.get("result", "Error fetching sentiment.")
                elif intent == "rumor":
                    rumor = get_crypto_rumors_and_news(coin)
                    response = rumor.get("result") if rumor.get("status") == "success" else rumor.get("result", "Error fetching rumors/news.")
                elif intent == "smart_money":
                    details = get_coin_details(coin_id)
                    if details.get("status") == "success":
                        if details.get("is_native_asset"):
                            flow = get_native_asset_smart_money_flow(details.get("chain"))
                        else:
                            flow = get_token_smart_money_flow(details.get("chain"), details.get("contract_address"))
                        response = flow.get("result") if flow.get("status") == "success" else flow.get("result", "Error fetching smart money flow.")
                    else:
                        response = details.get("result", "Error fetching coin details for smart money flow.")
                elif intent == "full_report":
                    details = get_coin_details(coin_id)
                    sentiment = get_crypto_community_insights(coin)
                    rumor = get_crypto_rumors_and_news(coin)
                    if details.get("status") == "success":
                        if details.get("is_native_asset"):
                            flow = get_native_asset_smart_money_flow(details.get("chain"))
                        else:
                            flow = get_token_smart_money_flow(details.get("chain"), details.get("contract_address"))
                    else:
                        flow = {"result": details.get("result", "Error fetching smart money flow.")}
                    response = f"**Market Data:**\n{details.get('result', '')}\n\n**Community Sentiment:**\n{sentiment.get('result', '')}\n\n**Rumors/News:**\n{rumor.get('result', '')}\n\n**Smart Money Flow:**\n{flow.get('result', '')}"
                else:
                    response = "Sorry, I didn't understand your question. Please ask about price, sentiment, rumors, smart money, or a general overview."
        except Exception as e:
            response = f"An error occurred: {str(e)}"
    
    st.session_state["messages"].append({"role": "assistant", "content": response})

# Display chat history
for msg in st.session_state["messages"]:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        st.chat_message("assistant").markdown(msg["content"])