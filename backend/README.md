Backend: FastAPI

Installatie:

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Start:

uvicorn main:app --reload --host 0.0.0.0 --port 8000

Configureer `DATABASE_URL`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL` en `ADMIN_PASSWORD` in je omgevingsvariabelen of `.env`. PostgreSQL-tabellen en gameconfiguraties worden automatisch aangemaakt tijdens FastAPI startup.
