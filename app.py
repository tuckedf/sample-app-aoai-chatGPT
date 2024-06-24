import copy
import json
import os
import logging
import uuid
import requests
import httpx
import hashlib
import time
from dotenv import load_dotenv
from urllib.parse import urlencode
from quart import Quart, session, request, jsonify
from azure.cosmos import CosmosClient, exceptions
from azure.core.exceptions import ResourceNotFoundError
from redis import Redis





from quart import (
    Blueprint,
    Quart,
    jsonify,
    make_response,
    request,
    send_from_directory,
    render_template,
)




from openai import AsyncAzureOpenAI
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from backend.auth.auth_utils import get_authenticated_user_details
from backend.history.cosmosdbservice import CosmosConversationClient

from backend.utils import format_as_ndjson, format_stream_response, generateFilterString, parse_multi_columns, format_non_streaming_response
from urllib.parse import urlparse
import requests

from quart.sessions import SessionInterface, SessionMixin
from azure.cosmos import PartitionKey
from uuid import uuid4

class RedisSession(dict, SessionMixin):
    def __init__(self, initial=None, sid=None):
        self.sid = sid or str(uuid4())
        super().__init__(initial or {})

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.modified = True

    def __delitem__(self, key):
        super().__delitem__(key)
        self.modified = True

class RedisSessionInterface(SessionInterface):
    def __init__(self, redis_client):
        self.client = redis_client

    async def open_session(self, app, request):
        sid = request.cookies.get(app.config['SESSION_COOKIE_NAME'])
        if sid is None:
            sid = str(uuid4())  # generate a new sid if it's None

        stored_session = None
        try:
            stored_session = self.client.get(sid)
            if stored_session is not None:
                stored_session = json.loads(stored_session)
        except Exception as e:
            print(f"Error getting session from Redis: {e}")

        if stored_session is None:
            stored_session = {'id': sid}
            self.client.set(sid, json.dumps(stored_session))

        return RedisSession(initial=stored_session, sid=sid)

    async def save_session(self, app, session, response):
        session_dict = {**session, 'id': session.sid}
        try:
            self.client.set(session.sid, json.dumps(session_dict))
        except Exception as e:
            print(f"Error saving session to Redis: {e}")
        response.set_cookie(app.config['SESSION_COOKIE_NAME'], session.sid)







bp = Blueprint("routes", __name__, static_folder="static", template_folder="static")



# UI configuration (optional)
UI_TITLE = os.environ.get("UI_TITLE") or "Contoso"
UI_LOGO = os.environ.get("UI_LOGO")
UI_CHAT_LOGO = os.environ.get("UI_CHAT_LOGO")
UI_CHAT_TITLE = os.environ.get("UI_CHAT_TITLE") or "Start chatting"
UI_CHAT_DESCRIPTION = os.environ.get("UI_CHAT_DESCRIPTION") or "This chatbot is configured to answer your questions"
UI_FAVICON = os.environ.get("UI_FAVICON") or "/favicon.ico"
UI_SHOW_SHARE_BUTTON = os.environ.get("UI_SHOW_SHARE_BUTTON", "true").lower() == "true"

# COSMODB Account Settings
AZURE_COSMOSDB_ACCOUNT = os.environ.get("AZURE_COSMOSDB_ACCOUNT")
AZURE_COSMOSDB_ACCOUNT_KEY = os.environ.get("AZURE_COSMOSDB_ACCOUNT_KEY")

# COSMODB Chat History Settings Settings
AZURE_COSMOSDB_DATABASE = os.environ.get("AZURE_COSMOSDB_DATABASE")
AZURE_COSMOSDB_CONVERSATIONS_CONTAINER = os.environ.get("AZURE_COSMOSDB_CONVERSATIONS_CONTAINER")

# COSMODB Sessions Mangement Settings
AZURE_COSMOSDB_SESSIONS_DATABASE = os.environ.get("AZURE_COSMOSDB_SESSIONS_DATABASE")
AZURE_COSMOSDB_SESSIONS_CONTAINER= os.environ.get("AZURE_COSMOSDB_SESSIONS_CONTAINER")
AZURE_COSMOSDB_DOC_URL= os.environ.get("AZURE_COSMOSDB_DOC_URL")

# COSMODB Enable Feedback
AZURE_COSMOSDB_ENABLE_FEEDBACK = os.environ.get("AZURE_COSMOSDB_ENABLE_FEEDBACK", "false").lower() == "true"
SESSION_NAME = os.environ.get("SESSION_NAME", "tuckbot_session")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "zi3dfaha7d.snsh5587hmshd")

#Azure Cache for Redis settings
REDIS_HOST= os.environ.get("REDIS_HOST")
REDIS_PORT= os.environ.get("REDIS_PORT")
REDIS_PASSWORD= os.environ.get("REDIS_PASSWORD")


# Initialize Redis client
redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, ssl=True, ssl_cert_reqs=None)

url = AZURE_COSMOSDB_DOC_URL
key = AZURE_COSMOSDB_ACCOUNT_KEY
cosmos_client = CosmosClient(url, credential=key)

# Get the database client
database = cosmos_client.get_database_client(AZURE_COSMOSDB_SESSIONS_DATABASE)

# Get the container client
container = database.get_container_client(AZURE_COSMOSDB_SESSIONS_CONTAINER)

def create_app():
    app = Quart(__name__)
    app.secret_key = SESSION_SECRET
    app.register_blueprint(bp)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    cosmos_client = init_cosmosdb_client()
    app.config['SESSION_COOKIE_NAME'] = SESSION_NAME
   # Initialize Redis session interface
    app.session_interface = RedisSessionInterface(redis_client)

    return app


@bp.route("/")
async def index():
    return await render_template("index.html", title=UI_TITLE, favicon=UI_FAVICON)

@bp.route("/favicon.ico")
async def favicon():
    return await bp.send_static_file("favicon.ico")

@bp.route("/assets/<path:path>")
async def assets(path):
    return await send_from_directory("static/assets", path)

load_dotenv()

# Debug settings
DEBUG = os.environ.get("DEBUG", "false")
if DEBUG.lower() == "true":
    logging.basicConfig(level=logging.DEBUG)

USER_AGENT = "GitHubSampleWebApp/AsyncAzureOpenAI/1.0.0"

# On Your Data Settings
DATASOURCE_TYPE = os.environ.get("DATASOURCE_TYPE", "AzureCognitiveSearch")
SEARCH_TOP_K = os.environ.get("SEARCH_TOP_K", 5)
SEARCH_STRICTNESS = os.environ.get("SEARCH_STRICTNESS", 3)
SEARCH_ENABLE_IN_DOMAIN = os.environ.get("SEARCH_ENABLE_IN_DOMAIN", "true")

# ACS Integration Settings
AZURE_SEARCH_SERVICE = os.environ.get("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_INDEX = os.environ.get("AZURE_SEARCH_INDEX")
AZURE_SEARCH_KEY = os.environ.get("AZURE_SEARCH_KEY", None)
AZURE_SEARCH_USE_SEMANTIC_SEARCH = os.environ.get("AZURE_SEARCH_USE_SEMANTIC_SEARCH", "false")
AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG = os.environ.get("AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG", "default")
AZURE_SEARCH_TOP_K = os.environ.get("AZURE_SEARCH_TOP_K", SEARCH_TOP_K)
AZURE_SEARCH_ENABLE_IN_DOMAIN = os.environ.get("AZURE_SEARCH_ENABLE_IN_DOMAIN", SEARCH_ENABLE_IN_DOMAIN)
AZURE_SEARCH_CONTENT_COLUMNS = os.environ.get("AZURE_SEARCH_CONTENT_COLUMNS")
AZURE_SEARCH_FILENAME_COLUMN = os.environ.get("AZURE_SEARCH_FILENAME_COLUMN")
AZURE_SEARCH_TITLE_COLUMN = os.environ.get("AZURE_SEARCH_TITLE_COLUMN")
AZURE_SEARCH_URL_COLUMN = os.environ.get("AZURE_SEARCH_URL_COLUMN")
AZURE_SEARCH_VECTOR_COLUMNS = os.environ.get("AZURE_SEARCH_VECTOR_COLUMNS")
AZURE_SEARCH_QUERY_TYPE = os.environ.get("AZURE_SEARCH_QUERY_TYPE")
AZURE_SEARCH_PERMITTED_GROUPS_COLUMN = os.environ.get("AZURE_SEARCH_PERMITTED_GROUPS_COLUMN")
AZURE_SEARCH_STRICTNESS = os.environ.get("AZURE_SEARCH_STRICTNESS", SEARCH_STRICTNESS)

# AOAI Integration Settings
AZURE_OPENAI_RESOURCE = os.environ.get("AZURE_OPENAI_RESOURCE")
AZURE_OPENAI_MODEL = os.environ.get("AZURE_OPENAI_MODEL")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY")
AZURE_OPENAI_TEMPERATURE = os.environ.get("AZURE_OPENAI_TEMPERATURE", 0)
AZURE_OPENAI_TOP_P = os.environ.get("AZURE_OPENAI_TOP_P", 1.0)
AZURE_OPENAI_MAX_TOKENS = os.environ.get("AZURE_OPENAI_MAX_TOKENS", 1000)
AZURE_OPENAI_STOP_SEQUENCE = os.environ.get("AZURE_OPENAI_STOP_SEQUENCE")
AZURE_OPENAI_SYSTEM_MESSAGE = os.environ.get("AZURE_OPENAI_SYSTEM_MESSAGE", "You are an AI assistant that helps people find information.")
AZURE_OPENAI_SYSTEM_MESSAGE_TUTOR = os.environ.get("AZURE_OPENAI_SYSTEM_MESSAGE_TUTOR", "You are an upbeat, encouraging tutor who helps students understand concepts by explaining ideas and asking students questions. Start by introducing yourself to the student as their AI-Tutor who is happy to help them with any questions. Only ask one question at a time. First, ask them what they would like to learn about. Wait for the response. Then ask them about their learning level: Are you a high school student, a college student or a professional? Wait for their response. Then ask them what they know already about the topic they have chosen. Wait for a response. Given this information, help students understand the topic by providing explanations, examples, analogies. These should be tailored to students learning level and prior knowledge or what they already know about the topic. Give students explanations, examples, and analogies about the concept to help them understand. You should guide students in an open-ended way. Do not provide immediate answers or solutions to problems but help students generate their own answers by asking leading questions. Ask students to explain their thinking. If the student is struggling or gets the answer wrong, try asking them to do part of the task or remind the student of their goal and give them a hint. If students improve, then praise them and show excitement. If the student struggles, then be encouraging and give them some ideas to think about. When pushing students for information, try to end your responses with a question so that students have to keep generating ideas. Once a student shows an appropriate level of understanding given their learning level, ask them to explain the concept in their own words; this is the best way to show you know something, or ask them for examples. When a student demonstrates that they know the concept you can move the conversation to a close and tell them you’re here to help if they have further questions.")
AZURE_OPENAI_PREVIEW_API_VERSION = os.environ.get("AZURE_OPENAI_PREVIEW_API_VERSION", "2023-12-01-preview")
AZURE_OPENAI_STREAM = os.environ.get("AZURE_OPENAI_STREAM", "true")
AZURE_OPENAI_MODEL_NAME = os.environ.get("AZURE_OPENAI_MODEL_NAME", "gpt-35-turbo-16k") # Name of the model, e.g. 'gpt-35-turbo-16k' or 'gpt-4'
AZURE_OPENAI_EMBEDDING_ENDPOINT = os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT")
AZURE_OPENAI_EMBEDDING_KEY = os.environ.get("AZURE_OPENAI_EMBEDDING_KEY")
AZURE_OPENAI_EMBEDDING_NAME = os.environ.get("AZURE_OPENAI_EMBEDDING_NAME", "")

# CosmosDB Mongo vcore vector db Settings
AZURE_COSMOSDB_MONGO_VCORE_CONNECTION_STRING = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_CONNECTION_STRING")  #This has to be secure string
AZURE_COSMOSDB_MONGO_VCORE_DATABASE = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_DATABASE")
AZURE_COSMOSDB_MONGO_VCORE_CONTAINER = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_CONTAINER")
AZURE_COSMOSDB_MONGO_VCORE_INDEX = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_INDEX")
AZURE_COSMOSDB_MONGO_VCORE_TOP_K = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_TOP_K", AZURE_SEARCH_TOP_K)
AZURE_COSMOSDB_MONGO_VCORE_STRICTNESS = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_STRICTNESS", AZURE_SEARCH_STRICTNESS)  
AZURE_COSMOSDB_MONGO_VCORE_ENABLE_IN_DOMAIN = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_ENABLE_IN_DOMAIN", AZURE_SEARCH_ENABLE_IN_DOMAIN)
AZURE_COSMOSDB_MONGO_VCORE_CONTENT_COLUMNS = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_CONTENT_COLUMNS", "")
AZURE_COSMOSDB_MONGO_VCORE_FILENAME_COLUMN = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_FILENAME_COLUMN")
AZURE_COSMOSDB_MONGO_VCORE_TITLE_COLUMN = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_TITLE_COLUMN")
AZURE_COSMOSDB_MONGO_VCORE_URL_COLUMN = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_URL_COLUMN")
AZURE_COSMOSDB_MONGO_VCORE_VECTOR_COLUMNS = os.environ.get("AZURE_COSMOSDB_MONGO_VCORE_VECTOR_COLUMNS")

SHOULD_STREAM = True if AZURE_OPENAI_STREAM.lower() == "true" else False



# Elasticsearch Integration Settings
ELASTICSEARCH_ENDPOINT = os.environ.get("ELASTICSEARCH_ENDPOINT")
ELASTICSEARCH_ENCODED_API_KEY = os.environ.get("ELASTICSEARCH_ENCODED_API_KEY")
ELASTICSEARCH_INDEX = os.environ.get("ELASTICSEARCH_INDEX")
ELASTICSEARCH_QUERY_TYPE = os.environ.get("ELASTICSEARCH_QUERY_TYPE", "simple")
ELASTICSEARCH_TOP_K = os.environ.get("ELASTICSEARCH_TOP_K", SEARCH_TOP_K)
ELASTICSEARCH_ENABLE_IN_DOMAIN = os.environ.get("ELASTICSEARCH_ENABLE_IN_DOMAIN", SEARCH_ENABLE_IN_DOMAIN)
ELASTICSEARCH_CONTENT_COLUMNS = os.environ.get("ELASTICSEARCH_CONTENT_COLUMNS")
ELASTICSEARCH_FILENAME_COLUMN = os.environ.get("ELASTICSEARCH_FILENAME_COLUMN")
ELASTICSEARCH_TITLE_COLUMN = os.environ.get("ELASTICSEARCH_TITLE_COLUMN")
ELASTICSEARCH_URL_COLUMN = os.environ.get("ELASTICSEARCH_URL_COLUMN")
ELASTICSEARCH_VECTOR_COLUMNS = os.environ.get("ELASTICSEARCH_VECTOR_COLUMNS")
ELASTICSEARCH_STRICTNESS = os.environ.get("ELASTICSEARCH_STRICTNESS", SEARCH_STRICTNESS)
ELASTICSEARCH_EMBEDDING_MODEL_ID = os.environ.get("ELASTICSEARCH_EMBEDDING_MODEL_ID")

# Pinecone Integration Settings
PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME")
PINECONE_TOP_K = os.environ.get("PINECONE_TOP_K", SEARCH_TOP_K)
PINECONE_STRICTNESS = os.environ.get("PINECONE_STRICTNESS", SEARCH_STRICTNESS)  
PINECONE_ENABLE_IN_DOMAIN = os.environ.get("PINECONE_ENABLE_IN_DOMAIN", SEARCH_ENABLE_IN_DOMAIN)
PINECONE_CONTENT_COLUMNS = os.environ.get("PINECONE_CONTENT_COLUMNS", "")
PINECONE_FILENAME_COLUMN = os.environ.get("PINECONE_FILENAME_COLUMN")
PINECONE_TITLE_COLUMN = os.environ.get("PINECONE_TITLE_COLUMN")
PINECONE_URL_COLUMN = os.environ.get("PINECONE_URL_COLUMN")
PINECONE_VECTOR_COLUMNS = os.environ.get("PINECONE_VECTOR_COLUMNS")

# Azure AI MLIndex Integration Settings - for use with MLIndex data assets created in Azure AI Studio
AZURE_MLINDEX_NAME = os.environ.get("AZURE_MLINDEX_NAME")
AZURE_MLINDEX_VERSION = os.environ.get("AZURE_MLINDEX_VERSION")
AZURE_ML_PROJECT_RESOURCE_ID = os.environ.get("AZURE_ML_PROJECT_RESOURCE_ID") # /subscriptions/{sub ID}/resourceGroups/{rg name}/providers/Microsoft.MachineLearningServices/workspaces/{AML project name}
AZURE_MLINDEX_TOP_K = os.environ.get("AZURE_MLINDEX_TOP_K", SEARCH_TOP_K)
AZURE_MLINDEX_STRICTNESS = os.environ.get("AZURE_MLINDEX_STRICTNESS", SEARCH_STRICTNESS)  
AZURE_MLINDEX_ENABLE_IN_DOMAIN = os.environ.get("AZURE_MLINDEX_ENABLE_IN_DOMAIN", SEARCH_ENABLE_IN_DOMAIN)
AZURE_MLINDEX_CONTENT_COLUMNS = os.environ.get("AZURE_MLINDEX_CONTENT_COLUMNS", "")
AZURE_MLINDEX_FILENAME_COLUMN = os.environ.get("AZURE_MLINDEX_FILENAME_COLUMN")
AZURE_MLINDEX_TITLE_COLUMN = os.environ.get("AZURE_MLINDEX_TITLE_COLUMN")
AZURE_MLINDEX_URL_COLUMN = os.environ.get("AZURE_MLINDEX_URL_COLUMN")
AZURE_MLINDEX_VECTOR_COLUMNS = os.environ.get("AZURE_MLINDEX_VECTOR_COLUMNS")
AZURE_MLINDEX_QUERY_TYPE = os.environ.get("AZURE_MLINDEX_QUERY_TYPE")

# Canvas Integration
CANVAS_API_KEY = os.environ.get("CANVAS_API_KEY")

# Tuck APIs
TUCK_AI_SEARCH_TEMPLATE_URL = os.environ.get("TUCK_AI_SEARCH_TEMPLATE_URL")
TUCK_AZURE_API_KEY = os.environ.get("TUCK_AZURE_API_KEY")
CAS_VALIDATION_URL = os.environ.get("CAS_VALIDATION_URL")
HOST_PROTOCOL = os.environ.get("HOST_PROTOCOL")

# Frontend Settings via Environment Variables
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
CHAT_HISTORY_ENABLED = AZURE_COSMOSDB_ACCOUNT and AZURE_COSMOSDB_DATABASE and AZURE_COSMOSDB_CONVERSATIONS_CONTAINER
frontend_settings = { 
    "auth_enabled": AUTH_ENABLED, 
    "feedback_enabled": AZURE_COSMOSDB_ENABLE_FEEDBACK and CHAT_HISTORY_ENABLED,
    "ui": {
        "title": UI_TITLE,
        "logo": UI_LOGO,
        "chat_logo": UI_CHAT_LOGO or UI_LOGO,
        "chat_title": UI_CHAT_TITLE,
        "chat_description": UI_CHAT_DESCRIPTION,
        "show_share_button": UI_SHOW_SHARE_BUTTON
    }
}



def validate_cas_ticket(ticket, service):
    # CAS server's serviceValidate URL
    cas_url = 'https://login.dartmouth.edu/cas/serviceValidate'
    
    params = {'ticket': ticket, 'service': service, 'format': 'json'}
    encoded_params = urlencode(params)
    response = requests.get(cas_url, params=encoded_params)
    logging.debug('CAS Validation Response')
    logging.debug(response.text)
    if response.status_code == 200:
        # Parse the response JSON to check for authentication success
        response_json = response.json()
        if 'authenticationSuccess' in response_json.get('serviceResponse', {}):
            return True
        else:
            return False
    else:
        print(f'Error: {response.status_code}')
        return False
    

def should_use_data():
    global DATASOURCE_TYPE
    if AZURE_SEARCH_SERVICE and AZURE_SEARCH_INDEX:
        DATASOURCE_TYPE = "AzureCognitiveSearch"
        logging.debug("Using Azure Cognitive Search")
        return True
    
    if AZURE_COSMOSDB_MONGO_VCORE_DATABASE and AZURE_COSMOSDB_MONGO_VCORE_CONTAINER and AZURE_COSMOSDB_MONGO_VCORE_INDEX and AZURE_COSMOSDB_MONGO_VCORE_CONNECTION_STRING:
        DATASOURCE_TYPE = "AzureCosmosDB"
        logging.debug("Using Azure CosmosDB Mongo vcore")
        return True
    
    if ELASTICSEARCH_ENDPOINT and ELASTICSEARCH_ENCODED_API_KEY and ELASTICSEARCH_INDEX:
        DATASOURCE_TYPE = "Elasticsearch"
        logging.debug("Using Elasticsearch")
        return True
    
    if PINECONE_ENVIRONMENT and PINECONE_API_KEY and PINECONE_INDEX_NAME:
        DATASOURCE_TYPE = "Pinecone"
        logging.debug("Using Pinecone")
        return True
    
    if AZURE_MLINDEX_NAME and AZURE_MLINDEX_VERSION and AZURE_ML_PROJECT_RESOURCE_ID:
        DATASOURCE_TYPE = "AzureMLIndex"
        logging.debug("Using Azure ML Index")
        return True

    return False

SHOULD_USE_DATA = should_use_data()

# Initialize Azure OpenAI Client
def init_openai_client(use_data=SHOULD_USE_DATA):
    azure_openai_client = None
    try:
        # Endpoint
        if not AZURE_OPENAI_ENDPOINT and not AZURE_OPENAI_RESOURCE:
            raise Exception("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_RESOURCE is required")
        
        endpoint = AZURE_OPENAI_ENDPOINT if AZURE_OPENAI_ENDPOINT else f"https://{AZURE_OPENAI_RESOURCE}.openai.azure.com/"
        
        # Authentication
        aoai_api_key = AZURE_OPENAI_KEY
        ad_token_provider = None
        if not aoai_api_key:
            logging.debug("No AZURE_OPENAI_KEY found, using Azure AD auth")
            ad_token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

        # Deployment
        deployment = AZURE_OPENAI_MODEL
        if not deployment:
            raise Exception("AZURE_OPENAI_MODEL is required")

        # Default Headers
        default_headers = {
            'x-ms-useragent': USER_AGENT
        }

        if use_data:
            base_url = f"{str(endpoint).rstrip('/')}/openai/deployments/{deployment}/extensions"
            azure_openai_client = AsyncAzureOpenAI(
                base_url=str(base_url),
                api_version=AZURE_OPENAI_PREVIEW_API_VERSION,
                api_key=aoai_api_key,
                azure_ad_token_provider=ad_token_provider,
                default_headers=default_headers,
            )
        else:
            azure_openai_client = AsyncAzureOpenAI(
                api_version=AZURE_OPENAI_PREVIEW_API_VERSION,
                api_key=aoai_api_key,
                azure_ad_token_provider=ad_token_provider,
                default_headers=default_headers,
                azure_endpoint=endpoint
            )
        return azure_openai_client
    except Exception as e:
        logging.exception("Exception in Azure OpenAI initialization", e)
        azure_openai_client = None
        raise e


def init_cosmosdb_client():
    cosmos_conversation_client = None
    if CHAT_HISTORY_ENABLED:
        try:
            cosmos_endpoint = f'https://{AZURE_COSMOSDB_ACCOUNT}.documents.azure.com:443/'

            if not AZURE_COSMOSDB_ACCOUNT_KEY:
                credential = DefaultAzureCredential()
            else:
                credential = AZURE_COSMOSDB_ACCOUNT_KEY

            cosmos_conversation_client = CosmosConversationClient(
                cosmosdb_endpoint=cosmos_endpoint, 
                credential=credential, 
                database_name=AZURE_COSMOSDB_DATABASE,
                container_name=AZURE_COSMOSDB_CONVERSATIONS_CONTAINER,
                enable_message_feedback=AZURE_COSMOSDB_ENABLE_FEEDBACK
            )
        except Exception as e:
            logging.exception("Exception in CosmosDB initialization", e)
            cosmos_conversation_client = None
            raise e
    else:
        logging.debug("CosmosDB not configured")
        
    return cosmos_conversation_client


def get_configured_data_source():


    if session.get('prompt_type', 'default') == 'tutor':
        AZURE_OPENAI_SYSTEM_MESSAGE_CURRENT = AZURE_OPENAI_SYSTEM_MESSAGE_TUTOR
        logging.debug('current system message')
        logging.debug(AZURE_OPENAI_SYSTEM_MESSAGE_CURRENT)  
    else:
        AZURE_OPENAI_SYSTEM_MESSAGE_CURRENT = AZURE_OPENAI_SYSTEM_MESSAGE
        logging.debug('current system message')
        logging.debug(AZURE_OPENAI_SYSTEM_MESSAGE_CURRENT)  
        

    url = TUCK_AI_SEARCH_TEMPLATE_URL
    headers = {'Authorization': 'Bearer ' + TUCK_AZURE_API_KEY}
    params = {'action': 'generate_template', 'user_id': session['user']}
   

    response = requests.get(url, headers=headers, params=params)
    print(f'Template Data: {response}')

    if response.status_code == 200:
        data = response.json()
        query_filter = data['filter']
        logging.debug(session['user'])
        logging.debug('query filter')
        logging.debug(f"QUERY FILTER: {json.dumps(query_filter, indent=4)}")
        # Continue with the rest of the function using the courses data
    else:
        print(f'Error: {response.status_code}')
        # Handle error       
    
    data_source = {}
    query_type = "simple"
    if DATASOURCE_TYPE == "AzureCognitiveSearch":
        # Set query type
        if AZURE_SEARCH_QUERY_TYPE:
            query_type = AZURE_SEARCH_QUERY_TYPE
        elif AZURE_SEARCH_USE_SEMANTIC_SEARCH.lower() == "true" and AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG:
            query_type = "semantic"

        # Set filter
        filter = None
        userToken = None
        if AZURE_SEARCH_PERMITTED_GROUPS_COLUMN:
            userToken = request.headers.get('X-MS-TOKEN-AAD-ACCESS-TOKEN', "")
            logging.debug(f"USER TOKEN is {'present' if userToken else 'not present'}")
            if not userToken:
                raise Exception("Document-level access control is enabled, but user access token could not be fetched.")

            filter = generateFilterString(userToken)
            logging.debug(f"FILTER: {filter}")
        
        # Set authentication
        authentication = {}
        if AZURE_SEARCH_KEY:
            authentication = {
                "type": "APIKey",
                "key": AZURE_SEARCH_KEY,
                "apiKey": AZURE_SEARCH_KEY
            }
        else:
            # If key is not provided, assume AOAI resource identity has been granted access to the search service
            authentication = {
                "type": "SystemAssignedManagedIdentity"
            }

        data_source = {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
                    "authentication": authentication,
                    "indexName": AZURE_SEARCH_INDEX,
                    "fieldsMapping": {
                        "contentFields": parse_multi_columns(AZURE_SEARCH_CONTENT_COLUMNS) if AZURE_SEARCH_CONTENT_COLUMNS else [],
                        "titleField": AZURE_SEARCH_TITLE_COLUMN if AZURE_SEARCH_TITLE_COLUMN else None,
                        "urlField": AZURE_SEARCH_URL_COLUMN if AZURE_SEARCH_URL_COLUMN else None,
                        "filepathField": AZURE_SEARCH_FILENAME_COLUMN if AZURE_SEARCH_FILENAME_COLUMN else None,
                        "vectorFields": parse_multi_columns(AZURE_SEARCH_VECTOR_COLUMNS) if AZURE_SEARCH_VECTOR_COLUMNS else []
                    },
                    "inScope": True if AZURE_SEARCH_ENABLE_IN_DOMAIN.lower() == "true" else False,
                    "topNDocuments": int(AZURE_SEARCH_TOP_K) if AZURE_SEARCH_TOP_K else int(SEARCH_TOP_K),
                    "queryType": query_type,
                    "semanticConfiguration": AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG if AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG else "",
                    "roleInformation": AZURE_OPENAI_SYSTEM_MESSAGE_CURRENT,
                    "filter": query_filter, # Dynamic from template
                  # "filter": filter, # Default 'None' set above.
                    "strictness": int(AZURE_SEARCH_STRICTNESS) if AZURE_SEARCH_STRICTNESS else int(SEARCH_STRICTNESS)
                }
            }
        logging.debug('data source')
        logging.debug(data_source)
    elif DATASOURCE_TYPE == "AzureCosmosDB":
        query_type = "vector"

        data_source = {
                "type": "AzureCosmosDB",
                "parameters": {
                    "authentication": {
                        "type": "ConnectionString",
                        "connectionString": AZURE_COSMOSDB_MONGO_VCORE_CONNECTION_STRING
                    },
                    "indexName": AZURE_COSMOSDB_MONGO_VCORE_INDEX,
                    "databaseName": AZURE_COSMOSDB_MONGO_VCORE_DATABASE,
                    "containerName": AZURE_COSMOSDB_MONGO_VCORE_CONTAINER,                    
                    "fieldsMapping": {
                        "contentFields": parse_multi_columns(AZURE_COSMOSDB_MONGO_VCORE_CONTENT_COLUMNS) if AZURE_COSMOSDB_MONGO_VCORE_CONTENT_COLUMNS else [],
                        "titleField": AZURE_COSMOSDB_MONGO_VCORE_TITLE_COLUMN if AZURE_COSMOSDB_MONGO_VCORE_TITLE_COLUMN else None,
                        "urlField": AZURE_COSMOSDB_MONGO_VCORE_URL_COLUMN if AZURE_COSMOSDB_MONGO_VCORE_URL_COLUMN else None,
                        "filepathField": AZURE_COSMOSDB_MONGO_VCORE_FILENAME_COLUMN if AZURE_COSMOSDB_MONGO_VCORE_FILENAME_COLUMN else None,
                        "vectorFields": parse_multi_columns(AZURE_COSMOSDB_MONGO_VCORE_VECTOR_COLUMNS) if AZURE_COSMOSDB_MONGO_VCORE_VECTOR_COLUMNS else []
                    },
                    "inScope": True if AZURE_COSMOSDB_MONGO_VCORE_ENABLE_IN_DOMAIN.lower() == "true" else False,
                    "topNDocuments": int(AZURE_COSMOSDB_MONGO_VCORE_TOP_K) if AZURE_COSMOSDB_MONGO_VCORE_TOP_K else int(SEARCH_TOP_K),
                    "strictness": int(AZURE_COSMOSDB_MONGO_VCORE_STRICTNESS) if AZURE_COSMOSDB_MONGO_VCORE_STRICTNESS else int(SEARCH_STRICTNESS),
                    "queryType": query_type,
                    "roleInformation": AZURE_OPENAI_SYSTEM_MESSAGE
                }
            }
    elif DATASOURCE_TYPE == "Elasticsearch":
        if ELASTICSEARCH_QUERY_TYPE:
            query_type = ELASTICSEARCH_QUERY_TYPE

        data_source = {
            "type": "Elasticsearch",
            "parameters": {
                "endpoint": ELASTICSEARCH_ENDPOINT,
                "authentication": {
                    "type": "EncodedAPIKey",
                    "encodedApiKey": ELASTICSEARCH_ENCODED_API_KEY
                },
                "indexName": ELASTICSEARCH_INDEX,
                "fieldsMapping": {
                    "contentFields": parse_multi_columns(ELASTICSEARCH_CONTENT_COLUMNS) if ELASTICSEARCH_CONTENT_COLUMNS else [],
                    "titleField": ELASTICSEARCH_TITLE_COLUMN if ELASTICSEARCH_TITLE_COLUMN else None,
                    "urlField": ELASTICSEARCH_URL_COLUMN if ELASTICSEARCH_URL_COLUMN else None,
                    "filepathField": ELASTICSEARCH_FILENAME_COLUMN if ELASTICSEARCH_FILENAME_COLUMN else None,
                    "vectorFields": parse_multi_columns(ELASTICSEARCH_VECTOR_COLUMNS) if ELASTICSEARCH_VECTOR_COLUMNS else []
                },
                "inScope": True if ELASTICSEARCH_ENABLE_IN_DOMAIN.lower() == "true" else False,
                "topNDocuments": int(ELASTICSEARCH_TOP_K) if ELASTICSEARCH_TOP_K else int(SEARCH_TOP_K),
                "queryType": query_type,
                "roleInformation": AZURE_OPENAI_SYSTEM_MESSAGE,
                "strictness": int(ELASTICSEARCH_STRICTNESS) if ELASTICSEARCH_STRICTNESS else int(SEARCH_STRICTNESS)
            }
        }
    elif DATASOURCE_TYPE == "AzureMLIndex":
        if AZURE_MLINDEX_QUERY_TYPE:
            query_type = AZURE_MLINDEX_QUERY_TYPE

        data_source = {
            "type": "AzureMLIndex",
            "parameters": {
                "name": AZURE_MLINDEX_NAME,
                "version": AZURE_MLINDEX_VERSION,
                "projectResourceId": AZURE_ML_PROJECT_RESOURCE_ID,
                "fieldsMapping": {
                    "contentFields": parse_multi_columns(AZURE_MLINDEX_CONTENT_COLUMNS) if AZURE_MLINDEX_CONTENT_COLUMNS else [],
                    "titleField": AZURE_MLINDEX_TITLE_COLUMN if AZURE_MLINDEX_TITLE_COLUMN else None,
                    "urlField": AZURE_MLINDEX_URL_COLUMN if AZURE_MLINDEX_URL_COLUMN else None,
                    "filepathField": AZURE_MLINDEX_FILENAME_COLUMN if AZURE_MLINDEX_FILENAME_COLUMN else None,
                    "vectorFields": parse_multi_columns(AZURE_MLINDEX_VECTOR_COLUMNS) if AZURE_MLINDEX_VECTOR_COLUMNS else []
                },
                "inScope": True if AZURE_MLINDEX_ENABLE_IN_DOMAIN.lower() == "true" else False,
                "topNDocuments": int(AZURE_MLINDEX_TOP_K) if AZURE_MLINDEX_TOP_K else int(SEARCH_TOP_K),
                "queryType": query_type,
                "roleInformation": AZURE_OPENAI_SYSTEM_MESSAGE,
                "strictness": int(AZURE_MLINDEX_STRICTNESS) if AZURE_MLINDEX_STRICTNESS else int(SEARCH_STRICTNESS)
            }
        }
    elif DATASOURCE_TYPE == "Pinecone":
        query_type = "vector"

        data_source = {
            "type": "Pinecone",
            "parameters": {
                "environment": PINECONE_ENVIRONMENT,
                "authentication": {
                    "type": "APIKey",
                    "key": PINECONE_API_KEY
                },
                "indexName": PINECONE_INDEX_NAME,
                "fieldsMapping": {
                    "contentFields": parse_multi_columns(PINECONE_CONTENT_COLUMNS) if PINECONE_CONTENT_COLUMNS else [],
                    "titleField": PINECONE_TITLE_COLUMN if PINECONE_TITLE_COLUMN else None,
                    "urlField": PINECONE_URL_COLUMN if PINECONE_URL_COLUMN else None,
                    "filepathField": PINECONE_FILENAME_COLUMN if PINECONE_FILENAME_COLUMN else None,
                    "vectorFields": parse_multi_columns(PINECONE_VECTOR_COLUMNS) if PINECONE_VECTOR_COLUMNS else []
                },
                "inScope": True if PINECONE_ENABLE_IN_DOMAIN.lower() == "true" else False,
                "topNDocuments": int(PINECONE_TOP_K) if PINECONE_TOP_K else int(SEARCH_TOP_K),
                "strictness": int(PINECONE_STRICTNESS) if PINECONE_STRICTNESS else int(SEARCH_STRICTNESS),
                "queryType": query_type,
                "roleInformation": AZURE_OPENAI_SYSTEM_MESSAGE,
            }
        }
    else:
        raise Exception(f"DATASOURCE_TYPE is not configured or unknown: {DATASOURCE_TYPE}")

    if "vector" in query_type.lower() and DATASOURCE_TYPE != "AzureMLIndex":
        embeddingDependency = {}
        if AZURE_OPENAI_EMBEDDING_NAME:
            embeddingDependency = {
                "type": "DeploymentName",
                "deploymentName": AZURE_OPENAI_EMBEDDING_NAME
            }
        elif AZURE_OPENAI_EMBEDDING_ENDPOINT and AZURE_OPENAI_EMBEDDING_KEY:
            embeddingDependency = {
                "type": "Endpoint",
                "endpoint": AZURE_OPENAI_EMBEDDING_ENDPOINT,
                "authentication": {
                    "type": "APIKey",
                    "key": AZURE_OPENAI_EMBEDDING_KEY
                }
            }
        elif DATASOURCE_TYPE == "Elasticsearch" and ELASTICSEARCH_EMBEDDING_MODEL_ID:
            embeddingDependency = {
                "type": "ModelId",
                "modelId": ELASTICSEARCH_EMBEDDING_MODEL_ID
            }
        else:
            raise Exception(f"Vector query type ({query_type}) is selected for data source type {DATASOURCE_TYPE} but no embedding dependency is configured")
        data_source["parameters"]["embeddingDependency"] = embeddingDependency

    return data_source

def prepare_model_args(request_body):
    request_messages = request_body.get("messages", [])
    messages = []
    if not SHOULD_USE_DATA:
        messages = [
            {
                "role": "system",
                "content": AZURE_OPENAI_SYSTEM_MESSAGE
            }
        ]

    for message in request_messages:
        if message:
            messages.append({
                "role": message["role"] ,
                "content": message["content"]
            })

    model_args = {
        "messages": messages,
        "temperature": float(AZURE_OPENAI_TEMPERATURE),
        "max_tokens": int(AZURE_OPENAI_MAX_TOKENS),
        "top_p": float(AZURE_OPENAI_TOP_P),
        "stop": parse_multi_columns(AZURE_OPENAI_STOP_SEQUENCE) if AZURE_OPENAI_STOP_SEQUENCE else None,
        "stream": SHOULD_STREAM,
        "model": AZURE_OPENAI_MODEL,
    }

    if SHOULD_USE_DATA:
        model_args["extra_body"] = {
            "dataSources": [get_configured_data_source()]
        }

    model_args_clean = copy.deepcopy(model_args)
    if model_args_clean.get("extra_body"):
        secret_params = ["key", "connectionString", "embeddingKey", "encodedApiKey", "apiKey"]
        for secret_param in secret_params:
            if model_args_clean["extra_body"]["dataSources"][0]["parameters"].get(secret_param):
                model_args_clean["extra_body"]["dataSources"][0]["parameters"][secret_param] = "*****"
        authentication = model_args_clean["extra_body"]["dataSources"][0]["parameters"].get("authentication", {})
        for field in authentication:
            if field in secret_params:
                model_args_clean["extra_body"]["dataSources"][0]["parameters"]["authentication"][field] = "*****"
        embeddingDependency = model_args_clean["extra_body"]["dataSources"][0]["parameters"].get("embeddingDependency", {})
        if "authentication" in embeddingDependency:
            for field in embeddingDependency["authentication"]:
                if field in secret_params:
                    model_args_clean["extra_body"]["dataSources"][0]["parameters"]["embeddingDependency"]["authentication"][field] = "*****"
        
    logging.debug(f"REQUEST BODY: {json.dumps(model_args_clean, indent=4)}")
    
    return model_args

async def send_chat_request(request):
    model_args = prepare_model_args(request)
    print(f"Model arguments: {model_args}")  # Print the model arguments

    try:
        azure_openai_client = init_openai_client()
        response = await azure_openai_client.chat.completions.create(**model_args)

    except Exception as e:
        logging.exception("Exception in send_chat_request")
        raise e

    return response

async def complete_chat_request(request_body):
    response = await send_chat_request(request_body)
    history_metadata = request_body.get("history_metadata", {})

    return format_non_streaming_response(response, history_metadata)

async def stream_chat_request(request_body):
    response = await send_chat_request(request_body)
    history_metadata = request_body.get("history_metadata", {})

    async def generate():
        async for completionChunk in response:
            yield format_stream_response(completionChunk, history_metadata)

    return generate()

async def conversation_internal(request_body):
    try:
        if SHOULD_STREAM:
            result = await stream_chat_request(request_body)
            response = await make_response(format_as_ndjson(result))
            response.timeout = None
            response.mimetype = "application/json-lines"
            return response
        else:
            result = await complete_chat_request(request_body)
            return jsonify(result)
    
    except Exception as ex:
        logging.exception(ex)
        if hasattr(ex, "status_code"):
            return jsonify({"error": str(ex)}), ex.status_code
        else:
            return jsonify({"error": str(ex)}), 500


@bp.route("/conversation", methods=["POST"])
async def conversation():
    if not request.is_json:
        return jsonify({"error": "request must be json"}), 415
    request_json = await request.get_json()
    
    return await conversation_internal(request_json)

@bp.route("/frontend_settings", methods=["GET"])  
def get_frontend_settings():
    try:
        return jsonify(frontend_settings), 200
    except Exception as e:
        logging.exception("Exception in /frontend_settings")
        return jsonify({"error": str(e)}), 500  
    
 

## Conversation History API ## 
@bp.route("/history/generate", methods=["POST"])
async def add_conversation():
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get('conversation_id', None)

    try:
        # make sure cosmos is configured
        cosmos_conversation_client = init_cosmosdb_client()
        if not cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        # check for the conversation_id, if the conversation is not set, we will create a new one
        history_metadata = {}
        if not conversation_id:
            title = await generate_title(request_json["messages"])
            conversation_dict = await cosmos_conversation_client.create_conversation(user_id=user_id, title=title)
            conversation_id = conversation_dict['id']
            history_metadata['title'] = title
            history_metadata['date'] = conversation_dict['createdAt']
            
        ## Format the incoming message object in the "chat/completions" messages format
        ## then write it to the conversation history in cosmos
        messages = request_json["messages"]
        if len(messages) > 0 and messages[-1]['role'] == "user":
            createdMessageValue = await cosmos_conversation_client.create_message(
                uuid=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=messages[-1]
            )
            if createdMessageValue == "Conversation not found":
                raise Exception("Conversation not found for the given conversation ID: " + conversation_id + ".")
        else:
            raise Exception("No user message found")
        
        await cosmos_conversation_client.cosmosdb_client.close()
        
        # Submit request to Chat Completions for response
        request_body = await request.get_json()
        history_metadata['conversation_id'] = conversation_id
        request_body['history_metadata'] = history_metadata
        return await conversation_internal(request_body)
       
    except Exception as e:
        logging.exception("Exception in /history/generate")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/update", methods=["POST"])
async def update_conversation():
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get('conversation_id', None)

    try:
        # make sure cosmos is configured
        cosmos_conversation_client = init_cosmosdb_client()
        if not cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        # check for the conversation_id, if the conversation is not set, we will create a new one
        if not conversation_id:
            raise Exception("No conversation_id found")
            
        ## Format the incoming message object in the "chat/completions" messages format
        ## then write it to the conversation history in cosmos
        messages = request_json["messages"]
        if len(messages) > 0 and messages[-1]['role'] == "assistant":
            if len(messages) > 1 and messages[-2].get('role', None) == "tool":
                # write the tool message first
                await cosmos_conversation_client.create_message(
                    uuid=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    input_message=messages[-2]
                )
            # write the assistant message
            await cosmos_conversation_client.create_message(
                uuid=messages[-1]['id'],
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=messages[-1]
            )
        else:
            raise Exception("No bot messages found")
        
        # Submit request to Chat Completions for response
        await cosmos_conversation_client.cosmosdb_client.close()
        response = {'success': True}
        return jsonify(response), 200
       
    except Exception as e:
        logging.exception("Exception in /history/update")
        return jsonify({"error": str(e)}), 500

@bp.route("/history/message_feedback", methods=["POST"])
async def update_message():
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()
    cosmos_conversation_client = init_cosmosdb_client()

    ## check request for message_id
    request_json = await request.get_json()
    message_id = request_json.get('message_id', None)
    message_feedback = request_json.get("message_feedback", None)
    try:
        if not message_id:
            return jsonify({"error": "message_id is required"}), 400
        
        if not message_feedback:
            return jsonify({"error": "message_feedback is required"}), 400
        
        ## update the message in cosmos
        updated_message = await cosmos_conversation_client.update_message_feedback(user_id, message_id, message_feedback)
        if updated_message:
            return jsonify({"message": f"Successfully updated message with feedback {message_feedback}", "message_id": message_id}), 200
        else:
            return jsonify({"error": f"Unable to update message {message_id}. It either does not exist or the user does not have access to it."}), 404
        
    except Exception as e:
        logging.exception("Exception in /history/message_feedback")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/delete", methods=["DELETE"])
async def delete_conversation():
    ## get the user id from the request headers
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()
    
    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get('conversation_id', None)

    try: 
        if not conversation_id:
            return jsonify({"error": "conversation_id is required"}), 400
        
        ## make sure cosmos is configured
        cosmos_conversation_client = init_cosmosdb_client()
        if not cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        ## delete the conversation messages from cosmos first
        deleted_messages = await cosmos_conversation_client.delete_messages(conversation_id, user_id)

        ## Now delete the conversation 
        deleted_conversation = await cosmos_conversation_client.delete_conversation(user_id, conversation_id)

        await cosmos_conversation_client.cosmosdb_client.close()

        return jsonify({"message": "Successfully deleted conversation and messages", "conversation_id": conversation_id}), 200
    except Exception as e:
        logging.exception("Exception in /history/delete")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/list", methods=["GET"])
async def list_conversations():
    offset = request.args.get("offset", 0)
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()

    ## make sure cosmos is configured
    cosmos_conversation_client = init_cosmosdb_client()
    if not cosmos_conversation_client:
        raise Exception("CosmosDB is not configured or not working")

    ## get the conversations from cosmos
    conversations = await cosmos_conversation_client.get_conversations(user_id, offset=offset, limit=25)
    await cosmos_conversation_client.cosmosdb_client.close()
    if not isinstance(conversations, list):
        return jsonify({"error": f"No conversations for {user_id} were found"}), 404

    ## return the conversation ids

    return jsonify(conversations), 200


@bp.route("/history/read", methods=["POST"])
async def get_conversation():
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get('conversation_id', None)
    
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    
    ## make sure cosmos is configured
    cosmos_conversation_client = init_cosmosdb_client()
    if not cosmos_conversation_client:
        raise Exception("CosmosDB is not configured or not working")

    ## get the conversation object and the related messages from cosmos
    conversation = await cosmos_conversation_client.get_conversation(user_id, conversation_id)
    ## return the conversation id and the messages in the bot frontend format
    if not conversation:
        return jsonify({"error": f"Conversation {conversation_id} was not found. It either does not exist or the logged in user does not have access to it."}), 404
    
    # get the messages for the conversation from cosmos
    conversation_messages = await cosmos_conversation_client.get_messages(user_id, conversation_id)

    ## format the messages in the bot frontend format
    messages = [{'id': msg['id'], 'role': msg['role'], 'content': msg['content'], 'createdAt': msg['createdAt'], 'feedback': msg.get('feedback')} for msg in conversation_messages]

    await cosmos_conversation_client.cosmosdb_client.close()
    return jsonify({"conversation_id": conversation_id, "messages": messages}), 200

@bp.route("/history/rename", methods=["POST"])
async def rename_conversation():
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get('conversation_id', None)
    
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    
    ## make sure cosmos is configured
    cosmos_conversation_client = init_cosmosdb_client()
    if not cosmos_conversation_client:
        raise Exception("CosmosDB is not configured or not working")
    
    ## get the conversation from cosmos
    conversation = await cosmos_conversation_client.get_conversation(user_id, conversation_id)
    if not conversation:
        return jsonify({"error": f"Conversation {conversation_id} was not found. It either does not exist or the logged in user does not have access to it."}), 404

    ## update the title
    title = request_json.get("title", None)
    if not title:
        return jsonify({"error": "title is required"}), 400
    conversation['title'] = title
    updated_conversation = await cosmos_conversation_client.upsert_conversation(conversation)

    await cosmos_conversation_client.cosmosdb_client.close()
    return jsonify(updated_conversation), 200

@bp.route("/history/delete_all", methods=["DELETE"])
async def delete_all_conversations():
    ## get the user id from the request headers
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()

    # get conversations for user
    try:
        ## make sure cosmos is configured
        cosmos_conversation_client = init_cosmosdb_client()
        if not cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        conversations = await cosmos_conversation_client.get_conversations(user_id, offset=0, limit=None)
        if not conversations:
            return jsonify({"error": f"No conversations for {user_id} were found"}), 404
        
        # delete each conversation
        for conversation in conversations:
            ## delete the conversation messages from cosmos first
            deleted_messages = await cosmos_conversation_client.delete_messages(conversation['id'], user_id)

            ## Now delete the conversation 
            deleted_conversation = await cosmos_conversation_client.delete_conversation(user_id, conversation['id'])
        await cosmos_conversation_client.cosmosdb_client.close()
        return jsonify({"message": f"Successfully deleted conversation and messages for user {user_id}"}), 200
    
    except Exception as e:
        logging.exception("Exception in /history/delete_all")
        return jsonify({"error": str(e)}), 500

@bp.route("/history/clear", methods=["POST"])
async def clear_messages():
    ## get the user id from the request headers
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    #user_id = authenticated_user['user_principal_id']
    user_id = hashlib.md5(session['user'].encode()).hexdigest()
    
    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get('conversation_id', None)

    try: 
        if not conversation_id:
            return jsonify({"error": "conversation_id is required"}), 400
        
        ## make sure cosmos is configured
        cosmos_conversation_client = init_cosmosdb_client()
        if not cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        ## delete the conversation messages from cosmos
        deleted_messages = await cosmos_conversation_client.delete_messages(conversation_id, user_id)

        return jsonify({"message": "Successfully deleted messages in conversation", "conversation_id": conversation_id}), 200
    except Exception as e:
        logging.exception("Exception in /history/clear_messages")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/ensure", methods=["GET"])
async def ensure_cosmos():
    if not AZURE_COSMOSDB_ACCOUNT:
        return jsonify({"error": "CosmosDB is not configured"}), 404
    
    try:
        cosmos_conversation_client = init_cosmosdb_client()
        success, err = await cosmos_conversation_client.ensure()
        if not cosmos_conversation_client or not success:
            if err:
                return jsonify({"error": err}), 422
            return jsonify({"error": "CosmosDB is not configured or not working"}), 500
        
        await cosmos_conversation_client.cosmosdb_client.close()
        return jsonify({"message": "CosmosDB is configured and working"}), 200
    except Exception as e:
        logging.exception("Exception in /history/ensure")
        cosmos_exception = str(e)
        if "Invalid credentials" in cosmos_exception:
            return jsonify({"error": cosmos_exception}), 401
        elif "Invalid CosmosDB database name" in cosmos_exception:
            return jsonify({"error": f"{cosmos_exception} {AZURE_COSMOSDB_DATABASE} for account {AZURE_COSMOSDB_ACCOUNT}"}), 422
        elif "Invalid CosmosDB container name" in cosmos_exception:
            return jsonify({"error": f"{cosmos_exception}: {AZURE_COSMOSDB_CONVERSATIONS_CONTAINER}"}), 422
        else:
            return jsonify({"error": "CosmosDB is not working"}), 500
        



from azure.cosmos import CosmosClient

@bp.route('/api/validate', methods=['GET'])
async def validate_ticket():
    # Define 'ticket' before the 'if' statement
    ticket = request.args.get('ticket')

    sid = request.cookies.get(app.config['SESSION_COOKIE_NAME'])
    print(f"Session ID: {sid}")  # print sid

    # Initialize Redis Client
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, ssl=True)

    # Check if the session exists
    stored_session = redis_client.get(sid)
    if stored_session is not None:
     stored_session = json.loads(stored_session.decode('utf-8'))
    print(f"Stored Session: {stored_session}")  # print stored session

    service = f"{HOST_PROTOCOL}://{urlparse(request.url).netloc}/"
    cas_url = CAS_VALIDATION_URL
    params = {'ticket': ticket, 'service': service, 'format': 'json'}
   
    if stored_session is None or 'user' not in stored_session:
        # If there isn't, proceed with the existing ticket validation logic
        async with httpx.AsyncClient() as client:
            response = await client.get(cas_url, params=params)

        if response.status_code != 200:
            return jsonify({'status': 'failure'}), 400

        response_json = response.json()
        if 'authenticationSuccess' not in response_json.get('serviceResponse', {}):
            return jsonify({'status': 'failure', 'ticket_data': response_json,}), 401

        # If ticket is valid, set user netid to session and return success
        user_netid = response_json['serviceResponse']['authenticationSuccess']['attributes']['netid'][0]
        session['user'] = user_netid
        session['user_id'] = user_netid
        session['message'] = True
        session['message'] = 'Verified from CAS Ticket'

    return jsonify({
    'status': 'success', 
    'session_id': session.sid, 
    'session_data': {
        'user': session.get('user'), 
        'user_id': session.get('user_id'), 
        'message': session.get('message', 'No message'),
        'redis_data': stored_session
    }
}), 200


@bp.route('/api/check_session', methods=['GET'])
async def check_session():
    sid = request.cookies.get(app.config['SESSION_COOKIE_NAME'])
    print(f"Session ID: {sid}")  # print sid

    # Check if the session exists
    stored_session = redis_client.get(sid)
    if stored_session is None:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404

    stored_session = json.loads(stored_session.decode('utf-8'))
    print(f"Stored Session: {stored_session}")  # print stored session
    return jsonify({'status': 'success', 'session': stored_session}), 200
    


#customization - add endpoint to set prompt type to session variable
@bp.route('/api/set_prompt_template', methods=['POST'])
async def set_prompt_template():
    data = await request.get_json()

    prompt_type = data.get('promptType', None)
    if prompt_type:
        print(f"Prompt Type: {prompt_type}")  # Debug log the promptType
        session['prompt_type'] = prompt_type

    return {'promptType': prompt_type}, 200



async def generate_title(conversation_messages):
    ## make sure the messages are sorted by _ts descending
    title_prompt = 'Summarize the conversation so far into a 4-word or less title. Do not use any quotation marks or punctuation. Respond with a json object in the format {{"title": string}}. Do not include any other commentary or description.'

    messages = [{'role': msg['role'], 'content': msg['content']} for msg in conversation_messages]
    messages.append({'role': 'user', 'content': title_prompt})

    try:
        azure_openai_client = init_openai_client(use_data=False)
        response = await azure_openai_client.chat.completions.create(
            model=AZURE_OPENAI_MODEL,
            messages=messages,
            temperature=1,
            max_tokens=64
        )
        
        title = json.loads(response.choices[0].message.content)['title']
        return title
    except Exception as e:
        return messages[-2]['content']
    
    
#get enrolled courses
@bp.route('/api/get_course_enrollments', methods=['GET'])
def get_course_enrollments():
    user = session.get('user')
    if not user:
        return jsonify({'error': 'User not found in session'}), 400

    url = f"https://apis.tuck.dartmouth.edu/canvas/enrollments?action=by_user&user={user}&include[]=course_id&include[]=type"
    headers = {'Authorization': 'Bearer ' + CANVAS_API_KEY}

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return jsonify(response.json()), 200
    else:
        return jsonify({'error': 'Failed to fetch data from the API'}), response.status_code




app = create_app()