from pydantic import BaseModel
from typing import List, Optional

class SiteCreate(BaseModel):
    name: str
    ownerEmail: str                   # NOW REQUIRED
    privacy: str = "Private"
    description: Optional[str] = None
    memberEmails: Optional[List[str]] = None
    visitorEmails: Optional[List[str]] = None

class GroupChange(BaseModel):        # used by new owner/member routes
    groupId: str
    user_upns: List[str]
