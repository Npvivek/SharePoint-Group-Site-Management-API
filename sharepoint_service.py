"""
POST /api/sharepoint/site
Body : {"name": "Marketing Hub", "privacy": "Private"}
Reply: {"siteUrl": "https://tenant.sharepoint.com/sites/market-1a2b"}
– Creates a Microsoft 365 group (team site)
– Retries up to 5 aliases if Graph says the nickname already exists
– Polls Graph until the SharePoint site is ready (≤ ~60 s)
"""

import os, uuid, asyncio, httpx, msal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from slugify import slugify
from dotenv import load_dotenv

load_dotenv()

TENANT_ID     = os.getenv("TENANT_ID")
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE     = ["https://graph.microsoft.com/.default"]

def get_token() -> str:
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
    tok = cca.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in tok:
        raise RuntimeError(f"MSAL auth failed: {tok.get('error_description')}")
    return tok["access_token"]

class SiteRequest(BaseModel):
    name: str
    privacy: str = "Private"
    description: str | None = None
    ownerEmail: str | None = None  # <-- add this line

app = FastAPI()

@app.get("/health")
async def health(): return {"status": "ok"}

@app.post("/api/sharepoint/site")
async def create_site(req: SiteRequest):
    base_alias = slugify(req.name, separator="")
    token   = get_token()
    hdrs    = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as http:
        #Retry-loop until Graph accepts the alias (≤ 5 attempts)
        for attempt in range(5):
            alias = f"{base_alias}-{uuid.uuid4().hex[:4]}"
            body  = {
                "displayName":     req.name,
                "mailNickname":    alias,
                "mailEnabled":     True,
                "securityEnabled": False,
                "visibility":      req.privacy,
                "description":     req.description or "",
                "groupTypes":      ["Unified"]
            }
            resp = await http.post("https://graph.microsoft.com/v1.0/groups",
                                   headers=hdrs, json=body, timeout=30)
            if resp.status_code == 201:          # success
                gid = resp.json()["id"]
                break
            if resp.status_code == 400 and "mailNickname" in resp.text:
                if attempt == 4:
                    raise HTTPException(409, "Could not find unique alias.")
                continue                          # try a new alias
            raise HTTPException(resp.status_code, resp.text)

        # Add owner to group if email is provided
        if req.ownerEmail:
            user_resp = await http.get(
                f"https://graph.microsoft.com/v1.0/users/{req.ownerEmail}",
                headers=hdrs, timeout=10)
            if user_resp.status_code == 200:
                user_id = user_resp.json()["id"]
                add_resp = await http.post(
                    f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
                    headers=hdrs,
                    json={"@odata.id": f"https://graph.microsoft.com/v1.0/users/{user_id}"},
                    timeout=10)
                if add_resp.status_code not in (204, 200):
                    raise HTTPException(add_resp.status_code, f"Failed to add owner: {add_resp.text}")
            else:
                raise HTTPException(user_resp.status_code, f"User lookup failed: {user_resp.text}")

        #Poll until the SharePoint site is provisioned
        for _ in range(12):                       # 12 × 5 s ≈ 1 min
            s = await http.get(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/sites/root?$select=webUrl",
                headers=hdrs, timeout=15)
            if s.status_code == 200 and "webUrl" in s.json():
                return {"siteUrl": s.json()["webUrl"]}
            if s.status_code not in (400, 404):
                raise HTTPException(s.status_code, s.text)
            await asyncio.sleep(5)

    raise HTTPException(504, "Timed out waiting for SharePoint site.")
