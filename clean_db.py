import sys
from sqlalchemy import create_engine, text
from datetime import datetime

url = 'postgresql://tenders:C-2022-000147@localhost:5432/marches_ai'
engine = create_engine(url)

try:
    with engine.begin() as conn:
        today = datetime.now().strftime('%Y-%m-%d')
        res = conn.execute(text(f"DELETE FROM opportunities WHERE deadline < '{today}'"))
        print(f"BING! {res.rowcount} offres perimees supprimees.")
except Exception as e:
    print("Error:", e)
