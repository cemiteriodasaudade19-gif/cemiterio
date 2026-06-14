# 🏛 Sistema Cemitério — Railway Deploy

## Deploy no Railway (grátis)

### Passo 1 — GitHub
1. Acesse **github.com** e crie uma conta gratuita (se não tiver)
2. Clique em **"New repository"** → nome: `cemiterio` → **Create repository**
3. Clique em **"uploading an existing file"**
4. Arraste TODOS os arquivos desta pasta (exceto a pasta `data/`) → **Commit changes**

### Passo 2 — Railway
1. Acesse **railway.app** → **"Login with GitHub"**
2. Clique em **"New Project"** → **"Deploy from GitHub repo"**
3. Selecione o repositório `cemiterio`
4. Railway detecta automaticamente e faz o deploy
5. Vá em **Settings → Networking → Generate Domain** para ter o link público

### Passo 3 — Primeiro acesso
- Acesse o link gerado pelo Railway
- Login: **admin** / Senha: **admin123**
- ⚠️ **Troque a senha imediatamente** (Admin → Editar usuário)
- Vá em **Admin → Importar** e suba o `FALECIDOS_CONSOLIDADO.xlsx`

## Perfis de acesso
| Perfil | Ver | Editar | Excluir | Admin |
|--------|-----|--------|---------|-------|
| Admin | ✅ | ✅ | ✅ | ✅ |
| Operador | ✅ | ✅ | ❌ | ❌ |
| Consulta | ✅ | ❌ | ❌ | ❌ |

## Rodar localmente (teste)
```bash
pip install -r requirements.txt
python run.py
# Acesse: http://localhost:8000
```

## Backup do banco
O banco fica em `data/cemiterio.db`. No Railway, use o botão **"Admin → Salvar base Excel"** periodicamente para ter um backup dos dados.

## Migrar para PostgreSQL (futuro)
Instale `psycopg2-binary` e substitua a conexão SQLite em `app/database.py` pela URL do PostgreSQL fornecida pelo Railway.
