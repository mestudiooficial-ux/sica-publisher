"""Atualiza o card azul de hoje na pagina Saude.Corpo (sem IA, sem gastar token).
Roda no GitHub Actions (.github/workflows/azul.yml) ou local: python azul_auto.py [--dry]"""
import os, sys, json, datetime, urllib.request, urllib.error

def load_env():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip().strip('"'))
load_env()
TOKEN = os.environ["NOTION_TOKEN"]
DB = "41a74be6e5ad8181b81cf39d6ce05add"      # Conteudo e Tarefas
FILA = "41a74be6e5ad81949043f47792d414d6"    # Fila de publicacao
HOME = "21b74be6e5ad805d98dfc9fcb3d91e29"    # pagina Saude.Corpo
H = {"Authorization": "Bearer " + TOKEN, "Notion-Version": "2022-06-28", "Content-Type": "application/json", "User-Agent": "curl/8.0"}
BRT = datetime.timezone(datetime.timedelta(hours=-3))
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

def api(m, path, body=None):
    r = urllib.request.Request("https://api.notion.com/v1/" + path, method=m, headers=H, data=None if body is None else json.dumps(body).encode())
    return json.load(urllib.request.urlopen(r, timeout=60))

def txt(p):
    t = p["type"]; v = p[t]
    if t in ("title", "rich_text"): return "".join(x["plain_text"] for x in v)
    if t in ("select", "status"): return v["name"] if v else ""
    if t == "date": return v["start"] if v else ""
    return ""

def query(db, flt):
    return api("POST", "databases/%s/query" % db, {"filter": flt, "page_size": 100})["results"]

now = datetime.datetime.now(BRT)
hoje = now.date().isoformat()
dia = lambda n: {"and": [{"property": n, "date": {"on_or_after": hoje}}, {"property": n, "date": {"on_or_before": hoje}}]}

fila = []
for p in query(FILA, {"and": [{"property": "Publicar em", "date": {"on_or_after": hoje + "T00:00:00-03:00"}},
                              {"property": "Publicar em", "date": {"on_or_before": hoje + "T23:59:59-03:00"}}]}):
    pr = p["properties"]
    d = txt(pr["Publicar em"])
    hh = datetime.datetime.fromisoformat(d).astimezone(BRT) if "T" in d else None
    fila.append((hh.strftime("%H:%M") if hh else "99:99", txt(pr["Peça"]), txt(pr["Conta"]), txt(pr["Status"])))
fila.sort()
nomes_fila = {f[1].strip().lower() for f in fila}

linhas = []
seen = set()
for p in query(DB, {"or": [dia("Prazo"), dia("Date")]}):
    pr = p["properties"]
    nome = txt(pr["Peça"]).strip()
    if nome.lower() in nomes_fila or nome in seen: continue
    seen.add(nome)
    etapa = txt(pr["Etapa"]).lower() if "Etapa" in pr else ""
    if txt(pr["Tipo"]) == "Publicação" and ("aprovado" in etapa or "postado" in etapa): continue  # ja aparece no calendario
    feito = txt(pr["Status"]) == "Feito"
    fmts = {x["name"] for x in pr["Formato"]["multi_select"]} if "Formato" in pr else set()
    tipo = txt(pr["Tipo"]) if "Tipo" in pr else ""
    if tipo == "Tarefa interna": ic = "📋"
    elif fmts & {"Reel", "TV"} or tipo.lower().startswith("vídeo"): ic = "🎥"
    elif fmts & {"Post", "Imagem", "Carrossel", "Story"}: ic = "🖼️"
    else: ic = "📋"
    linhas.append(("✅ Feito: " if feito else ic + " A fazer: ") + nome)
ordem = {"🎥": 0, "🖼️": 1, "📋": 2, "✅": 3}
linhas.sort(key=lambda s: (ordem.get(s.split(" ")[0], 9), s))
for hhmm, nome, conta, st in fila:
    if st != "Erro": continue  # postagens do dia ficam no calendario; so avisa erro
    h = hhmm.replace(":00", "h").replace(":", "h")
    if st in ("Publicado",): icone, pre = "✅", "Publicado %s: " % h
    elif st in ("Erro",): icone, pre = "⚠️", "Erro ao publicar %s: " % h
    else: icone, pre = "🕖", "Hoje %s: " % h
    linhas.append("%s %s%s (%s)" % (icone, pre, nome, conta))
if now.weekday() == 0:
    linhas.append(("✅" if now.hour >= 9 else "🕗") + " 08h35: pesquisa semanal de concorrentes")

titulo = "Hoje · %s %s (atualizado às %s)" % (DIAS[now.weekday()], now.strftime("%d/%m/%Y"), now.strftime("%Hh%M"))
corpo = [titulo] + (linhas or ["Nada marcado para hoje."])
print("\n".join(corpo))
if "--dry" in sys.argv: sys.exit(0)

alvo = None
for b in api("GET", "blocks/%s/children?page_size=20" % HOME)["results"]:
    if b["type"] == "callout" and b["callout"]["color"] == "blue_background":
        alvo = b; break
if not alvo: sys.exit("card azul nao encontrado")
rt = [{"type": "text", "text": {"content": corpo[0]}, "annotations": {"bold": True}}]
rt += [{"type": "text", "text": {"content": "\n" + l}} for l in corpo[1:]]
api("PATCH", "blocks/" + alvo["id"], {"callout": {"rich_text": rt}})
print("card azul atualizado")
