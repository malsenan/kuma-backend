from fastapi import FastAPI

from whatsapp.webhook import router as whatsapp_router

API_VERSION = "0.2.0"

app = FastAPI(
    title="Lumora API",
    description="WhatsApp intake webhook for informal-entrepreneur credit onboarding.",
    version=API_VERSION,
)

# WhatsApp Cloud API webhook: GET/POST /webhook
app.include_router(whatsapp_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": API_VERSION}
