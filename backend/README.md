Backend: FastAPI

Installatie:

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Start:

uvicorn main:app --reload --host 0.0.0.0 --port 8000

Configureer DATABASE_URL en RESEND_API_KEY in je omgevingsvariabelen of .env

Maak de tabel aan met het SQL in app/models.py als eerste stap.
