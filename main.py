"""
Cortex Analyst API
====================
This API allows users to interact with their data using natural language using Snowflake's Cortex service.
"""
import json
import time
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional, Union, Any
import logging
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from urllib.parse import urlunparse


from typing import TypedDict, Union

# Snowflake imports
from snowflake.snowpark import Session
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.exceptions import SnowparkSQLException
from snowflake.connector import SnowflakeConnection

import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of available semantic model paths
AVAILABLE_SEMANTIC_MODELS_PATHS = [
    "VAP_DEV_VAPNL_POC.ANALYSE_POC.INPUT_STAGE_CORTEX/PIANO_B2C.yaml"
]
API_ENDPOINT = "/api/v2/cortex/analyst/message"
FEEDBACK_API_ENDPOINT = "/api/v2/cortex/analyst/feedback"
API_TIMEOUT = 50000  # in milliseconds

class Headers(TypedDict):
    Accept: str
    Content_Type: str
    Authorization: str
# Helper classes for Cortex Analyst Tool
class SnowflakeError(Exception):
    """Exception raised for Snowflake errors."""
    def __init__(self, message="An error occurred with Snowflake"):
        self.message = message
        super().__init__(self.message)

class CortexEndpointBuilder:
    def __init__(self, connection: Union[Session, SnowflakeConnection]):
        self.connection = _get_connection(connection)
        self.BASE_URL = self._set_base_url()
        self.inside_snowflake = self._determine_runtime()
        self.BASE_HEADERS = self._set_base_headers()

    def _determine_runtime(self):
        try:
            from _stored_proc_restful import StoredProcRestful

            return True
        except ImportError:
            return False

    def _set_base_url(self):
        scheme = "https"
        con = self.connection
        if hasattr(con, "scheme"):
            scheme = con.scheme
        host = con.host
        host = host.replace("_", "-")
        host = host.lower()
        url = urlunparse((scheme, host, "", "", "", ""))
        return url

    def _set_base_headers(self):
        if self.inside_snowflake:
            token = None
        else:
            token = self.connection.rest.token
        return {
            "Content-Type": "application/json",
            "Authorization": f'Snowflake Token="{token}"',
        }

    def get_complete_endpoint(self):
        URL_SUFFIX = "/api/v2/cortex/inference:complete"
        if self.inside_snowflake:
            return URL_SUFFIX
        return f"{self.BASE_URL}{URL_SUFFIX}"

    def get_analyst_endpoint(self):
        URL_SUFFIX = "/api/v2/cortex/analyst/message"
        if self.inside_snowflake:
            return URL_SUFFIX
        return f"{self.BASE_URL}{URL_SUFFIX}"

    def get_search_endpoint(self, database, schema, service_name):
        URL_SUFFIX = f"/api/v2/databases/{database}/schemas/{schema}/cortex-search-services/{service_name}:query"
        URL_SUFFIX = URL_SUFFIX.lower()
        if self.inside_snowflake:
            return URL_SUFFIX
        return f"{self.BASE_URL}{URL_SUFFIX}"

    def get_complete_headers(self) -> Headers:
        return self.BASE_HEADERS | {"Accept": "application/json"}

    def get_analyst_headers(self) -> Headers:
        return self.BASE_HEADERS

    def get_search_headers(self) -> Headers:
        return self.BASE_HEADERS | {"Accept": "application/json"}

class CortexAnalystTool:
    """Cortex Analyst tool for interacting with Snowflake's Cortex service."""

    def __init__(
        self,
        semantic_model,
        stage,
        connection,
        service_topic="data",
        data_description="the source data"
    ):
        """Initialize the Cortex Analyst Tool.
        
        Parameters
        ----------
        semantic_model (str): yaml file name containing semantic model for Cortex Analyst
        stage (str): name of stage containing semantic model yaml.
        connection (object): snowpark connection object
        service_topic (str): topic of the data in the tables
        data_description (str): description of the source data
        """
        self.connection = CortexEndpointBuilder(connection).connection
        self.FILE = semantic_model
        self.STAGE = stage
        self.service_topic = service_topic
        self.data_description = data_description
        
        logger.info(f"Cortex Analyst Tool successfully initialized")

    async def ask(self, query):
        """Process a query using Cortex Analyst."""
        logger.debug(f"Cortex Analyst Prompt: {query}")

        url, headers, data = self._prepare_analyst_request(prompt=query)

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url=url, json=data) as response:
                response_text = await response.text()
                json_response = json.loads(response_text)

        # Return the raw response for further processing in the API
        return json_response

    def _prepare_analyst_request(self, prompt):
        """Prepare a request to the Cortex Analyst API."""
        data = {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
            "semantic_model_file": f"""@VAP_DEV_VAPNL_POC.ANALYSE_POC.INPUT_STAGE_CORTEX/{self.FILE}""",
        }

        eb = CortexEndpointBuilder(self.connection)
        headers = eb.get_analyst_headers()
        url = eb.get_analyst_endpoint()

        return url, headers, data

    def process_sql_response(self, response):
        """Process SQL query in the response and execute it."""
        if len(response) > 1 and "sql" in response[0]["type"] and "statement" in response[1]:
            sql_query = response[1]["statement"]
            logger.debug(f"Cortex Analyst SQL Query: {sql_query}")
            
            # Execute the query

            cursor = self.connection.cursor()
            cursor.execute(sql_query)
            result = cursor.fetch_pandas_all()
            
            return {
                "query": sql_query,
                "data": result.to_dict(orient="records"),
                "columns": list(result.columns)
            }
        
        return None

def _get_connection(snowflake_connection):
    """Helper to standardize connection handling."""
    if isinstance(snowflake_connection, Session):
        # If it's a Snowpark session, use the underlying connection
        return snowflake_connection._conn._conn
    elif isinstance(snowflake_connection, SnowflakeConnection):
        # If it's already a SnowflakeConnection, use it directly
        return snowflake_connection
    else:
        raise ValueError("Unsupported connection type")

# Setup Snowflake connection
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
                'authenticator': 'externalbrowser',
                'client_session_keep_alive': True
            }
        
        # Filter out None values
        connection_parameters = {k: v for k, v in creds.items() if v is not None}
        
        # Create and return session
        session = Session.builder.configs(connection_parameters).create()
        logger.info("Successfully created Snowflake session")
        if isinstance(session, Session):
            return getattr(session, "connection")
        return session
    except Exception as e:
        logger.error(f"Error connecting to Snowflake: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Snowflake: {str(e)}")

# Initialize FastAPI app
app = FastAPI(
    title="Cortex Analyst API",
    description="API for interacting with data using natural language via Snowflake Cortex",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="templates")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Try to initialize a Snowpark session for executing queries
try:
    session = get_snowflake_session()
    # Initialize the Cortex Analyst Tool
    cortex_tool = CortexAnalystTool(
        semantic_model=AVAILABLE_SEMANTIC_MODELS_PATHS[0].split('/')[-1],
        stage=AVAILABLE_SEMANTIC_MODELS_PATHS[0].split('/')[0].split('.')[-1],
        connection=session,
        service_topic="user data",
        data_description="analytics data"
    )
    logger.info("Successfully initialized Cortex Analyst Tool")
    USE_SNOWFLAKE = True
except Exception as e:
    logger.warning(f"Could not connect to Snowflake: {e}. Using mock implementations.")
    session = None
    cortex_tool = None
    USE_SNOWFLAKE = False

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

@app.get("/", response_class=HTMLResponse)
async def serve_html(request: Request):
    """Serve the HTML frontend"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/info")
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
async def analyst_message(request: Request):
    """Send a message to the Cortex Analyst"""
    try:
        # Get request body as JSON
        request_data = await request.json()
        
        # Extract messages and semantic model file
        messages = request_data.get("messages", [])
        semantic_model_file = request_data.get("semantic_model_file", "")
        
        # Get the user query (last message)
        user_query = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_content = message.get("content", [])
                for content in user_content:
                    if content.get("type") == "text":
                        user_query = content.get("text", "")
                        break
                if user_query:
                    break
        
        # Prepare the request body
        request_body = {
            "messages": messages,
            "semantic_model_file": semantic_model_file,
        }

        if USE_SNOWFLAKE and cortex_tool:
            # Call the actual Cortex Analyst API
            logger.info(f"Sending query to Cortex Analyst: {user_query}")
            response = await cortex_tool.ask(user_query)
            
            # Store conversation in memory
            conversation_id = response.get("request_id", "default")
            if conversation_id not in conversations:
                conversations[conversation_id] = []
            conversations[conversation_id].extend(messages)
            print(response)
            
            # Check if there's SQL to execute
            if "message" in response and "content" in response["message"]:
                content = response["message"]["content"]
                sql_result = cortex_tool.process_sql_response(content)
                
                if sql_result:
                    # Store SQL result for later use
                    if conversation_id not in conversations:
                        conversations[conversation_id] = []
                    conversations[conversation_id].append({
                        "sql_result": sql_result
                    })
            
            return response
        else:
            # Use mock implementation
            logger.info("Using mock Cortex Analyst implementation")
            response = mock_analyst_response(request_body)
            
            # Store conversation in memory
            conversation_id = response.get("request_id", "default")
            if conversation_id not in conversations:
                conversations[conversation_id] = []
            conversations[conversation_id].extend(messages)
            
            return response
        
    except Exception as e:
        logger.error(f"Error processing analyst message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/analyst/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """Submit feedback for a query"""
    try:
        # In a real implementation, this would call Cortex Analyst API
        # For now, we'll just return a success message
        return {"message": "Feedback submitted successfully"}
        
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
        if USE_SNOWFLAKE and session:
            # Execute the query using Snowflake
            logger.info(f"Executing SQL query: {query}")
            try:
                df = session.sql(query).to_pandas()
                return {
                    "success": True,
                    "data": df.to_dict(orient="records"),
                    "columns": list(df.columns)
                }
            except SnowparkSQLException as e:
                logger.error(f"SQL execution error: {str(e)}")
                return {
                    "success": False,
                    "error": str(e)
                }
        else:
            # Use mock implementation
            logger.info("Using mock SQL execution")
            result = mock_sql_result(query)
            
            return {
                "success": True,
                "data": result["data"],
                "columns": result["columns"]
            }
    except Exception as e:
        logger.error(f"Error executing SQL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

def mock_analyst_response(request_body):
    """Mock function to simulate Cortex Analyst API response"""
    user_message = request_body["messages"][-1]["content"][0]["text"]
    
    response = {
        "request_id": f"req-{int(time.time())}",
        "message": {
            "role": "analyst",
            "content": [
                {
                    "type": "text",
                    "text": f"I received your message: '{user_message}'\n\nThis is a mock response since we don't have a real Cortex Analyst API connection. In a real setup, this would provide intelligent insights based on your semantic model."
                },
                {
                    "type": "suggestions",
                    "suggestions": [
                        "Show me top customers",
                        "Analyze revenue trends",
                        "What are the KPIs?"
                    ]
                }
            ]
        }
    }
    
    # Add SQL response for certain queries
    if "sql" in user_message.lower() or "data" in user_message.lower() or "query" in user_message.lower():
        response["message"]["content"].append({
            "type": "sql",
            "statement": "SELECT * FROM customers LIMIT 10"
        })
    
    return response

def mock_sql_result(query):
    """Mock function to simulate SQL query results"""
    # Create a mock dataset
    data = []
    for i in range(10):
        data.append({
            "id": i + 1,
            "name": f"Customer {i + 1}",
            "revenue": 1000 * (i + 1),
            "region": ["North", "South", "East", "West"][i % 4]
        })
    
    return {
        "data": data,
        "columns": ["id", "name", "revenue", "region"]
    }

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