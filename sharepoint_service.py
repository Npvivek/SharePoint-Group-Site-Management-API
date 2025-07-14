"""
One-file SharePoint micro-service
────────────────────────────────
▶ POST  /api/sharepoint/site
   { "name": "Project X",
     "ownerEmail": "lead@corp.com",
     "memberEmails": ["dev@corp.com"],
     "visitorEmails": ["guest@corp.com"] }

   ← { "groupId": "...", "siteId": "...", "siteUrl": "..." }

▶ POST  /api/sharepoint/owners   • add owners
▶ DELETE /api/sharepoint/owners  • remove owners
▶ POST  /api/sharepoint/members  • add members
▶ DELETE /api/sharepoint/members • remove members
Body for those four =
{ "groupId": "...", "user_upns": ["alice@corp.com","bob@corp.com"] }
"""

import os, uuid, asyncio, httpx, msal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from slugify import slugify
from dotenv import load_dotenv
from typing import List, Optional

# ─────────────────────────────────────────────── env / auth
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

async def resolve_user_id(upn: str, client: httpx.AsyncClient, hdrs: dict) -> str:
    r = await client.get(
        f"https://graph.microsoft.com/v1.0/users/{upn}?$select=id",
        headers=hdrs, timeout=10
    )
    r.raise_for_status()
    return r.json()["id"]

# ─────────────────────────────────────────────── models
class SiteCreate(BaseModel):
    name: str
    ownerEmail: str                    # ← REQUIRED
    privacy: str = "Private"
    description: Optional[str] = None
    memberEmails: Optional[List[str]] = None
    visitorEmails: Optional[List[str]] = None

class GroupChange(BaseModel):
    groupId: str
    user_upns: List[str]

# ─────────────────────────────────────────────── helpers
async def add_members(gid: str, upns: list[str]):
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
            await http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/members/$ref",
                            headers=hdrs, json=ref, timeout=10)

async def remove_members(gid: str, upns: list[str]):
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            await http.delete(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/members/{oid}/$ref",
                headers=hdrs, timeout=10)

async def add_owners(gid: str, upns: list[str]):
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
            await http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
                            headers=hdrs, json=ref, timeout=10)

async def remove_owners(gid: str, upns: list[str]):
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            await http.delete(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/{oid}/$ref",
                headers=hdrs, timeout=10)

async def add_visitors(site_id: str, upns: list[str]):
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            perm = {
                "roles": ["read"],
                "grantee": {"@odata.type": "microsoft.graph.user", "id": oid}
            }
            await http.post(
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/permissions",
                headers=hdrs, json=perm, timeout=10
            )

# ─────────────────────────────────────────────── FastAPI
app = FastAPI(title="SharePoint One-file API")

@app.get("/health")
async def health(): return {"status": "ok"}

# ---------- create site ------------------------------------------------------
@app.post("/api/sharepoint/site")
async def create_site(req: SiteCreate):
    base_alias = slugify(req.name, separator="")
    token = get_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}

    async with httpx.AsyncClient() as http:
        # try up to 5 aliases
        for _ in range(5):
            alias = f"{base_alias}-{uuid.uuid4().hex[:4]}"
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
            r = await http.post("https://graph.microsoft.com/v1.0/groups",
                                headers=hdrs, json=body, timeout=30)
            if r.status_code == 201:
                gid = r.json()["id"]
                break
            if r.status_code == 400 and "mailNickname" in r.text:
                continue
            raise HTTPException(r.status_code, r.text)
        else:
            raise HTTPException(409, "Alias collision – could not create site")

        # add initial owner (required by schema, so always present)
        oid = await resolve_user_id(req.ownerEmail, http, hdrs)
        await http.post(
            f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
            headers=hdrs,
            json={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"},
            timeout=10
        )

        # poll until site exists
        for _ in range(12):
            s = await http.get(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/sites/root?$select=webUrl,id",
                headers=hdrs, timeout=15)
            if s.status_code == 200:
                site_info = s.json()
                site_url  = site_info["webUrl"]
                site_id   = site_info["id"]
                break
            await asyncio.sleep(5)
        else:
            raise HTTPException(504, "Site provisioning timed out")

        # optional members / visitors
        if req.memberEmails:
            await add_members(gid, req.memberEmails)
        if req.visitorEmails:
            await add_visitors(site_id, req.visitorEmails)

    return {"groupId": gid, "siteId": site_id, "siteUrl": site_url}

# ---------- owners -----------------------------------------------------------
@app.post("/api/sharepoint/owners")
async def api_add_owners(body: GroupChange):
    await add_owners(body.groupId, body.user_upns)
    return {"addedOwners": body.user_upns}

@app.delete("/api/sharepoint/owners")
async def api_remove_owners(body: GroupChange):
    await remove_owners(body.groupId, body.user_upns)
    return {"removedOwners": body.user_upns}

# ---------- members ----------------------------------------------------------
@app.post("/api/sharepoint/members")
async def api_add_members(body: GroupChange):
    await add_members(body.groupId, body.user_upns)
    return {"addedMembers": body.user_upns}

@app.delete("/api/sharepoint/members")
async def api_remove_members(body: GroupChange):
    await remove_members(body.groupId, body.user_upns)
    return {"removedMembers": body.user_upns}
