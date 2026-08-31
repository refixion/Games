import httpx
from .config import settings

RESEND_API = 'https://api.resend.com/emails'


async def send_secret_email(to_email: str, *, player_name: str = '', role_name: str = 'Speler', game_name: str = 'Secret Game', secret_info: str = 'Houd deze informatie geheim tot het spel begint.'):
    api_key = settings.resend_api_key
    if not api_key:
        raise RuntimeError('RESEND_API_KEY not configured')

    from_email = settings.resend_from_email or 'game@refixion.nl'
    greeting = f"Beste {player_name}," if player_name else 'Beste speler,'
    html = f"""
    <html>
      <body style="margin:0;padding:0;background:#0b1020;font-family:Arial,sans-serif;color:#e5e7eb;">
        <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
          <div style="background:linear-gradient(135deg,#111827,#1f2937);border:1px solid rgba(148,163,184,0.25);border-radius:18px;padding:28px;">
            <p style="letter-spacing:0.12em;text-transform:uppercase;color:#a5b4fc;font-size:12px;margin:0 0 16px;">{game_name}</p>
            <h1 style="margin:0 0 16px;font-size:28px;color:#f8fafc;">Je geheime rol</h1>
            <p style="margin:0 0 18px;line-height:1.6;">{greeting}</p>
            <div style="background:#111827;border:1px solid rgba(148,163,184,0.2);border-radius:12px;padding:18px;margin:20px 0;">
              <p style="margin:0 0 8px;color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;">Rol</p>
              <p style="margin:0;font-size:24px;font-weight:700;color:#f8fafc;">{role_name}</p>
            </div>
            <p style="margin:0 0 18px;line-height:1.7;">{secret_info}</p>
            <p style="margin:0;color:#cbd5e1;">Houd deze informatie geheim en volg de aanwijzingen van het spel.</p>
          </div>
        </div>
      </body>
    </html>
    """

    payload = {
        'from': from_email,
        'to': [to_email],
        'subject': f'{game_name}: jouw geheime informatie',
        'text': f"{greeting}\n\nRol: {role_name}\n\n{secret_info}\n\nHoud deze informatie geheim.",
        'html': html,
    }
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    async with httpx.AsyncClient() as client:
        response = await client.post(RESEND_API, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()
        return response.json()
