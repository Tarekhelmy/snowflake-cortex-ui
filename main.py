# Copyright 2025 Snowflake Inc.
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple
import os
import uuid
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Snowflake imports
from snowflake.snowpark import Session
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.exceptions import SnowparkSQLException

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Snowflake Cortex Chat API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates for serving the HTML
templates = Jinja2Templates(directory="templates")

# Pydantic models
class Message(BaseModel):
    role: str
    content: str
    id: str
    timestamp: Optional[str] = None
    conversation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class MessageRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    semantic_model: Optional[str] = None

class Conversation(BaseModel):
    id: str
    title: str
    messages: List[Message]
    created_at: str
    updated_at: str

# In-memory storage (replace with database in production)
conversations: Dict[str, Conversation] = {}

# Define available semantic models
SEMANTIC_MODELS = [
    "FINANCIAL_METRICS.ANALYSTS.PERFORMANCE/financial_metrics.yaml",
    "SALES_DATA.ANALYTICS.DASHBOARD/sales_analytics.yaml"
]

def get_snowflake_session():
    """Create a Snowflake Snowpark session using environment variables"""
    try:
        # Connection parameters
        if os.path.isfile("/snowflake/session/token"):
            creds = {
                'host': os.getenv('SNOWFLAKE_HOST'),
                'port': os.getenv('SNOWFLAKE_PORT'),
                'protocol': "https",
                'account': os.getenv('SNOWFLAKE_ACCOUNT'),
                'authenticator': "oauth",
                'token': open('/snowflake/session/token', 'r').read(),
                'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
                'database': os.getenv('SNOWFLAKE_DATABASE'),
                'schema': os.getenv('SNOWFLAKE_SCHEMA'),
                'client_session_keep_alive': True
            }
        else:
            creds = {
                'account': os.getenv('SNOWFLAKE_ACCOUNT'),
                'user': os.getenv('SNOWFLAKE_USER'),
                'password': os.getenv('SNOWFLAKE_PASSWORD'),
                'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
                'database': os.getenv('SNOWFLAKE_DATABASE'),
                'schema': os.getenv('SNOWFLAKE_SCHEMA'),
                'client_session_keep_alive': True
            }
        
        # Filter out None values
        connection_parameters = {k: v for k, v in connection_parameters.items() if v is not None}
        
        # Create and return session
        session = Session.builder.configs(connection_parameters).create()
        logger.info("Successfully created Snowflake session")
        return session
    except Exception as e:
        logger.error(f"Error connecting to Snowflake: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Snowflake: {str(e)}")

def execute_snowflake_query(session, query: str) -> Tuple[Any, Optional[str]]:
    """Execute a query in Snowflake and return the results"""
    try:
        result = session.sql(query).collect()
        return result, None
    except SnowparkSQLException as e:
        error_msg = str(e)
        logger.error(f"Snowflake query error: {error_msg}")
        return None, error_msg

# Query Snowflake Cortex Analyst
async def query_cortex_analyst(message: str, semantic_model: Optional[str] = None) -> Dict[str, Any]:
    """
    Query Snowflake Cortex Analyst to analyze the user's question and generate a response
    """
    try:
        session = get_snowflake_session()
        
        # Escape single quotes in the message for SQL safety
        safe_message = message.replace("'", "''")
        
        # Use the provided semantic model or default to the first one in our list
        if not semantic_model:
            semantic_model = SEMANTIC_MODELS[0]
        
        # First, use Cortex Analyst to analyze the user's question
        analyst_query = f"""
        SELECT CORTEX_ANALYST(
            '{safe_message}',
            semantic_model_file => '@{semantic_model}',
            service_topic => 'financial data and business metrics',
            data_description => 'company financial metrics and performance data'
        )
        """
        
        logger.info(f"Executing Cortex Analyst query with semantic model: {semantic_model}")
        result, error = execute_snowflake_query(session, analyst_query)
        
        if error:
            logger.error(f"Cortex Analyst query error: {error}")
            return {
                "content": f"I encountered an error analyzing your question: {error}",
                "metadata": None
            }
            
        if not result or not result[0]:
            logger.warning("No result from Cortex Analyst")
            return {
                "content": "I'm having trouble analyzing your question. Could you please rephrase it?",
                "metadata": None
            }
        
        # Extract the analyst data and parse it
        analyst_data = result[0][0]
        logger.info(f"Analyst result received")
        
        # Check if analyst_data contains SQL
        analyst_json = json.loads(analyst_data) if isinstance(analyst_data, str) else analyst_data
        
        # If we have SQL in the result, execute it
        sql_statement = None
        sql_results = None
        
        if isinstance(analyst_json, dict) and 'generated_sql' in analyst_json:
            sql_statement = analyst_json['generated_sql']
            logger.info(f"Executing generated SQL: {sql_statement}")
            sql_results, sql_error = execute_snowflake_query(session, sql_statement)
            
            if sql_error:
                logger.error(f"SQL execution error: {sql_error}")
                sql_results = f"Error executing SQL: {sql_error}"
            else:
                # Convert SQL results to a more readable format
                sql_results = [dict(row) for row in sql_results] if sql_results else []
        
        # Next, use Cortex Completion to interpret the analyst results and generate a response
        completion_query = f"""
        SELECT CORTEX_COMPLETION(
            'You are a helpful financial data assistant that provides clear insights. 
             The user asked: "{safe_message}"
             Based on data analysis, here is the information: {json.dumps(analyst_json)}
             {f"SQL Query Results: {json.dumps(sql_results)}" if sql_results else ""}
             Provide a clear, helpful response that answers the user\'s question based on this data.',
            temperature => 0.3,
            max_tokens => 1000
        )
        """
        
        logger.info(f"Executing Cortex Completion query")
        completion_result, completion_error = execute_snowflake_query(session, completion_query)
        
        # Close the session
        session.close()
        
        if completion_error:
            logger.error(f"Completion query error: {completion_error}")
            return {
                "content": f"I processed your data but encountered an error generating a response: {completion_error}",
                "metadata": {"analyst_data": analyst_json}
            }
        
        if completion_result and completion_result[0]:
            # Prepare metadata with both analyst data and SQL results if available
            metadata = {
                "analyst_data": analyst_json,
                "sql_statement": sql_statement,
                "sql_results": sql_results
            }
            
            return {
                "content": completion_result[0][0],
                "metadata": metadata
            }
        else:
            return {
                "content": "I processed your question but couldn't generate a helpful response. Please try again with a more specific question.",
                "metadata": {"analyst_data": analyst_json}
            }
    except Exception as e:
        logger.error(f"Error in query_cortex_analyst: {e}", exc_info=True)
        return {
            "content": f"I encountered an error when processing your request: {str(e)}",
            "metadata": None
        }

# Fallback to standard Cortex completion if Analyst fails
async def query_cortex_completion(message: str) -> str:
    """Fallback to standard Cortex completion if Analyst fails"""
    try:
        session = get_snowflake_session()
        
        # Escape single quotes in the message for SQL safety
        safe_message = message.replace("'", "''")
        
        # Standard query using Snowflake Cortex
        query = f"""
        SELECT CORTEX_COMPLETION('{safe_message}', 
                               system_prompt => 'You are a helpful assistant that analyzes data and provides insights',
                               temperature => 0.7,
                               max_tokens => 1000)
        """
        
        result, error = execute_snowflake_query(session, query)
        session.close()
        
        if error:
            return f"I encountered an error processing your request: {error}"
            
        if result and result[0]:
            return result[0][0]
        else:
            return "Sorry, I couldn't process your request."
    except Exception as e:
        logger.error(f"Error with fallback Cortex completion: {e}")
        return f"I encountered an error when processing your request: {str(e)}"

# API Routes
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

@app.get("/api/semantic-models")
async def get_semantic_models():
    """Return the list of available semantic models"""
    return {"models": SEMANTIC_MODELS}

@app.post("/api/messages", response_model=Message)
async def send_message(request: MessageRequest):
    user_message = request.message.strip()
    conversation_id = request.conversation_id
    semantic_model = request.semantic_model
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
    
    # First try with Cortex Analyst
    try:
        logger.info(f"Processing message with Cortex Analyst: {user_message}")
        analyst_response = await query_cortex_analyst(user_message, semantic_model)
        response_content = analyst_response["content"]
        metadata = analyst_response["metadata"]
        
        # Create assistant message
        assistant_message = Message(
            id=str(uuid.uuid4()),
            role="assistant",
            content=response_content,
            timestamp=datetime.now().isoformat(),
            conversation_id=conversation_id,
            metadata=metadata
        )
    except Exception as e:
        # Fallback to standard completion
        logger.warning(f"Analyst failed, falling back to standard completion: {e}")
        response_content = await query_cortex_completion(user_message)
        
        # Create assistant message with the fallback response
        assistant_message = Message(
            id=str(uuid.uuid4()),
            role="assistant",
            content=response_content,
            timestamp=datetime.now().isoformat(),
            conversation_id=conversation_id,
            metadata=None
        )
    
    # Add to conversation
    conversations[conversation_id].messages.append(assistant_message)
    
    return assistant_message

# Serve the HTML frontend
@app.get("/", response_class=HTMLResponse)
async def serve_html(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Function to save conversations to a file (for persistence)
def save_conversations_to_file(filename="conversations.json"):
    try:
        with open(filename, "w") as f:
            # Convert the conversations dict to a serializable format
            serializable_convs = {}
            for conv_id, conv in conversations.items():
                serializable_convs[conv_id] = conv.dict()
            json.dump(serializable_convs, f, indent=2)
        logger.info(f"Conversations saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving conversations: {e}")

# Function to load conversations from a file (for persistence)
def load_conversations_from_file(filename="conversations.json"):
    try:
        if not os.path.exists(filename):
            logger.info(f"Conversations file {filename} not found, starting with empty conversations")
            return
            
        with open(filename, "r") as f:
            loaded_convs = json.load(f)
            for conv_id, conv_data in loaded_convs.items():
                # Convert back to Conversation objects
                conversations[conv_id] = Conversation(**conv_data)
        logger.info(f"Loaded {len(conversations)} conversations from {filename}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Error loading conversations: {e}")
        # If file doesn't exist or is malformed, start with empty conversations
        pass

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    # Create necessary directories
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    load_conversations_from_file()
    logger.info("Application started")

@app.on_event("shutdown")
async def shutdown_event():
    save_conversations_to_file()
    logger.info("Application shutting down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)