import httpx
import os
from .config import settings

RESEND_API = 'https://api.resend.com/emails'

async def send_secret_email(to_email: str):
    api_key = settings.resend_api_key
    if not api_key:
        raise RuntimeError('RESEND_API_KEY not configured')
    payload = {
        "from": "no-reply@secretgame.example",
        "to": [to_email],
        "subject": "🤫 Jij bent gekozen",
        "text": "Je bent de geheime speler voor dit spel.\nHoud dit geheim tot het spel begint."
    }
    headers = { 'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json' }
    async with httpx.AsyncClient() as client:
        r = await client.post(RESEND_API, json=payload, headers=headers, timeout=10.0)
        r.raise_for_status()
        return r.json()
