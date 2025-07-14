import os, uuid, time, httpx, msal
from typing import List, Optional
from slugify import slugify
from dotenv import load_dotenv
from flask import Flask, request, jsonify, abort
from pydantic import BaseModel, ValidationError

# ─────────────────────────────── env / auth
load_dotenv()
TENANT_ID     = os.getenv("TENANT_ID")
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE         = ["https://graph.microsoft.com/.default"]

def get_token() -> str:
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    tok = cca.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in tok:
        raise RuntimeError(f"MSAL auth failed: {tok.get('error_description')}")
    return tok["access_token"]

def graph_headers(token: str, json_ct: bool = True) -> dict:
    hdrs = {"Authorization": f"Bearer {token}"}
    if json_ct:
        hdrs["Content-Type"] = "application/json"
    return hdrs

def resolve_user_id(upn: str, client: httpx.Client, hdrs: dict) -> str:
    r = client.get(f"https://graph.microsoft.com/v1.0/users/{upn}?$select=id",
                   headers=hdrs, timeout=10)
    r.raise_for_status()
    return r.json()["id"]

# ─────────────────────────────── pydantic schemas
class SiteCreate(BaseModel):
    name: str
    ownerEmail: str
    privacy: str = "Private"
    description: Optional[str] = None
    memberEmails: Optional[List[str]] = None
    visitorEmails: Optional[List[str]] = None

class GroupChange(BaseModel):
    groupId: str
    user_upns: List[str]

# ─────────────────────────────── helpers
def add_members(gid: str, upns: list[str]):
    token = get_token()
    with httpx.Client() as http:
        hdrs = graph_headers(token)
        for upn in upns:
            oid = resolve_user_id(upn, http, hdrs)
            ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
            http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/members/$ref",
                      headers=hdrs | {"Content-Type": "application/json"},
                      json=ref, timeout=10)

def remove_members(gid: str, upns: list[str]):
    token = get_token()
    with httpx.Client() as http:
        hdrs = graph_headers(token, json_ct=False)
        for upn in upns:
            oid = resolve_user_id(upn, http, hdrs)
            http.delete(f"https://graph.microsoft.com/v1.0/groups/{gid}/members/{oid}/$ref",
                        headers=hdrs, timeout=10)

def add_owners(gid: str, upns: list[str]):
    token = get_token()
    with httpx.Client() as http:
        hdrs = graph_headers(token)
        for upn in upns:
            oid = resolve_user_id(upn, http, hdrs)
            ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
            http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
                      headers=hdrs | {"Content-Type": "application/json"},
                      json=ref, timeout=10)

def remove_owners(gid: str, upns: list[str]):
    token = get_token()
    with httpx.Client() as http:
        hdrs = graph_headers(token, json_ct=False)
        for upn in upns:
            oid = resolve_user_id(upn, http, hdrs)
            http.delete(f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/{oid}/$ref",
                        headers=hdrs, timeout=10)

def add_visitors(site_id: str, upns: list[str]):
    token = get_token()
    with httpx.Client() as http:
        hdrs = graph_headers(token)
        for upn in upns:
            oid = resolve_user_id(upn, http, hdrs)
            perm = {
                "roles": ["read"],
                "grantee": {"@odata.type": "microsoft.graph.user", "id": oid}
            }
            http.post(f"https://graph.microsoft.com/v1.0/sites/{site_id}/permissions",
                      headers=hdrs, json=perm, timeout=10)

# ─────────────────────────────── Flask app & routes
app = Flask(__name__)

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/api/sharepoint/site", methods=["POST"])
def create_site():
    try:
        req = SiteCreate(**request.get_json(force=True))
    except ValidationError as ve:
        return jsonify(ve.errors()), 422

    token = get_token()
    hdrs  = graph_headers(token)
    alias_base = slugify(req.name, separator="")

    with httpx.Client() as http:
        # retry alias up to 5x
        for _ in range(5):
            alias = f"{alias_base}-{uuid.uuid4().hex[:4]}"
            body  = {
                "displayName": req.name,
                "mailNickname": alias,
                "mailEnabled": True,
                "securityEnabled": False,
                "visibility": req.privacy,
                "groupTypes": ["Unified"],
            }
            if req.description and req.description.strip():
                body["description"] = req.description
            r = http.post("https://graph.microsoft.com/v1.0/groups",
                          headers=hdrs, json=body, timeout=30)
            if r.status_code == 201:
                gid = r.json()["id"]
                break
            if r.status_code == 400 and "mailNickname" in r.text:
                continue
            return r.text, r.status_code
        else:
            abort(409, "alias collisions")

        # initial owner
        oid = resolve_user_id(req.ownerEmail, http, hdrs)
        http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
                  headers=hdrs, json={"@odata.id":
                      f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}, timeout=10)

        # poll for site
        for _ in range(12):
            s = http.get(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/sites/root?$select=webUrl,id",
                headers=hdrs, timeout=15)
            if s.status_code == 200:
                j = s.json()
                site_url, site_id = j["webUrl"], j["id"]
                break
            time.sleep(5)
        else:
            abort(504, "site provisioning timeout")

        # optional extras
        if req.memberEmails:
            add_members(gid, req.memberEmails)
        if req.visitorEmails:
            add_visitors(site_id, req.visitorEmails)

    return {"groupId": gid, "siteId": site_id, "siteUrl": site_url}

# ---- owners
@app.route("/api/sharepoint/owners", methods=["POST"])
def add_owners_route():
    body = GroupChange(**request.get_json(force=True))
    add_owners(body.groupId, body.user_upns)
    return {"addedOwners": body.user_upns}

@app.route("/api/sharepoint/owners", methods=["DELETE"])
def remove_owners_route():
    body = GroupChange(**request.get_json(force=True))
    remove_owners(body.groupId, body.user_upns)
    return {"removedOwners": body.user_upns}

# ---- members
@app.route("/api/sharepoint/members", methods=["POST"])
def add_members_route():
    body = GroupChange(**request.get_json(force=True))
    add_members(body.groupId, body.user_upns)
    return {"addedMembers": body.user_upns}

@app.route("/api/sharepoint/members", methods=["DELETE"])
def remove_members_route():
    body = GroupChange(**request.get_json(force=True))
    remove_members(body.groupId, body.user_upns)
    return {"removedMembers": body.user_upns}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
