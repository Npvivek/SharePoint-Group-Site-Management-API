"""
Flask micro-service for creating and managing Distribution Lists (DLs)
using a modern RESTful API design.

Endpoints
──────────────
POST   /api/dl                - Create a new Distribution List.
GET    /api/dl/<group_id>     - Retrieve details for a DL.
PATCH  /api/dl/<group_id>     - Update a DL's properties, owners, or members.
DELETE /api/dl/<group_id>     - Permanently delete a DL.
"""

import os
import time
import uuid
import logging

import httpx
import msal
from typing import List, Optional
from slugify import slugify
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from pydantic import BaseModel, ValidationError
from flask_cors import CORS

# ─────────────────────── ENV + AUTH ──────────────────────────
load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CUSTOM_DOMAIN = "continuserve.com"

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]

# Global cache for the access token
_token_cache = {"token": None, "expires_at": 0}


def get_token() -> str:
    """Acquires an application access token from MSAL, using a simple in-memory cache."""
    now = time.time()
    # Check if token exists and has more than 60 seconds of validity left
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]

    app.logger.info("No valid cached token found, acquiring new token from MSAL.")
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    tok = cca.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in tok:
        raise RuntimeError(f"MSAL auth failed: {tok.get('error_description')}")

    _token_cache["token"] = tok["access_token"]
    _token_cache["expires_at"] = now + tok.get("expires_in", 3599)

    return _token_cache["token"]


def graph_headers(token: str, json_ct: bool = True) -> dict:
    """Returns standard headers for MS Graph API calls."""
    hdrs = {"Authorization": f"Bearer {token}"}
    if json_ct:
        hdrs["Content-Type"] = "application/json"
    return hdrs


# ────────────────────────── MODELS ───────────────────────────
class DLCreate(BaseModel):
    name: str
    ownerEmails: List[str]
    memberEmails: Optional[List[str]] = None


class DLUpdate(BaseModel):
    name: Optional[str] = None
    ownerEmails: Optional[List[str]] = None
    memberEmails: Optional[List[str]] = None


class DLDetails(BaseModel):
    groupId: str
    name: str
    primaryEmail: str
    owners: List[str]
    members: List[str]


# ───────────────────────── HELPERS ───────────────────────────
def resolve_user_id(upn: str, client: httpx.Client, hdrs: dict) -> str:
    """Finds a user's Object ID from their User Principal Name (email)."""
    r = client.get(f"https://graph.microsoft.com/v1.0/users/{upn}?$select=id", headers=hdrs, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def sync_group_users(http: httpx.Client, group_id: str, desired_upns_list: list[str], role: str, hdrs: dict):
    """Synchronizes owners or members of a group to match the desired list."""
    assert role in ("owners", "members")
    url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/{role}"
    
    r = http.get(f"{url}?$select=id,userPrincipalName", headers=hdrs, timeout=10)
    r.raise_for_status()
    current_users = {u["userPrincipalName"]: u["id"] for u in r.json().get("value", []) if u.get("userPrincipalName")}

    desired_upns = set(desired_upns_list)
    current_upns = set(current_users.keys())

    for upn in (desired_upns - current_upns):
        oid = resolve_user_id(upn, http, hdrs)
        ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
        http.post(f"{url}/$ref", headers=hdrs, json=ref, timeout=10).raise_for_status()

    for upn in (current_upns - desired_upns):
        oid = current_users[upn]
        http.delete(f"{url}/{oid}/$ref", headers=hdrs, timeout=10).raise_for_status()


# ─────────────────────────── APP ─────────────────────────────
app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.INFO)


@app.route("/api/dl", methods=["POST"])
def create_dl():
    """Creates a new Distribution List (M365 Group)."""
    try:
        req = DLCreate(**request.get_json(force=True))
    except ValidationError as ve:
        return jsonify(ve.errors()), 422

    gid = None
    try:
        token = get_token()
        hdrs = graph_headers(token)
        alias = slugify(req.name)

        with httpx.Client() as http:
            # 1. Resolve owner and member emails to their Object IDs first.
            # This will fail early if a user is not found, preventing partial creation.
            owner_oids = [resolve_user_id(upn, http, hdrs) for upn in req.ownerEmails]
            member_oids = []
            if req.memberEmails:
                member_oids = [resolve_user_id(upn, http, hdrs) for upn in req.memberEmails]

            # 2. Build the @odata.bind arrays for the group creation payload.
            owners_bind = [f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}" for oid in owner_oids]

            # Combine owner and member IDs, removing duplicates, to ensure owners are also members.
            all_member_oids = list(set(owner_oids + member_oids))
            members_bind = [f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}" for oid in all_member_oids]

            group_payload = {
                "displayName": req.name,
                "mailNickname": alias,
                "mailEnabled": True,
                "securityEnabled": False,
                "groupTypes": ["Unified"],
                "visibility": "Private",
                "owners@odata.bind": owners_bind,
                "members@odata.bind": members_bind,
            }

            # 3. Create the group with owners and members in a single atomic call.
            r = http.post("https://graph.microsoft.com/v1.0/groups", headers=hdrs, json=group_payload, timeout=40)
            r.raise_for_status()
            group_data = r.json()
            gid = group_data["id"]

            # 4. The group is created. Manually construct the final email with your custom domain.
            final_email = f"{alias}@{CUSTOM_DOMAIN}"
            return jsonify({
                "groupId": gid,
                "primaryEmail": final_email,
            }), 201

    except httpx.HTTPStatusError as e:
        if gid:  # Rollback if group was created but a later step failed
            app.logger.warning(f"An error occurred after creating group {gid}. Attempting rollback.")
            try:
                # Attempt to delete the group that was just created.
                rollback_hdrs = graph_headers(get_token(), json_ct=False)
                httpx.delete(f"https://graph.microsoft.com/v1.0/groups/{gid}", headers=rollback_hdrs, timeout=30)
                app.logger.info(f"Successfully rolled back (deleted) group {gid}.")
            except Exception as rollback_e:
                # Log the failure but continue to return the original error to the client.
                app.logger.error(f"CRITICAL: Failed to rollback (delete) group {gid} after creation error. Manual cleanup required. Rollback error: {rollback_e}")

        error_details = {"message": str(e)}
        if e.response:
            try:
                error_details = e.response.json()
            except Exception:
                error_details = {"message": e.response.text or "No error details provided."}
        app.logger.error(f"Graph API Error on {request.path}: {e}")
        return jsonify({"error": "Microsoft Graph API Error", "details": error_details}), e.response.status_code if e.response else 500
    except Exception as e:
        app.logger.error(f"Internal Server Error on {request.path}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected internal error occurred."}), 500


@app.route("/api/dl/<group_id>", methods=["PATCH"])
def update_dl(group_id: str):
    """Updates a DL's properties and synchronizes its users."""
    try:
        req = DLUpdate(**request.get_json(force=True))
    except ValidationError as ve:
        return jsonify(ve.errors()), 422

    try:
        token = get_token()
        with httpx.Client() as http:
            hdrs = graph_headers(token)

            # Update the display name if provided
            if req.name is not None:
                http.patch(f"https://graph.microsoft.com/v1.0/groups/{group_id}", headers=hdrs, json={"displayName": req.name}).raise_for_status()

            # The owner and member lists must be handled together to ensure consistency.
            if req.ownerEmails is not None or req.memberEmails is not None:
                
                # Assume the request payload is the complete, desired state of the group.
                # If a list isn't provided, default to an empty list for the logic below.
                desired_owners = req.ownerEmails or []
                desired_members = req.memberEmails or []

                # Sync the owners list first.
                sync_group_users(http, group_id, desired_owners, "owners", hdrs)

                # Now, create the definitive list of members, ensuring it includes all owners.
                all_final_members = list(set(desired_owners + desired_members))
                
                # Sync the members list with this complete and correct list.
                sync_group_users(http, group_id, all_final_members, "members", hdrs)

        return jsonify({"message": f"Group {group_id} updated successfully."})
    except httpx.HTTPStatusError as e:
        error_details = {"message": str(e)}
        if e.response:
            try: error_details = e.response.json()
            except Exception: error_details = {"message": e.response.text or "No details provided."}
        app.logger.error(f"Graph API Error on {request.path}: {e}")
        return jsonify({"error": "Microsoft Graph API Error", "details": error_details}), e.response.status_code if e.response else 500
    except Exception as e:
        app.logger.error(f"Internal Server Error on {request.path}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected internal error occurred."}), 500


@app.route("/api/dl/<group_id>", methods=["GET"])
def get_dl_details(group_id: str):
    """Retrieves consolidated details for a Distribution List."""
    try:
        token = get_token()
        with httpx.Client() as http:
            hdrs = graph_headers(token)

            group_r = http.get(f"https://graph.microsoft.com/v1.0/groups/{group_id}?$select=id,displayName,proxyAddresses", headers=hdrs)
            group_r.raise_for_status()
            group_data = group_r.json()

            owners_r = http.get(f"https://graph.microsoft.com/v1.0/groups/{group_id}/owners?$select=userPrincipalName", headers=hdrs)
            owners_r.raise_for_status()
            owners_data = owners_r.json().get("value", [])

            members_r = http.get(f"https://graph.microsoft.com/v1.0/groups/{group_id}/members?$select=userPrincipalName", headers=hdrs)
            members_r.raise_for_status()
            members_data = members_r.json().get("value", [])

            primary_email = next((addr.split(':', 1)[1] for addr in group_data.get("proxyAddresses", []) if addr.startswith("SMTP:")), "N/A")

            details = {
                "groupId": group_data["id"],
                "name": group_data["displayName"],
                "primaryEmail": primary_email,
                "owners": [owner.get("userPrincipalName") for owner in owners_data if owner.get("userPrincipalName")],
                "members": [member.get("userPrincipalName") for member in members_data if member.get("userPrincipalName")]
            }
            return DLDetails(**details).model_dump(), 200

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return jsonify({"error": "Resource not found. The DL may have been deleted."}), 404
        error_details = {"message": str(e)}
        if e.response:
            try:
                error_details = e.response.json()
            except Exception:
                error_details = {"message": e.response.text or "No error details provided."}
        app.logger.error(f"Graph API Error on {request.path}: {e}")
        return jsonify({"error": "Microsoft Graph API Error", "details": error_details}), e.response.status_code if e.response else 500
    except Exception as e:
        app.logger.error(f"Internal Server Error on {request.path}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected internal error occurred."}), 500


@app.route("/api/dl/<group_id>", methods=["DELETE"])
def delete_dl(group_id: str):
    """Permanently deletes a Microsoft 365 Group."""
    try:
        token = get_token()
        with httpx.Client() as http:
            hdrs = graph_headers(token, json_ct=False)

            soft_delete_r = http.delete(f"https://graph.microsoft.com/v1.0/groups/{group_id}", headers=hdrs, timeout=30)
            if soft_delete_r.status_code not in (204, 404):
                soft_delete_r.raise_for_status()

            perm_delete_url = f"https://graph.microsoft.com/v1.0/directory/deletedItems/{group_id}"
            for attempt in range(5):
                perm_delete_r = http.delete(perm_delete_url, headers=hdrs, timeout=30)
                if perm_delete_r.status_code == 204:
                    app.logger.info(f"Permanently deleted group {group_id} on attempt {attempt + 1}.")
                    return jsonify({"message": f"Distribution List {group_id} permanently deleted."}), 200
                if perm_delete_r.status_code == 404:
                    app.logger.info(f"Delete attempt {attempt + 1}: Group {group_id} not yet in deletedItems. Retrying...")
                    time.sleep(1)
                    continue
                perm_delete_r.raise_for_status()
            
            app.logger.warning(f"Group {group_id} was not found for permanent deletion after 5 attempts. Assuming it's already gone.")
            return jsonify({"message": f"Distribution List {group_id} permanently deleted."}), 200
    except httpx.HTTPStatusError as e:
        error_details = {"message": str(e)}
        if e.response:
            try:
                error_details = e.response.json()
            except Exception:
                error_details = {"message": e.response.text or "No error details provided."}
        app.logger.error(f"Graph API Error on {request.path}: {e}")
        return jsonify({"error": "Microsoft Graph API Error", "details": error_details}), e.response.status_code if e.response else 500
    except Exception as e:
        app.logger.error(f"Internal Server Error on {request.path}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected internal error occurred."}), 500



# --------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)