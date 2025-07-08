import uuid, asyncio, httpx, slugify
from auth import get_app_token, resolve_user_id

async def add_members(gid: str, upns: list[str]):
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
            await http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/members/$ref",
                            headers=hdrs, json=ref, timeout=10)

async def add_visitors(site_id: str, upns: list[str]):
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            perm = {
              "roles": ["read"],
              "grantee": { "@odata.type": "microsoft.graph.user", "id": oid }
            }
            await http.post(f"https://graph.microsoft.com/v1.0/sites/{site_id}/permissions",
                            headers=hdrs, json=perm, timeout=10)

async def group_to_site(gid: str) -> str:
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        r = await http.get(
            f"https://graph.microsoft.com/v1.0/groups/{gid}/sites/root?$select=id",
            headers=hdrs, timeout=10)
        r.raise_for_status()
        return r.json()["id"]

async def create_team_site(req):
    base_alias = slugify.slugify(req.name, separator="")
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        gid = None
        for _ in range(5):
            alias = f"{base_alias}-{uuid.uuid4().hex[:4]}"
            body  = {
                "displayName": req.name,
                "mailNickname": alias,
                "mailEnabled": True,
                "securityEnabled": False,
                "visibility": req.privacy,
                "groupTypes": ["Unified"]
            }
            if req.description and req.description.strip():
                body["description"] = req.description
            print("Request body:", body)
            r = await http.post("https://graph.microsoft.com/v1.0/groups",
                                headers=hdrs, json=body, timeout=30)
            print("Graph response:", r.status_code, r.text)
            if r.status_code == 201:
                gid = r.json()["id"]
                break
            if r.status_code == 400 and "mailNickname" in r.text:
                continue
            r.raise_for_status()
        if not gid:
            raise Exception("Failed to create group after 5 attempts (mailNickname conflict or other error)")
        # add owner if provided
        if req.ownerEmail:
            oid = await resolve_user_id(req.ownerEmail, http, hdrs)
            owner_resp = await http.post(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
                headers=hdrs,
                json={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"},
                timeout=10
            )
            if owner_resp.status_code not in (204, 200):
                raise Exception(f"Failed to add owner: {owner_resp.status_code} {owner_resp.text}")
        # poll site and get site_id
        for _ in range(12):
            s = await http.get(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/sites/root?$select=webUrl,id",
                headers=hdrs, timeout=15)
            if s.status_code == 200:
                site_json = s.json()
                site_url  = site_json["webUrl"]
                site_id   = site_json["id"]
                break
            await asyncio.sleep(5)
        else:
            raise TimeoutError("Site provisioning timed out")
        # add members / visitors if provided
        if req.memberEmails:
            await add_members(gid, req.memberEmails)
        if req.visitorEmails:
            await add_visitors(site_id, req.visitorEmails)
        return gid, site_url, site_id

async def add_owners(gid: str, upns: list[str]):
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            ref = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{oid}"}
            await http.post(f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/$ref",
                            headers=hdrs, json=ref, timeout=10)

async def remove_owners(gid: str, upns: list[str]):
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            await http.delete(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/owners/{oid}/$ref",
                headers=hdrs, timeout=10)

async def remove_members(gid: str, upns: list[str]):
    token = get_app_token()
    hdrs  = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        for upn in upns:
            oid = await resolve_user_id(upn, http, hdrs)
            await http.delete(
                f"https://graph.microsoft.com/v1.0/groups/{gid}/members/{oid}/$ref",
                headers=hdrs, timeout=10)
