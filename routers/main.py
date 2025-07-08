from fastapi import FastAPI
from routers import sites

app = FastAPI(title="AI Hub SharePoint API")
app.include_router(sites.router)

@app.get("/health")
async def health(): return {"status": "ok"}
