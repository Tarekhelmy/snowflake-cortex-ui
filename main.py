# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import snowflake.connector
import os
import uuid
from dotenv import load_dotenv
from datetime import datetime
import json

# Load environment variables
load_dotenv()

app = FastAPI(title="Snowflake Cortex Chat API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates for serving the HTML
templates = Jinja2Templates(directory="templates")

# Pydantic models
class Message(BaseModel):
    role: str
    content: str
    id: str
    timestamp: Optional[str] = None
    conversation_id: Optional[str] = None

class MessageRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class Conversation(BaseModel):
    id: str
    title: str
    messages: List[Message]
    created_at: str
    updated_at: str

# In-memory storage (replace with database in production)
conversations: Dict[str, Conversation] = {}

# Snowflake connection setup
def get_snowflake_connection():
    try:
        conn = snowflake.connector.connect(
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
            database=os.getenv("SNOWFLAKE_DATABASE"),
            schema=os.getenv("SNOWFLAKE_SCHEMA")
        )
        return conn
    except Exception as e:
        print(f"Error connecting to Snowflake: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Snowflake: {str(e)}")

# Query Snowflake Cortex
async def query_cortex(message: str) -> str:
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        
        # Escape single quotes in the message for SQL safety
        safe_message = message.replace("'", "''")
        
        # Example query using Snowflake Cortex
        # Adjust according to your specific Cortex setup
        query = f"""
        SELECT CORTEX_COMPLETION('{safe_message}', 
                                 system_prompt => 'You are a helpful assistant that analyzes data and provides insights',
                                 temperature => 0.7,
                                 max_tokens => 1000)
        """
        cursor.execute(query)
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result and result[0]:
            return result[0]
        else:
            return "Sorry, I couldn't process your request."
    except Exception as e:
        print(f"Error querying Snowflake Cortex: {e}")
        return f"I encountered an error when processing your request: {str(e)}"

# API Routes
@app.post("/api/messages", response_model=Message)
async def send_message(request: MessageRequest):
    user_message = request.message.strip()
    conversation_id = request.conversation_id
    timestamp = datetime.now().isoformat()
    
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Create a new conversation if needed
    if not conversation_id or conversation_id not in conversations:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=user_message[:30] + ("..." if len(user_message) > 30 else ""),
            messages=[],
            created_at=timestamp,
            updated_at=timestamp
        )
    
    # Add user message to conversation
    user_message_obj = Message(
        id=str(uuid.uuid4()),
        role="user",
        content=user_message,
        timestamp=timestamp,
        conversation_id=conversation_id
    )
    conversations[conversation_id].messages.append(user_message_obj)
    conversations[conversation_id].updated_at = timestamp
    
    # Get response from Snowflake Cortex
    response_content = await query_cortex(user_message)
    
    # Create assistant message
    assistant_message = Message(
        id=str(uuid.uuid4()),
        role="assistant",
        content=response_content,
        timestamp=datetime.now().isoformat(),
        conversation_id=conversation_id
    )
    
    # Add to conversation
    conversations[conversation_id].messages.append(assistant_message)
    
    return assistant_message

@app.get("/api/conversations", response_model=List[Conversation])
async def get_conversations():
    return list(conversations.values())

@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conversation_id]

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    del conversations[conversation_id]
    return {"success": True}

# Serve the HTML frontend
@app.get("/", response_class=HTMLResponse)
async def serve_html(request: Request):
    with open("templates/index.html", "r") as file:
        html_content = file.read()
    return HTMLResponse(content=html_content)

# Function to save conversations to a file (for persistence)
def save_conversations_to_file(filename="conversations.json"):
    with open(filename, "w") as f:
        # Convert the conversations dict to a serializable format
        serializable_convs = {}
        for conv_id, conv in conversations.items():
            serializable_convs[conv_id] = conv.dict()
        json.dump(serializable_convs, f, indent=2)

# Function to load conversations from a file (for persistence)
def load_conversations_from_file(filename="conversations.json"):
    try:
        with open(filename, "r") as f:
            loaded_convs = json.load(f)
            for conv_id, conv_data in loaded_convs.items():
                # Convert back to Conversation objects
                conversations[conv_id] = Conversation(**conv_data)
    except (FileNotFoundError, json.JSONDecodeError):
        # If file doesn't exist or is malformed, start with empty conversations
        pass

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    load_conversations_from_file()

@app.on_event("shutdown")
async def shutdown_event():
    save_conversations_to_file()

if __name__ == "__main__":
    import uvicorn
    
    # Create templates directory if it doesn't exist
    os.makedirs("templates", exist_ok=True)
    
    # Save the HTML file to the templates directory
    with open("templates/index.html", "w") as f:
        # You would need to provide your HTML content here
        # This is where you'd save the HTML from your frontend artifact
        pass
        
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)