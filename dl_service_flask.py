"""
Distribution List Management API

A Flask-based REST API for managing Microsoft 365 Distribution Lists (DLs)
using the Microsoft Graph and Exchange Online APIs.
Optimized for reduced latency through batching and concurrent execution.
"""

import atexit
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import httpx
import msal
from dotenv import load_dotenv
from flask import Flask, g, has_request_context, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, EmailStr, ValidationError, field_validator
from slugify import slugify

# --- 1. Configuration (No Changes) ---
class AppConfig:
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.load_config()
        return cls._instance
    def load_config(self):
        load_dotenv()
        self.TENANT_ID, self.CLIENT_ID, self.CLIENT_SECRET = os.getenv("TENANT_ID"), os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET")
        self.CUSTOM_DOMAIN, self.CORS_ORIGIN = os.getenv("CUSTOM_DOMAIN", "example.com"), os.getenv("CORS_ORIGIN", "*")
        if not all([self.TENANT_ID, self.CLIENT_ID, self.CLIENT_SECRET]):
            raise ValueError("Missing required environment variables: TENANT_ID, CLIENT_ID, CLIENT_SECRET")
        self.AUTHORITY = f"https://login.microsoftonline.com/{self.TENANT_ID}"
        self.EXO_SCOPE, self.GRAPH_SCOPE = ["https://outlook.office365.com/.default"], ["https://graph.microsoft.com/.default"]
        self.GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
        self.EXO_REST_ENDPOINT = f"https://outlook.office365.com/adminapi/beta/{self.TENANT_ID}/InvokeCommand"
        self.OWNERS_AS_MEMBERS = os.getenv("OWNERS_AS_MEMBERS", "true").lower() == "true"

# --- 2. Pydantic Models (No Changes) ---
class DLCreate(BaseModel):
    name: str
    ownerEmails: List[EmailStr]
    memberEmails: Optional[List[EmailStr]] = None
    allowExternalSenders: bool = False
    @field_validator("ownerEmails")
    @classmethod
    def must_have_at_least_one_owner(cls, v):
        if not v: raise ValueError("At least one owner is required")
        return v
class DLUpdate(BaseModel):
    name: Optional[str] = None
    displayName: Optional[str] = None
    ownerEmails: Optional[List[EmailStr]] = None
    memberEmails: Optional[List[EmailStr]] = None
    allowExternalSenders: Optional[bool] = None
class DLDetails(BaseModel):
    dlId: str
    name: str
    displayName: str
    primaryEmail: str
    owners: List[str]
    members: List[str]
    allowExternalSenders: bool

# --- 3. Custom Exceptions (No Changes) ---
class ApiError(Exception):
    status_code = 500
    message = "An unexpected API error occurred."
    def __init__(self, message: str = None, details: dict = None):
        super().__init__(message)
        if message: self.message = message
        self.details = details or {}
class NotFoundError(ApiError):
    status_code = 404
    message = "The requested resource was not found."
class ConflictError(ApiError):
    status_code = 409
    message = "A resource with the same name or identifier already exists."
class BadRequestError(ApiError):
    status_code = 400

# --- 4. Centralized Logging (No Changes) ---
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(g, "request_id", "-") if has_request_context() else "-"
        return True
class SafeRequestIdFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return super().format(record)
def setup_logging():
    formatter = SafeRequestIdFormatter('%(asctime)s - %(levelname)s - [%(request_id)s] - %(name)s - %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.addFilter(RequestIdFilter())
    root_logger.setLevel(logging.INFO)
    logging.getLogger("werkzeug").propagate = True
    logging.getLogger("gunicorn.error").propagate = True

# --- 5. Authentication (No Changes) ---
class AuthManager:
    _instance, _lock = None, threading.Lock()
    def __new__(cls, config: AppConfig):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.config = config
                cls._instance.cca = msal.ConfidentialClientApplication(config.CLIENT_ID, authority=config.AUTHORITY, client_credential=config.CLIENT_SECRET)
                cls._instance.token_cache = {}
        return cls._instance
    def get_token(self, scope: List[str]) -> str:
        scope_key, now, token_info = scope[0], time.time(), self.token_cache.get(scope[0], {})
        if token_info.get("token") and token_info.get("expires_at", 0) > now + 60: return token_info["token"]
        with self._lock:
            token_info = self.token_cache.get(scope_key, {})
            if token_info.get("token") and token_info.get("expires_at", 0) > now + 60: return token_info["token"]
            logging.info(f"Acquiring new token for scope: {scope_key}")
            result = self.cca.acquire_token_for_client(scopes=scope)
            if "access_token" not in result: raise RuntimeError(f"MSAL auth failed: {result.get('error_description')}")
            self.token_cache[scope_key] = {"token": result["access_token"], "expires_at": now + result.get("expires_in", 3599)}
            return self.token_cache[scope_key]["token"]

# --- 6. API Clients (Optimized) ---

class BaseApiClient: # (No Changes)
    RETRY_ATTEMPTS, RETRY_BACKOFF_FACTOR = 3, 2
    def __init__(self, http_client: httpx.Client):
        self.http_client = http_client
    def _handle_http_error(self, e: httpx.HTTPStatusError):
        try: details = e.response.json()
        except Exception: details = {"raw": e.response.text}
        if e.response.status_code == 404: raise NotFoundError(details=details) from e
        if "already exists" in str(details).lower(): raise ConflictError(details=details) from e
        raise ApiError(f"API Error: {e.response.status_code} {e.response.reason_phrase}", details=details) from e

class ExchangeApiClient(BaseApiClient): # (No Changes)
    def __init__(self, config: AppConfig, auth_manager: AuthManager, http_client: httpx.Client):
        super().__init__(http_client)
        self.config, self.auth_manager = config, auth_manager
    def invoke_command(self, command_name: str, parameters: dict, anchor_mailbox: str = None) -> dict:
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                token = self.auth_manager.get_token(self.config.EXO_SCOPE)
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                if anchor_mailbox: headers["X-AnchorMailbox"] = anchor_mailbox
                payload = {"CmdletInput": {"CmdletName": command_name, "Parameters": parameters}}
                response = self.http_client.post(self.config.EXO_REST_ENDPOINT, headers=headers, json=payload, timeout=120)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in [429, 503] and attempt < self.RETRY_ATTEMPTS - 1:
                    time.sleep(self.RETRY_BACKOFF_FACTOR ** attempt)
                else: self._handle_http_error(e)
        raise ApiError(f"Exchange API request failed after {self.RETRY_ATTEMPTS} attempts.")

class GraphApiClient(BaseApiClient):
    """Client for interacting with the Microsoft Graph API."""
    def __init__(self, config: AppConfig, auth_manager: AuthManager, http_client: httpx.Client):
        super().__init__(http_client)
        self.config, self.auth_manager = config, auth_manager
    def _get_auth_headers(self) -> Dict[str, str]:
        token = self.auth_manager.get_token(self.config.GRAPH_SCOPE)
        return {"Authorization": f"Bearer {token}"}

    # --- OPTIMIZATION: BATCH USER VALIDATION ---
    def validate_users_exist_batch(self, upns: List[str]):
        """Validates a list of users in a single batch request to reduce latency."""
        if not upns: return
        
        unique_upns = list(set(upns))
        batch_requests = [{"id": str(i), "method": "GET", "url": f"/users/{upn}?$select=id"} for i, upn in enumerate(unique_upns)]
        batch_payload = {"requests": batch_requests}
        url = f"{self.config.GRAPH_BASE_URL}/$batch"
        
        try:
            response = self.http_client.post(url, headers=self._get_auth_headers(), json=batch_payload, timeout=30)
            response.raise_for_status()
            
            not_found_users = []
            for i, res in enumerate(response.json().get("responses", [])):
                if res.get("status") == 404:
                    not_found_users.append(unique_upns[i])
            
            if not_found_users:
                raise BadRequestError(f"The following users do not exist: {', '.join(not_found_users)}")
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
    
    def resolve_user_emails_from_ids(self, user_ids: List[str]) -> List[str]: # (No changes)
        if not user_ids: return []
        batch_requests = [{"id": str(i + 1), "method": "GET", "url": f"/users/{uid}?$select=userPrincipalName"} for i, uid in enumerate(user_ids)]
        batch_payload = {"requests": batch_requests}
        url = f"{self.config.GRAPH_BASE_URL}/$batch"
        try:
            response = self.http_client.post(url, headers=self._get_auth_headers(), json=batch_payload, timeout=30)
            response.raise_for_status()
            return [res["body"]["userPrincipalName"] for res in response.json().get("responses", []) if res.get("status") == 200]
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)

# --- 7. Service Layer (Optimized) ---

class DLService:
    """Encapsulates the business logic for managing Distribution Lists."""
    def __init__(self, config: AppConfig, exo_client: ExchangeApiClient, graph_client: GraphApiClient, executor: ThreadPoolExecutor):
        self.config, self.exo_client, self.graph_client, self.executor = config, exo_client, graph_client, executor

    # --- OPTIMIZATION: USE BATCH VALIDATION ---
    def _validate_users_exist(self, emails: List[str]):
        """Wrapper for the new batch validation method."""
        self.graph_client.validate_users_exist_batch(emails)

    def _add_member_with_retries(self, dl_alias_member_tuple):
        """Helper for concurrent execution that accepts a tuple."""
        dl_alias, member_upn = dl_alias_member_tuple
        for attempt in range(3):
            try:
                self.exo_client.invoke_command("Add-DistributionGroupMember", {"Identity": dl_alias, "Member": member_upn})
                logging.info(f"Successfully added member '{member_upn}' to '{dl_alias}'.")
                return True
            except ConflictError:
                logging.warning(f"Member '{member_upn}' already exists in '{dl_alias}'.")
                return True
            except ApiError as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    logging.error(f"Final failure to add member '{member_upn}': {e.message}")
                    return False
        return False

    def create_dl(self, dl_data: DLCreate) -> Dict[str, str]:
        """Creates a new Distribution List and populates its members concurrently."""
        alias = slugify(dl_data.name)
        self._validate_users_exist(dl_data.ownerEmails + (dl_data.memberEmails or []))

        dl_params = {
            "Name": alias, "DisplayName": dl_data.name, "Alias": alias, "ManagedBy": dl_data.ownerEmails,
            "RequireSenderAuthenticationEnabled": not dl_data.allowExternalSenders,
            "PrimarySmtpAddress": f"{alias}@{self.config.CUSTOM_DOMAIN}"
        }
        self.exo_client.invoke_command("New-DistributionGroup", dl_params, anchor_mailbox=dl_data.ownerEmails[0])
        logging.info(f"DL '{alias}' created. Waiting for replication...")
        time.sleep(5) # This delay is for reliability and is hard to avoid.

        members_to_add = set(dl_data.memberEmails or [])
        if self.config.OWNERS_AS_MEMBERS:
            members_to_add.update(dl_data.ownerEmails)

        # --- OPTIMIZATION: CONCURRENT MEMBER ADDITION ---
        if members_to_add:
            logging.info(f"Concurrently adding {len(members_to_add)} members to '{alias}'...")
            # Create a list of tuples (alias, member_email) for the executor
            tasks = [(alias, member) for member in members_to_add]
            results = list(self.executor.map(self._add_member_with_retries, tasks))
            if not all(results):
                logging.warning(f"One or more members failed to be added to '{alias}'.")

        return {"dlId": alias, "primaryEmail": dl_params["PrimarySmtpAddress"]}

    def get_dl_details(self, dl_id: str) -> Dict: # (No significant latency change possible)
        dl_props = self.exo_client.invoke_command("Get-DistributionGroup", {"Identity": dl_id})["value"][0]
        members = [m["PrimarySmtpAddress"] for m in self.exo_client.invoke_command("Get-DistributionGroupMember", {"Identity": dl_id}).get("value", []) if "PrimarySmtpAddress" in m]
        owner_emails = self.graph_client.resolve_user_emails_from_ids(dl_props.get("ManagedBy", []))
        return {
            "dlId": dl_props.get("Name"), "name": dl_props.get("Name"), "displayName": dl_props.get("DisplayName"),
            "primaryEmail": dl_props.get("PrimarySmtpAddress"), "owners": owner_emails, "members": members,
            "allowExternalSenders": not dl_props.get("RequireSenderAuthenticationEnabled", True)
        }

    def update_dl(self, dl_id: str, update_data: DLUpdate): # (Logic is now more complex, no changes made)
        current_props = self.exo_client.invoke_command("Get-DistributionGroup", {"Identity": dl_id})["value"][0]
        dl_alias = current_props["Name"]
        props_to_update = {"Identity": dl_alias}
        if update_data.name:
            new_alias = slugify(update_data.name)
            props_to_update.update({"Name": new_alias, "Alias": new_alias, "PrimarySmtpAddress": f"{new_alias}@{self.config.CUSTOM_DOMAIN}"})
            dl_alias = new_alias
        if update_data.displayName is not None: props_to_update["DisplayName"] = update_data.displayName
        if update_data.allowExternalSenders is not None: props_to_update["RequireSenderAuthenticationEnabled"] = not update_data.allowExternalSenders
        if len(props_to_update) > 1: self.exo_client.invoke_command("Set-DistributionGroup", props_to_update)
        if update_data.ownerEmails is not None:
            self._validate_users_exist(update_data.ownerEmails)
            self.exo_client.invoke_command("Set-DistributionGroup", {"Identity": dl_alias, "ManagedBy": update_data.ownerEmails})
        if update_data.memberEmails is not None:
            self._validate_users_exist(update_data.memberEmails)
            desired_members = set(update_data.memberEmails)
            if self.config.OWNERS_AS_MEMBERS:
                final_owners = update_data.ownerEmails if update_data.ownerEmails is not None else self.graph_client.resolve_user_emails_from_ids(current_props.get("ManagedBy", []))
                desired_members.update(final_owners)
            current_members = {m["PrimarySmtpAddress"] for m in self.exo_client.invoke_command("Get-DistributionGroupMember", {"Identity": dl_alias}).get("value", []) if "PrimarySmtpAddress" in m}
            to_add = desired_members - current_members
            to_remove = current_members - desired_members
            if to_add:
                add_tasks = [(dl_alias, member) for member in to_add]
                self.executor.map(self._add_member_with_retries, add_tasks)
            if to_remove:
                # Removal is typically fast, but can be parallelized too if needed
                for member in to_remove: self.exo_client.invoke_command("Remove-DistributionGroupMember", {"Identity": dl_alias, "Member": member, "Confirm": False})

    def delete_dl(self, dl_id: str): # (No change)
        self.exo_client.invoke_command("Remove-DistributionGroup", {"Identity": dl_id, "Confirm": False})

# --- 8. Flask App Factory & Routes (Optimized) ---

def create_app(config: AppConfig) -> Flask:
    """Creates and configures the Flask application and its dependencies."""
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGIN}})

    # --- OPTIMIZATION: ADD A THREAD POOL FOR CONCURRENT TASKS ---
    executor = ThreadPoolExecutor(max_workers=10)
    
    # Dependency Injection Setup
    http_client = httpx.Client()
    auth_manager = AuthManager(config)
    graph_client = GraphApiClient(config, auth_manager, http_client)
    exo_client = ExchangeApiClient(config, auth_manager, http_client)
    dl_service = DLService(config, exo_client, graph_client, executor)

    def close_clients():
        executor.shutdown(wait=True)
        http_client.close()
    atexit.register(close_clients)

    @app.before_request
    def assign_request_id(): g.request_id = str(uuid.uuid4())
    
    def validate_dl_id(dl_id: str):
        if not re.match(r'^[a-zA-Z0-9\-\._@=, ]+$', dl_id): raise BadRequestError(f"Invalid format for dl_id: '{dl_id}'.")

    @app.route("/api/dl", methods=["POST"])
    def create_dl_route():
        dl_data = DLCreate(**request.get_json())
        result = dl_service.create_dl(dl_data)
        return jsonify(result), 201

    # (Other routes remain the same)
    @app.route("/api/dl/<string:dl_id>", methods=["GET"])
    def get_dl_route(dl_id: str):
        validate_dl_id(dl_id); result = dl_service.get_dl_details(dl_id)
        return DLDetails(**result).model_dump(), 200
    @app.route("/api/dl/<string:dl_id>", methods=["PATCH"])
    def update_dl_route(dl_id: str):
        validate_dl_id(dl_id); update_data = DLUpdate(**request.get_json())
        dl_service.update_dl(dl_id, update_data)
        return jsonify({"message": f"Distribution List '{dl_id}' updated successfully."}), 200
    @app.route("/api/dl/<string:dl_id>", methods=["DELETE"])
    def delete_dl_route(dl_id: str):
        validate_dl_id(dl_id); dl_service.delete_dl(dl_id)
        return jsonify({"message": f"Distribution List '{dl_id}' deleted successfully."}), 200

    # (Error handlers remain the same)
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        logging.error(f"API Error: {error.message} - Details: {error.details}")
        return jsonify({"error": error.message, "details": error.details}), error.status_code
    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        logging.warning(f"Validation Error: {error.errors()}")
        return jsonify({"error": "Validation Error", "details": error.errors()}), 422
    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception):
        logging.critical(f"Unhandled Exception: {error}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500

    return app

# --- Application Entry Point (No Changes) ---
if __name__ == "__main__":
    setup_logging()
    app_config = AppConfig()
    flask_app = create_app(app_config)
    flask_app.run(host="0.0.0.0", port=7000, debug=True)