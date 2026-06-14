import sqlite3
import os
from contextlib import contextmanager
from passlib.context import CryptContext

DB_PATH = os.environ.get("DB_PATH", "data/cemiterio.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    login       TEXT NOT NULL UNIQUE,
    senha_hash  TEXT NOT NULL,
    perfil      TEXT NOT NULL DEFAULT 'operador',  -- admin | operador | consulta
    ativo       INTEGER NOT NULL DEFAULT 1,
    criado_em   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS falecidos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    numctfal        INTEGER,
    nome            TEXT,
    nomepesq        TEXT,
    sexofale        TEXT,
    mae             TEXT,
    pai             TEXT,
    dtnasc          TEXT,
    dtfaleci        TEXT,
    idadanos        REAL,
    docobito        TEXT,
    outrasinf       TEXT,
    cancelado       INTEGER DEFAULT 0,
    motivcancel     TEXT,
    conferido       INTEGER DEFAULT 0,
    operador        TEXT,
    dtcadastro      TEXT,
    livronum        INTEGER,
    livropag        INTEGER,
    livroord        INTEGER,
    numprocano      TEXT,
    sep_data        TEXT,
    sep_tipojaz     TEXT,
    sep_quadra      TEXT,
    sep_bloclote    TEXT,
    sep_nicolgav    TEXT,
    sep_lacre       INTEGER,
    sep_dtprevexum  TEXT,
    exa_cemisn      TEXT,
    exa_datexu      TEXT,
    exa_datreinuma  TEXT,
    exa_tipojaz     TEXT,
    exa_quadra      TEXT,
    exa_bloclote    TEXT,
    exa_nicolgav    TEXT,
    exa_lacre       INTEGER,
    transjaz        INTEGER DEFAULT 0,
    reabertura      INTEGER DEFAULT 0,
    observgeral     TEXT,
    criado_por      INTEGER REFERENCES usuarios(id),
    criado_em       TEXT DEFAULT (datetime('now','localtime')),
    atualizado_por  INTEGER REFERENCES usuarios(id),
    atualizado_em   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS lotes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    quadra   TEXT NOT NULL,
    numero   INTEGER NOT NULL,
    letra    TEXT,
    tipo     TEXT,
    UNIQUE(quadra, numero, letra)
);

CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER REFERENCES usuarios(id),
    acao        TEXT NOT NULL,
    tabela      TEXT,
    registro_id INTEGER,
    detalhe     TEXT,
    criado_em   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_falecidos_nome     ON falecidos(nomepesq);
CREATE INDEX IF NOT EXISTS idx_falecidos_quadra   ON falecidos(sep_quadra);
CREATE INDEX IF NOT EXISTS idx_falecidos_dtfaleci ON falecidos(dtfaleci);
CREATE INDEX IF NOT EXISTS idx_falecidos_exu      ON falecidos(exa_datexu);
"""

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        # Admin padrão
        existing = conn.execute("SELECT id FROM usuarios WHERE login='admin'").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO usuarios (nome, login, senha_hash, perfil) VALUES (?,?,?,?)",
                ("Administrador", "admin", pwd_context.hash("admin123"), "admin")
            )
    print(f"[DB] Banco inicializado: {DB_PATH}")

def importar_xlsx(caminho: str, usuario_id: int):
    import pandas as pd
    df = pd.read_excel(caminho)
    df = df.fillna("")

    col_map = {
        "NUMCTFAL":"numctfal","NOME":"nome","NOMEPESQ":"nomepesq","SEXOFALE":"sexofale",
        "MAE":"mae","PAI":"pai","DTNASC":"dtnasc","DTFALECI":"dtfaleci","IDADANOS":"idadanos",
        "DOCOBITO":"docobito","OUTRASINF":"outrasinf","CANCELADO":"cancelado",
        "MOTIVCANCEL":"motivcancel","CONFERIDO":"conferido","OPERADOR":"operador",
        "DTCADASTRO":"dtcadastro","LIVRONUM":"livronum","LIVROPAG":"livropag",
        "LIVROORD":"livroord","NUMPROCANO":"numprocano","SEP_DATA":"sep_data",
        "SEP_TIPOJAZ":"sep_tipojaz","SEP_QUADRA":"sep_quadra","SEP_BLOCLOTE":"sep_bloclote",
        "SEP_NICOLGAV":"sep_nicolgav","SEP_LACRE":"sep_lacre","SEP_DTPREVEXUM":"sep_dtprevexum",
        "EXU_CEMISN":"exa_cemisn","EXU_DATEXU":"exa_datexu","EXU_DATREINUMA":"exa_datreinuma",
        "EXU_TIPOJAZ":"exa_tipojaz","EXU_QUADRA":"exa_quadra","EXU_BLOCLOTE":"exa_bloclote",
        "EXU_NICOLGAV":"exa_nicolgav","EXU_LACRE":"exa_lacre",
        "TRANSJAZANTEXUM":"transjaz","REABERTURA":"reabertura","OBSERVGERAL":"observgeral",
    }
    df = df.rename(columns=col_map)
    db_cols = [c for c in col_map.values() if c in df.columns]

    with db() as conn:
        conn.execute("DELETE FROM falecidos")
        rows = []
        for _, row in df.iterrows():
            vals = {c: (str(row[c]) if row[c] != "" else None) for c in db_cols}
            vals["criado_por"] = usuario_id
            rows.append(vals)
        if rows:
            keys = list(rows[0].keys())
            placeholders = ",".join("?" * len(keys))
            cols_str = ",".join(keys)
            conn.executemany(
                f"INSERT INTO falecidos ({cols_str}) VALUES ({placeholders})",
                [list(r.values()) for r in rows]
            )
    return len(rows)
