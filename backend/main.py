"""
Cortex Analyst API
====================
This API allows users to interact with their data using natural language.
"""
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Union

import _snowflake  # For interacting with Snowflake-specific APIs
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from snowflake.snowpark.context import get_active_session  # To interact with Snowflake sessions
from snowflake.snowpark.exceptions import SnowparkSQLException
import os

# List of available semantic model paths in the format: <DATABASE>.<SCHEMA>.<STAGE>/<FILE-NAME>
# Each path points to a YAML file defining a semantic model
AVAILABLE_SEMANTIC_MODELS_PATHS = [
    "VAP_DEV_VAPNL_POC.ANALYSE_POC.INPUT_STAGE_CORTEX/PIANO_B2C.yaml"
]
API_ENDPOINT = "/api/v2/cortex/analyst/message"
FEEDBACK_API_ENDPOINT = "/api/v2/cortex/analyst/feedback"
API_TIMEOUT = 50000  # in milliseconds

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
        connection_parameters = creds
        connection_parameters = {k: v for k, v in connection_parameters.items() if v is not None}
        
        # Create and return session
        session = Session.builder.configs(connection_parameters).create()
        logger.info("Successfully created Snowflake session")
        return session
    except Exception as e:
        logger.error(f"Error connecting to Snowflake: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Snowflake: {str(e)}")

# Initialize a Snowpark session for executing queries
session = get_active_session()

# Initialize FastAPI app
app = FastAPI(
    title="Cortex Analyst API",
    description="API for interacting with data using natural language",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Define Pydantic models for request/response validation
class ContentItem(BaseModel):
    type: str
    text: Optional[str] = None
    suggestions: Optional[List[str]] = None
    statement: Optional[str] = None
    confidence: Optional[Dict] = None

class Message(BaseModel):
    role: str
    content: List[ContentItem]

class ConversationRequest(BaseModel):
    messages: List[Message]
    semantic_model_file: str

class FeedbackRequest(BaseModel):
    request_id: str
    positive: bool
    feedback_message: Optional[str] = None

# Global state to store conversations
conversations = {}

@app.get("/")
async def root():
    """Root endpoint returning API information"""
    return {
        "name": "Cortex Analyst API",
        "description": "API for interacting with data using natural language",
        "version": "1.0.0"
    }

@app.get("/semantic-models")
async def get_semantic_models():
    """Get available semantic models"""
    return {
        "models": [
            {"path": path, "name": path.split("/")[-1]} 
            for path in AVAILABLE_SEMANTIC_MODELS_PATHS
        ]
    }

@app.post("/analyst/message")
async def analyst_message(request: ConversationRequest):
    """Send a message to the Cortex Analyst"""
    try:
        # Convert Pydantic model to dict for the API request
        messages = [message.dict() for message in request.messages]
        
        # Prepare the request body
        request_body = {
            "messages": messages,
            "semantic_model_file": request.semantic_model_file,
        }

        # Send request to Cortex Analyst API
        response, error_msg = get_analyst_response(request_body)
        
        if error_msg:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        
        # Store conversation in memory (in a real app, use a database)
        conversation_id = response.get("request_id", "default")
        if conversation_id not in conversations:
            conversations[conversation_id] = []
        conversations[conversation_id].extend(messages)
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/analyst/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """Submit feedback for a query"""
    try:
        request_body = feedback.dict()
        
        resp = _snowflake.send_snow_api_request(
            "POST",  # method
            FEEDBACK_API_ENDPOINT,  # path
            {},  # headers
            {},  # params
            request_body,  # body
            None,  # request_guid
            API_TIMEOUT,  # timeout in milliseconds
        )
        
        if resp["status"] == 200:
            return {"message": "Feedback submitted successfully"}

        parsed_content = json.loads(resp["content"])
        raise HTTPException(
            status_code=resp["status"],
            detail={
                "request_id": parsed_content.get("request_id"),
                "error_code": parsed_content.get("error_code"),
                "message": parsed_content.get("message")
            }
        )
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a specific conversation by ID"""
    if conversation_id not in conversations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    return {"conversation_id": conversation_id, "messages": conversations[conversation_id]}

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a specific conversation by ID"""
    if conversation_id not in conversations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    del conversations[conversation_id]
    return {"message": "Conversation deleted successfully"}

@app.post("/execute-sql")
async def execute_sql(request: Dict):
    """Execute a SQL query and return the results"""
    query = request.get("query")
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query is required"
        )
    
    try:
        df, error = get_query_exec_result(query)
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error
            )
        
        # Convert DataFrame to dict for JSON response
        result = df.to_dict(orient="records")
        columns = list(df.columns)
        
        return {
            "success": True,
            "data": result,
            "columns": columns
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

def get_analyst_response(request_body: Dict) -> tuple[Dict, Optional[str]]:
    """
    Send request to the Cortex Analyst API and return the response.

    Args:
        request_body (Dict): The request body with messages and semantic model file.

    Returns:
        Tuple[Dict, Optional[str]]: The response from the API and any error message.
    """
    # Send a POST request to the Cortex Analyst API endpoint
    resp = _snowflake.send_snow_api_request(
        "POST",  # method
        API_ENDPOINT,  # path
        {},  # headers
        {},  # params
        request_body,  # body
        None,  # request_guid
        API_TIMEOUT,  # timeout in milliseconds
    )

    # Content is a string with serialized JSON object
    parsed_content = json.loads(resp["content"])

    # Check if the response is successful
    if resp["status"] < 400:
        # Return the content of the response as a JSON object
        return parsed_content, None
    else:
        # Craft readable error message
        error_msg = f"""
🚨 An Analyst API error has occurred 🚨

* response code: `{resp['status']}`
* request-id: `{parsed_content['request_id']}`
* error code: `{parsed_content['error_code']}`

Message:
```
{parsed_content['message']}
```
        """
        return parsed_content, error_msg

def get_query_exec_result(query: str) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Execute the SQL query and convert the results to a pandas DataFrame.

    Args:
        query (str): The SQL query.

    Returns:
        Tuple[Optional[pd.DataFrame], Optional[str]]: The query results and the error message.
    """
    try:
        df = session.sql(query).to_pandas()
        return df, None
    except SnowparkSQLException as e:
        return None, str(e)

# Error handling middleware
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for all unhandled exceptions"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)