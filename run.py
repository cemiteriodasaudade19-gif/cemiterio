#!/usr/bin/env python3
"""
Iniciar o sistema:
    python run.py

Variáveis de ambiente opcionais:
    PORT=8000          porta (padrão: 8000)
    DB_PATH=data/cemiterio.db
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n🏛  Sistema Cemitério — http://localhost:{port}")
    print(f"    Login padrão: admin / admin123\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
