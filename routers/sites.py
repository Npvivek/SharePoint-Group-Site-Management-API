from fastapi import APIRouter, HTTPException
from models import SiteCreate, GroupChange
from services import sharepoint

router = APIRouter(prefix="/api/sharepoint", tags=["sharepoint"])

@router.post("/site")
async def api_create_site(req: SiteCreate):
    try:
        gid, url, sid = await sharepoint.create_team_site(req)
        return {"groupId": gid, "siteId": sid, "siteUrl": url}
    except TimeoutError as e:
        raise HTTPException(504, str(e))

@router.post("/owners")
async def api_add_owners(body: GroupChange):
    await sharepoint.add_owners(body.groupId, body.user_upns)
    return {"addedOwners": body.user_upns}

@router.delete("/owners")
async def api_remove_owners(body: GroupChange):
    await sharepoint.remove_owners(body.groupId, body.user_upns)
    return {"removedOwners": body.user_upns}

@router.post("/members")
async def api_add_members(body: GroupChange):
    await sharepoint.add_members(body.groupId, body.user_upns)
    return {"addedMembers": body.user_upns}

@router.delete("/members")
async def api_remove_members(body: GroupChange):
    await sharepoint.remove_members(body.groupId, body.user_upns)
    return {"removedMembers": body.user_upns}
