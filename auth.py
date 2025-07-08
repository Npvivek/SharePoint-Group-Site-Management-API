import msal, httpx, asyncio
from settings import settings

AUTHORITY = f"https://login.microsoftonline.com/{settings.tenant_id}"
SCOPE     = ["https://graph.microsoft.com/.default"]

def get_app_token() -> str:
    cca = msal.ConfidentialClientApplication(
        settings.client_id,
        authority=AUTHORITY,
        client_credential=settings.client_secret,
    )
    tok = cca.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in tok:
        raise RuntimeError(f"MSAL auth failed: {tok.get('error_description')}")
    return tok["access_token"]

async def resolve_user_id(upn: str, client: httpx.AsyncClient, headers: dict) -> str:
    r = await client.get(
        f"https://graph.microsoft.com/v1.0/users/{upn}?$select=id",
        headers=headers, timeout=10
    )
    r.raise_for_status()
    return r.json()["id"]
