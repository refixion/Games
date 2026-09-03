Backend: FastAPI

Installatie:

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Start:

uvicorn main:app --reload --host 0.0.0.0 --port 8000

Configureer `DATABASE_URL`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `ADMIN_PASSWORD`, `AI_API_KEY`, `AI_BASE_URL` en `AI_MODEL` in je omgevingsvariabelen of `.env`. PostgreSQL-tabellen, gameconfiguraties en generatie-opslag worden automatisch aangemaakt tijdens FastAPI startup. Zonder `AI_API_KEY` blijft de API beschikbaar, maar testgeneratie en `Start spel` geven bewust een duidelijke configuratiefout.
