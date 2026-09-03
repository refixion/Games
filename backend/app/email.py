import html
import httpx
from .config import settings

RESEND_API = 'https://api.resend.com/emails'


def build_secret_email(*, player_name: str, to_email: str, game: dict, role: dict) -> dict:
  greeting = f'Beste {player_name},'
  clues = role.get('clues', [])
  personal_info = role.get('personal_info', '')
  instructions = role.get('instructions', 'Houd deze informatie geheim tot het spel begint.')
  safe = lambda value: html.escape(str(value))
  clue_html = ''.join(f'<li>{safe(clue)}</li>' for clue in clues)
  text = f"{greeting}\n\nGame: {game['name']}\nRol: {role['name']}\n\n{role['description']}\n\nPersoonlijke informatie: {personal_info}\n\nClues:\n" + '\n'.join(f'- {clue}' for clue in clues) + f"\n\n{instructions}"
  html_body = f'''<html><body style="font-family:Arial,sans-serif;color:#17202a;background:#f5f2ea;padding:24px"><div style="max-width:640px;margin:auto;background:#fffdf8;border:1px solid #d7d0c2;padding:32px"><p style="color:#b45309;text-transform:uppercase;letter-spacing:.12em;font-size:12px">{safe(game['name'])}</p><h1>Jouw geheime rol</h1><p>{safe(greeting)}</p><h2>{safe(role['name'])}</h2><p>{safe(role['description'])}</p><p><strong>Persoonlijke informatie</strong><br>{safe(personal_info)}</p><p><strong>Clues</strong></p><ul>{clue_html}</ul><p>{safe(instructions)}</p></div></body></html>'''
  return {'to': to_email, 'subject': 'Jouw geheime rol — Secret Game', 'text': text, 'html': html_body}


async def send_secret_email(to_email: str, *, player_name: str, game: dict, role: dict):
    api_key = settings.resend_api_key
    if not api_key:
        raise RuntimeError('RESEND_API_KEY not configured')

    from_email = settings.resend_from_email or 'game@refixion.nl'
    payload = build_secret_email(player_name=player_name, to_email=to_email, game=game, role=role)
    payload['from'] = from_email
    payload['to'] = [to_email]
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    async with httpx.AsyncClient() as client:
        response = await client.post(RESEND_API, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()
        return response.json()
