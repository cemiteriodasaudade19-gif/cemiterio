import os, math, shutil
from fastapi import FastAPI, Depends, HTTPException, Form, UploadFile, File, Request, Response, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional

from app.database import db, init_db, importar_xlsx
from app.auth import (
    authenticate_user, create_token, get_current_user,
    require_admin, require_operador, hash_password
)

app = FastAPI(title="Sistema Cemitério", docs_url=None, redoc_url=None)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.on_event("startup")
def startup():
    init_db()

# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login")
def login(response: Response, login: str = Form(...), senha: str = Form(...)):
    user = authenticate_user(login, senha)
    if not user:
        raise HTTPException(status_code=401, detail="Login ou senha incorretos")
    token = create_token({"sub": user["id"], "perfil": user["perfil"]})
    resp = JSONResponse({"ok": True, "perfil": user["perfil"], "nome": user["nome"]})
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=28800)
    with db() as conn:
        conn.execute("INSERT INTO auditoria (usuario_id,acao,detalhe) VALUES (?,?,?)",
                     (user["id"], "login", f"Login de {user['login']}"))
    return resp

@app.post("/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("access_token")
    return resp

@app.get("/app", response_class=HTMLResponse)
def main_app(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("app.html", {"request": request, "user": user})

@app.get("/api/me")
def me(user=Depends(get_current_user)):
    return {"id": user["id"], "nome": user["nome"], "perfil": user["perfil"], "login": user["login"]}

# ── FALECIDOS ─────────────────────────────────────────────────────────────────
@app.get("/api/falecidos")
def listar(
    q: str = Query(""), sexo: str = Query(""), quadra: str = Query(""),
    jazigo: str = Query(""), exumado: str = Query(""), destino: str = Query(""),
    historico: str = Query(""), vencidos: str = Query(""),
    page: int = Query(1), per_page: int = Query(50),
    sort: str = Query("nome"), dir: str = Query("asc"),
    user=Depends(get_current_user)
):
    allowed = {"nome","dtfaleci","sep_quadra","sep_bloclote","exa_datexu","numctfal","sep_dtprevexum"}
    sort = sort if sort in allowed else "nome"
    direction = "ASC" if dir == "asc" else "DESC"
    where, params = ["1=1"], []
    if q:
        where.append("(nome LIKE ? OR mae LIKE ? OR pai LIKE ? OR CAST(numctfal AS TEXT) LIKE ? OR exa_nicolgav LIKE ? OR CAST(exa_lacre AS TEXT) LIKE ? OR historico LIKE ?)")
        like = f"%{q}%"; params += [like]*7
    if sexo: where.append("sexofale=?"); params.append(sexo)
    if quadra: where.append("sep_quadra=?"); params.append(quadra)
    if jazigo: where.append("sep_tipojaz=?"); params.append(jazigo)
    if destino: where.append("exa_tipojaz=?"); params.append(destino)
    if historico: where.append("historico=?"); params.append(historico)
    if exumado == "sim": where.append("exa_datexu IS NOT NULL AND exa_datexu != ''")
    elif exumado == "nao": where.append("(exa_datexu IS NULL OR exa_datexu = '')")
    if vencidos == "1":
        where.append("(exa_datexu IS NULL OR exa_datexu = '') AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum != ''")
    clause = " AND ".join(where)
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM falecidos WHERE {clause}", params).fetchone()[0]
        offset = (page-1)*per_page
        rows = conn.execute(
            f"SELECT * FROM falecidos WHERE {clause} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()
    return {"total": total, "pages": math.ceil(total/per_page), "page": page, "data": [dict(r) for r in rows]}

@app.get("/api/falecidos/{fid}")
def get_um(fid: int, user=Depends(get_current_user)):
    with db() as conn:
        row = conn.execute("SELECT * FROM falecidos WHERE id=?", (fid,)).fetchone()
    if not row: raise HTTPException(404, "Não encontrado")
    return dict(row)

CAMPOS = [
    "numctfal","nome","nomepesq","sexofale","mae","pai","dtnasc","dtfaleci","idadanos",
    "docobito","outrasinf","cancelado","motivcancel","conferido","operador","dtcadastro",
    "livronum","livropag","livroord","numprocano","sep_data","sep_tipojaz","sep_quadra",
    "sep_bloclote","sep_nicolgav","sep_lacre","sep_dtprevexum","exa_cemisn","exa_datexu",
    "exa_datreinuma","exa_tipojaz","exa_quadra","exa_bloclote","exa_nicolgav","exa_lacre",
    "transjaz","reabertura","observgeral","historico",
    "dec_nome","dec_parentes","dec_rg","dec_cpf","dec_ender","dec_endernum",
    "dec_bairro","dec_munic","dec_uf","dec_fones"
]

@app.post("/api/falecidos")
def criar(data: dict, user=Depends(require_operador)):
    vals = {c: data.get(c) for c in CAMPOS if data.get(c) is not None}
    vals["criado_por"] = user["id"]
    if "nome" in vals: vals["nomepesq"] = vals["nome"].upper()
    keys = list(vals.keys())
    with db() as conn:
        cur = conn.execute(f"INSERT INTO falecidos ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})", list(vals.values()))
        fid = cur.lastrowid
        conn.execute("INSERT INTO auditoria (usuario_id,acao,tabela,registro_id,detalhe) VALUES (?,?,?,?,?)",
                     (user["id"],"criar","falecidos",fid,vals.get("nome","")))
    return {"id": fid}

@app.put("/api/falecidos/{fid}")
def editar(fid: int, data: dict, user=Depends(require_operador)):
    vals = {c: data.get(c) for c in CAMPOS if c in data}
    if "nome" in vals: vals["nomepesq"] = vals["nome"].upper()
    vals["atualizado_por"] = user["id"]
    sets = ", ".join(f"{k}=?" for k in vals) + ", atualizado_em=datetime('now','localtime')"
    with db() as conn:
        conn.execute(f"UPDATE falecidos SET {sets} WHERE id=?", list(vals.values()) + [fid])
        conn.execute("INSERT INTO auditoria (usuario_id,acao,tabela,registro_id,detalhe) VALUES (?,?,?,?,?)",
                     (user["id"],"editar","falecidos",fid,vals.get("nome","")))
    return {"ok": True}

@app.delete("/api/falecidos/{fid}")
def deletar(fid: int, user=Depends(require_admin)):
    with db() as conn:
        row = conn.execute("SELECT nome FROM falecidos WHERE id=?", (fid,)).fetchone()
        if not row: raise HTTPException(404)
        conn.execute("DELETE FROM falecidos WHERE id=?", (fid,))
        conn.execute("INSERT INTO auditoria (usuario_id,acao,tabela,registro_id,detalhe) VALUES (?,?,?,?,?)",
                     (user["id"],"deletar","falecidos",fid,row["nome"]))
    return {"ok": True}

# ── DASHBOARD / MAPA ──────────────────────────────────────────────────────────
@app.get("/api/dashboard")
def dashboard(user=Depends(get_current_user)):
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM falecidos").fetchone()[0]
        masc  = conn.execute("SELECT COUNT(*) FROM falecidos WHERE sexofale='M'").fetchone()[0]
        fem   = conn.execute("SELECT COUNT(*) FROM falecidos WHERE sexofale='F'").fetchone()[0]
        exum  = conn.execute("SELECT COUNT(*) FROM falecidos WHERE exa_datexu IS NOT NULL AND exa_datexu!=''").fetchone()[0]
        venc  = conn.execute("""SELECT COUNT(*) FROM falecidos
            WHERE (exa_datexu IS NULL OR exa_datexu='')
            AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
            AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2)) < date('now')
        """).fetchone()[0]
        by_year = conn.execute("""
            SELECT SUBSTR(dtfaleci,7,4) ano, COUNT(*) total FROM falecidos
            WHERE dtfaleci IS NOT NULL AND dtfaleci!=''
            AND CAST(SUBSTR(dtfaleci,7,4) AS INTEGER) BETWEEN 1999 AND 2024
            GROUP BY ano ORDER BY ano""").fetchall()
        by_exu = conn.execute("""
            SELECT SUBSTR(exa_datexu,7,4) ano, COUNT(*) total FROM falecidos
            WHERE exa_datexu IS NOT NULL AND exa_datexu!=''
            AND CAST(SUBSTR(exa_datexu,7,4) AS INTEGER) BETWEEN 2000 AND 2024
            GROUP BY ano ORDER BY ano""").fetchall()
        by_jaz = conn.execute("""
            SELECT sep_tipojaz, COUNT(*) total FROM falecidos
            WHERE sep_tipojaz IS NOT NULL AND sep_tipojaz!=''
            GROUP BY sep_tipojaz ORDER BY total DESC""").fetchall()
        by_quad = conn.execute("""
            SELECT sep_quadra, COUNT(*) total,
                   SUM(CASE WHEN exa_datexu IS NOT NULL AND exa_datexu!='' THEN 1 ELSE 0 END) exumados
            FROM falecidos WHERE sep_quadra IS NOT NULL AND sep_quadra!=''
            GROUP BY sep_quadra ORDER BY total DESC LIMIT 15""").fetchall()
        by_month = conn.execute("""
            SELECT SUBSTR(dtfaleci,1,2) mes, COUNT(*) total FROM falecidos
            WHERE dtfaleci IS NOT NULL AND dtfaleci!=''
            GROUP BY mes ORDER BY mes""").fetchall()
        alertas_30 = conn.execute("""SELECT COUNT(*) FROM falecidos
            WHERE (exa_datexu IS NULL OR exa_datexu='')
            AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
            AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2))
                BETWEEN date('now') AND date('now','+30 days')""").fetchone()[0]
    return {
        "totais": {"total":total,"masc":masc,"fem":fem,"exum":exum,"venc":venc,"prox30":alertas_30},
        "byYear": [dict(r) for r in by_year],
        "byExuYear": [dict(r) for r in by_exu],
        "byJazigo": [dict(r) for r in by_jaz],
        "byQuadra": [dict(r) for r in by_quad],
        "byMonth": [dict(r) for r in by_month],
    }

@app.get("/api/mapa")
def mapa(user=Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute("""
            SELECT sep_quadra, sep_bloclote,
                   COUNT(*) total,
                   SUM(CASE WHEN exa_datexu IS NOT NULL AND exa_datexu!='' THEN 1 ELSE 0 END) exumados,
                   SUM(CASE WHEN (exa_datexu IS NULL OR exa_datexu='')
                       AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
                       AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2)) < date('now')
                       THEN 1 ELSE 0 END) vencidos,
                   MAX(sep_tipojaz) tipo
            FROM falecidos
            WHERE sep_quadra IS NOT NULL AND sep_quadra!=''
              AND sep_bloclote IS NOT NULL AND sep_bloclote!=''
              AND CAST(sep_bloclote AS INTEGER) BETWEEN 1 AND 250
            GROUP BY sep_quadra, sep_bloclote""").fetchall()
    return [dict(r) for r in rows]

@app.get("/api/alertas")
def alertas(dias: int = Query(0), user=Depends(get_current_user)):
    if dias == 0:
        cond = "AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2)) < date('now')"
    else:
        cond = f"AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2)) BETWEEN date('now') AND date('now','+{dias} days')"
    with db() as conn:
        rows = conn.execute(f"""
            SELECT * FROM falecidos
            WHERE (exa_datexu IS NULL OR exa_datexu='')
            AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
            {cond}
            ORDER BY sep_dtprevexum ASC
            LIMIT 2000""").fetchall()
    return [dict(r) for r in rows]

@app.get("/api/relatorio/{tipo}")
def relatorio(tipo: str, user=Depends(get_current_user)):
    with db() as conn:
        if tipo == "vencidos":
            rows = conn.execute("""SELECT numctfal,nome,sep_quadra,sep_bloclote,sep_tipojaz,sep_dtprevexum
                FROM falecidos WHERE (exa_datexu IS NULL OR exa_datexu='')
                AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
                AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2)) < date('now')
                ORDER BY sep_dtprevexum ASC""").fetchall()
        elif tipo == "proximos30":
            rows = conn.execute("""SELECT numctfal,nome,sep_quadra,sep_bloclote,sep_tipojaz,sep_dtprevexum
                FROM falecidos WHERE (exa_datexu IS NULL OR exa_datexu='')
                AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
                AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2))
                    BETWEEN date('now') AND date('now','+30 days')
                ORDER BY sep_dtprevexum ASC""").fetchall()
        elif tipo == "proximos90":
            rows = conn.execute("""SELECT numctfal,nome,sep_quadra,sep_bloclote,sep_tipojaz,sep_dtprevexum
                FROM falecidos WHERE (exa_datexu IS NULL OR exa_datexu='')
                AND sep_dtprevexum IS NOT NULL AND sep_dtprevexum!=''
                AND date(substr(sep_dtprevexum,7,4)||'-'||substr(sep_dtprevexum,1,2)||'-'||substr(sep_dtprevexum,4,2))
                    BETWEEN date('now') AND date('now','+90 days')
                ORDER BY sep_dtprevexum ASC""").fetchall()
        elif tipo == "exumados":
            rows = conn.execute("""SELECT numctfal,nome,sep_quadra,sep_bloclote,exa_datexu,exa_tipojaz,exa_nicolgav,exa_lacre,historico
                FROM falecidos WHERE exa_datexu IS NOT NULL AND exa_datexu!=''
                ORDER BY exa_datexu DESC""").fetchall()
        elif tipo == "anual":
            rows = conn.execute("""
                SELECT SUBSTR(dtfaleci,7,4) ano,
                       COUNT(*) obitos,
                       SUM(CASE WHEN exa_datexu IS NOT NULL AND exa_datexu!='' THEN 1 ELSE 0 END) exumacoes
                FROM falecidos WHERE dtfaleci IS NOT NULL AND dtfaleci!=''
                GROUP BY ano ORDER BY ano DESC""").fetchall()
        elif tipo == "lotesVagos":
            rows = conn.execute("""
                SELECT sep_quadra quadra, COUNT(*) total,
                       SUM(CASE WHEN exa_datexu IS NOT NULL AND exa_datexu!='' THEN 1 ELSE 0 END) exumados,
                       COUNT(*) - SUM(CASE WHEN exa_datexu IS NOT NULL AND exa_datexu!='' THEN 1 ELSE 0 END) sem_exumacao
                FROM falecidos WHERE sep_quadra IS NOT NULL AND sep_quadra!=''
                GROUP BY sep_quadra ORDER BY sep_quadra""").fetchall()
        else:
            raise HTTPException(400, "Relatório inválido")
    return [dict(r) for r in rows]

# ── OPÇÕES ────────────────────────────────────────────────────────────────────
@app.get("/api/opcoes")
def opcoes(user=Depends(get_current_user)):
    with db() as conn:
        quadras = [r[0] for r in conn.execute("SELECT DISTINCT sep_quadra FROM falecidos WHERE sep_quadra IS NOT NULL AND sep_quadra!='' ORDER BY sep_quadra").fetchall()]
        jazigos = [r[0] for r in conn.execute("SELECT DISTINCT sep_tipojaz FROM falecidos WHERE sep_tipojaz IS NOT NULL AND sep_tipojaz!='' ORDER BY sep_tipojaz").fetchall()]
        destinos = [r[0] for r in conn.execute("SELECT DISTINCT exa_tipojaz FROM falecidos WHERE exa_tipojaz IS NOT NULL AND exa_tipojaz!='' ORDER BY exa_tipojaz").fetchall()]
        historicos = [r[0] for r in conn.execute("SELECT DISTINCT historico FROM falecidos WHERE historico IS NOT NULL AND historico!='' ORDER BY historico").fetchall()]
    return {"quadras": quadras, "jazigos": jazigos, "destinos": destinos, "historicos": historicos}

# ── USUÁRIOS ──────────────────────────────────────────────────────────────────
@app.get("/api/usuarios")
def listar_usuarios(user=Depends(require_admin)):
    with db() as conn:
        rows = conn.execute("SELECT id,nome,login,perfil,ativo,criado_em FROM usuarios ORDER BY nome").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/usuarios")
def criar_usuario(data: dict, user=Depends(require_admin)):
    if not {"nome","login","senha","perfil"}.issubset(data.keys()):
        raise HTTPException(400, "Campos obrigatórios: nome, login, senha, perfil")
    if data["perfil"] not in ("admin","operador","consulta"):
        raise HTTPException(400, "Perfil inválido")
    with db() as conn:
        try:
            conn.execute("INSERT INTO usuarios (nome,login,senha_hash,perfil) VALUES (?,?,?,?)",
                         (data["nome"], data["login"], hash_password(data["senha"]), data["perfil"]))
        except Exception:
            raise HTTPException(400, "Login já existe")
    return {"ok": True}

@app.put("/api/usuarios/{uid}")
def editar_usuario(uid: int, data: dict, user=Depends(require_admin)):
    sets, params = [], []
    for f in ("nome","login","perfil","ativo"):
        if f in data: sets.append(f"{f}=?"); params.append(data[f])
    if "senha" in data and data["senha"]:
        sets.append("senha_hash=?"); params.append(hash_password(data["senha"]))
    if not sets: raise HTTPException(400, "Nada para atualizar")
    params.append(uid)
    with db() as conn:
        conn.execute(f"UPDATE usuarios SET {', '.join(sets)} WHERE id=?", params)
    return {"ok": True}

# ── IMPORTAÇÃO ────────────────────────────────────────────────────────────────
@app.post("/api/importar")
async def importar(file: UploadFile = File(...), user=Depends(require_admin)):
    if not file.filename.endswith((".xlsx",".xls")):
        raise HTTPException(400, "Apenas .xlsx ou .xls")
    tmp = f"/tmp/import_{user['id']}.xlsx"
    with open(tmp, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        total = importar_xlsx(tmp, user["id"])
        with db() as conn:
            conn.execute("INSERT INTO auditoria (usuario_id,acao,detalhe) VALUES (?,?,?)",
                         (user["id"],"importar",f"Importados {total} registros"))
        return {"ok": True, "importados": total}
    finally:
        if os.path.exists(tmp): os.remove(tmp)

# ── AUDITORIA ─────────────────────────────────────────────────────────────────
@app.get("/api/auditoria")
def auditoria(page: int = 1, user=Depends(require_admin)):
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]
        rows = conn.execute("""SELECT a.*, u.nome usuario_nome FROM auditoria a
            LEFT JOIN usuarios u ON a.usuario_id=u.id
            ORDER BY a.id DESC LIMIT 50 OFFSET ?""", ((page-1)*50,)).fetchall()
    return {"total": total, "data": [dict(r) for r in rows]}
