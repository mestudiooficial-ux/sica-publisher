"""Tarefas semanais da SiCa que rodam no GitHub (sem IA, somente leitura na Meta).

python semanal.py relatorio   numeros da semana em .docx pelo WhatsApp (copia dos numeros no Notion)
python semanal.py coletar     coleta publica dos concorrentes e grava no Notion para a analise
python semanal.py avisar      manda pelo WhatsApp os links da pesquisa e do Radar de Trends
Com --dry nada e gravado nem enviado.
ATENCAO: o repositorio e publico, entao nada de dados, ids ou tokens nos prints.
"""
import contextlib, datetime as dt, io, json, os, sys, tempfile, urllib.error, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv
BRT = dt.timezone(dt.timedelta(hours=-3))
HOJE = dt.datetime.now(BRT).date()
DB_PESQUISA = "41e74be6e5ad81588070c010227016c6"
DB_RADAR = "42374be6e5ad81ac9193dd243ba51f13"
PAGINA_SICA = "41874be6e5ad801d94b3da760f7c1309"
TITULO_NUMEROS = "Números semanais · SiCa"
CONCORRENTES = {"panobiancoacademia": "Panobianco", "smartfit": "Smart Fit", "bluefitacademia": "Bluefit"}


def carregar_env():
    """No GitHub tudo vem dos Secrets; no PC, completa com os .env locais."""
    def ler(*p):
        arq = os.path.join(AQUI, *p)
        if not os.path.exists(arq):
            return {}
        return {k.strip(): v.strip().strip('"') for k, v in
                (l.split("=", 1) for l in open(arq, encoding="utf-8-sig") if "=" in l and not l.startswith("#"))}
    raiz, wa, pub = ler("..", ".env"), ler("..", "sica-whatsapp", ".env"), ler(".env")
    for destino, valor in (("META_READ_TOKEN", raiz.get("META_ACCESS_TOKEN")),
                           ("IG_READ_ID", raiz.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")),
                           ("NOTION_TOKEN", pub.get("NOTION_TOKEN")),
                           ("WHATSAPP_TOKEN", wa.get("WHATSAPP_TOKEN")),
                           ("WHATSAPP_PHONE_NUMBER_ID_TESTE", wa.get("WHATSAPP_PHONE_NUMBER_ID_TESTE")),
                           ("WHATSAPP_ALLOWED_NUMBER", wa.get("WHATSAPP_ALLOWED_NUMBER"))):
        if valor and not os.environ.get(destino):
            os.environ[destino] = valor


def env(nome):
    v = os.environ.get(nome)
    if not v:
        sys.exit("falta o segredo " + nome)
    return v


def http(url, corpo=None, metodo=None, cab=None):
    h = {"User-Agent": "curl/8.0", **(cab or {})}
    data = None
    if corpo is not None:
        data = json.dumps(corpo).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=metodo)
    return json.load(urllib.request.urlopen(req, timeout=60))


def notion(metodo, caminho, corpo=None):
    return http("https://api.notion.com/v1/" + caminho, corpo, metodo,
                {"Authorization": "Bearer " + env("NOTION_TOKEN"), "Notion-Version": "2022-06-28"})


def rt(texto):
    return [{"type": "text", "text": {"content": texto[i:i + 1900]}} for i in range(0, len(texto), 1900)]


def bloco(texto, tipo="paragraph"):
    return {"object": "block", "type": tipo, tipo: {"rich_text": rt(texto)}}


def filhos(pid):
    saida, cursor = [], None
    while True:
        caminho = "blocks/%s/children?page_size=100" % pid
        if cursor:
            caminho += "&start_cursor=" + cursor
        r = notion("GET", caminho)
        saida += r["results"]
        if not r.get("has_more"):
            return saida
        cursor = r["next_cursor"]


def whatsapp(texto):
    try:
        http("https://graph.facebook.com/v21.0/%s/messages" % env("WHATSAPP_PHONE_NUMBER_ID_TESTE"),
             {"messaging_product": "whatsapp", "to": env("WHATSAPP_ALLOWED_NUMBER"), "type": "text",
              "text": {"body": texto}}, "POST", {"Authorization": "Bearer " + env("WHATSAPP_TOKEN")})
        print("WhatsApp: aceito pela Meta")
    except urllib.error.HTTPError as e:
        print("WhatsApp: nao enviado, codigo", json.loads(e.read())["error"].get("code"))


# ---------- relatorio de sabado ----------
def pagina_numeros():
    for b in filhos(PAGINA_SICA):
        if b["type"] == "child_page" and b["child_page"]["title"] == TITULO_NUMEROS:
            return b["id"]
    if DRY:
        return None
    return notion("POST", "pages", {"parent": {"page_id": PAGINA_SICA},
                                    "properties": {"title": {"title": rt(TITULO_NUMEROS)}}})["id"]


def relatorio():
    import relatorio_semanal as r
    leitura = {"META_ACCESS_TOKEN": env("META_READ_TOKEN"), "INSTAGRAM_BUSINESS_ACCOUNT_ID": env("IG_READ_ID")}
    r.env_de = lambda *p: leitura if p == (".env",) else os.environ
    r.SAIDA = tempfile.mkdtemp()

    pid = pagina_numeros()
    anteriores = []
    for b in (filhos(pid) if pid else []):
        if b["type"] == "code":
            d = json.loads("".join(x["plain_text"] for x in b["code"]["rich_text"]))
            if d["data"] < HOJE.isoformat():
                anteriores.append(d)
    if anteriores:
        ant = max(anteriores, key=lambda d: d["data"])
        with open(os.path.join(r.SAIDA, ant["data"] + "_dados.json"), "w", encoding="utf-8") as f:
            json.dump(ant, f)

    with contextlib.redirect_stdout(io.StringIO()):
        r.coletar()
    with open(os.path.join(r.SAIDA, HOJE.isoformat() + "_dados.json"), encoding="utf-8") as f:
        d = json.load(f)
    validas = [c for c in d["contas"] if "erro" not in c]
    if not validas:
        if not DRY:
            whatsapp("SiCa: o relatório semanal não saiu porque a Meta não liberou a leitura das contas.")
        sys.exit("nenhuma conta com acesso")

    destaques = ["# O que chamou atenção"]
    for c in validas:
        var = ", %+d na semana" % c["variacao"] if "variacao" in c else ""
        linha = "- %s: %s seguidores%s, %d posts" % (c["nome"], c["seguidores"], var, len(c["posts"]))
        if c["posts"]:
            m = c["posts"][0]
            alc = m["alcance"] if m["alcance"] is not None else "indisponível"
            linha += ". Maior alcance: %s de %s (%s)" % (m["tipo"], m["quando"], alc)
        destaques.append(linha)
    sem = [c["nome"] for c in d["contas"] if "erro" in c]
    if sem:
        destaques += ["# Atenção", "- Sem acesso pela API: " + ", ".join(sem)]
    arq = os.path.join(r.SAIDA, "destaques.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("\n".join(destaques))

    print("contas lidas: %d de %d" % (len(validas), len(d["contas"])))
    if DRY:
        with contextlib.redirect_stdout(io.StringIO()):
            r.gerar(arq, False)
        print("teste: documento gerado, nada gravado nem enviado")
        return
    guardar = {"data": d["data"], "contas": [{"nome": c["nome"], "seguidores": c.get("seguidores")} for c in d["contas"]]}
    codigo = bloco(json.dumps(guardar, ensure_ascii=False), "code")
    codigo["code"]["language"] = "json"
    notion("PATCH", "blocks/%s/children" % pid, {"children":
           [bloco("Semana até " + HOJE.strftime("%d/%m/%Y"), "heading_3")]
           + [bloco(l.lstrip("# -")) for l in destaques] + [codigo]})
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r.gerar(arq, True)
        print("documento enviado pelo WhatsApp")
    except SystemExit:
        print("documento nao enviado (janela de 24h?); numeros salvos no Notion")


# ---------- concorrentes ----------
def posts_de(usuario, limite):
    posts, cursor, seguidores = [], "", None
    for _ in range(12):
        depois = ".after(%s)" % cursor if cursor else ""
        campos = ("business_discovery.username(%s){followers_count,media.limit(50)%s{media_type,media_product_type,"
                  "timestamp,like_count,comments_count,permalink,caption}}") % (usuario, depois)
        url = "https://graph.facebook.com/v21.0/%s?%s" % (env("IG_READ_ID"), urllib.parse.urlencode(
            {"fields": campos, "access_token": env("META_READ_TOKEN")}))
        bd = http(url)["business_discovery"]
        seguidores = bd["followers_count"]
        lote = bd.get("media", {}).get("data", [])
        for x in lote:
            x["quando"] = dt.datetime.strptime(x["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(BRT)
        posts += lote
        cursor = bd.get("media", {}).get("paging", {}).get("cursors", {}).get("after", "")
        # posts fixados podem ser antigos: para so quando o lote inteiro ja passou do limite
        if not lote or not cursor or max(x["quando"] for x in lote).date() < limite:
            break
    return seguidores, posts


def posicao(valor, base):
    return 100.0 * sum(1 for b in base if b <= valor) / len(base)


def interacao(p, seg):
    if p.get("like_count") is None or p.get("comments_count") is None:
        return None
    return (p["like_count"] + p["comments_count"]) / seg


def comentarios(p, seg):
    return None if p.get("comments_count") is None else p["comments_count"] / seg


def avaliar(post, base, seg):
    """Score por percentil (pesos da skill, so com o que a API entrega)."""
    metricas = [(w, f) for w, f in ((0.5, interacao), (0.2, comentarios)) if f(post, seg) is not None]

    def score(p):
        soma = peso = 0.0
        for w, f in metricas:
            v = f(p, seg)
            amostra = [f(b, seg) for b in base if f(b, seg) is not None]
            if v is not None and amostra:
                soma += w * posicao(v, amostra)
                peso += w
        return soma / peso if peso else None

    s = score(post)
    if s is None or len(metricas) < 2 or len(base) < 10:
        return s, "INCONCLUSIVO"
    notas = sorted(x for x in (score(b) for b in base) if x is not None)
    return s, "OUTLIER" if s >= notas[int(0.9 * (len(notas) - 1))] else "NÃO OUTLIER"


def formato(p):
    if p.get("media_product_type") == "REELS":
        return "Reel"
    return "Carrossel" if p.get("media_type") == "CAROUSEL_ALBUM" else None


def coletar():
    fim = HOJE - dt.timedelta(days=HOJE.weekday() + 1)   # ultimo domingo
    ini = fim - dt.timedelta(days=6)
    base_ini = ini - dt.timedelta(days=60)
    if not DRY and notion("POST", "databases/%s/query" % DB_PESQUISA,
                          {"filter": {"property": "Data da pesquisa", "date": {"equals": HOJE.isoformat()}}})["results"]:
        print("ja existe pesquisa de hoje; nada a fazer")
        return
    corpo, avaliadas, outliers, ok, falhas = [], 0, 0, [], []
    for usuario, marca in CONCORRENTES.items():
        try:
            seg, posts = posts_de(usuario, base_ini)
        except Exception as e:
            falhas.append(marca)
            print("falha na coleta de um perfil:", type(e).__name__)
            continue
        ok.append(marca)
        sel = []
        for p in posts:
            f = formato(p)
            if not f or not (ini <= p["quando"].date() <= fim):
                continue
            base = [b for b in posts if formato(b) == f and base_ini <= b["quando"].date() < ini]
            s, classe = avaliar(p, base, seg)
            sel.append((s if s is not None else -1, p, f, classe, len(base)))
        sel.sort(key=lambda x: -x[0])
        avaliadas += len(sel)
        outliers += sum(1 for x in sel if x[3] == "OUTLIER")
        corpo.append(bloco("%s (@%s) · %s seguidores · %d publicações na semana" % (marca, usuario, seg, len(sel)), "heading_2"))
        for s, p, f, classe, n in sel[:5]:
            curt, com = (p.get(k) if p.get(k) is not None else "indisponível" for k in ("like_count", "comments_count"))
            corpo.append(bloco(
                "%s · %s · %s · score %s · curtidas %s · comentários %s · base de 60 dias: %d\n%s\n"
                "Legenda (trecho de terceiro, só para análise): %s" % (
                    p["quando"].strftime("%d/%m %Hh%M"), f, classe, "-" if s < 0 else round(s), curt, com, n,
                    p.get("permalink", ""), (p.get("caption") or "")[:600])))
    periodo = "%s a %s (base: 60 dias anteriores)" % (ini.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y"))
    print("perfis coletados: %d de %d | publicacoes: %d | outliers: %d" % (len(ok), len(CONCORRENTES), avaliadas, outliers))
    if not ok:
        if not DRY:
            whatsapp("SiCa: a coleta dos concorrentes falhou. A Meta não liberou a leitura.")
        sys.exit("nenhum perfil coletado")
    if DRY:
        print("teste: nada gravado")
        return
    limites = "Business Discovery não traz visualizações, alcance, salvamentos nem compartilhamentos; vídeo não analisado."
    if falhas:
        limites += " Falha na coleta de: " + ", ".join(falhas) + "."
    notion("POST", "pages", {"parent": {"database_id": DB_PESQUISA}, "properties": {
        "Nome": {"title": rt("Coleta Instagram — " + HOJE.isoformat())},
        "Data da pesquisa": {"date": {"start": HOJE.isoformat()}},
        "Região": {"select": {"name": "Rio de Janeiro (RJ)"}},
        "Período analisado": {"rich_text": rt(periodo)},
        "Concorrentes": {"multi_select": [{"name": m} for m in ok]},
        "Publicações avaliadas": {"number": avaliadas},
        "Outliers": {"number": outliers},
        "Fonte": {"rich_text": rt("Instagram Graph API / Business Discovery, " + dt.datetime.now(BRT).strftime("%d/%m %Hh%M"))},
        "Cobertura e limitações": {"rich_text": rt(limites)}}, "children": corpo[:100]})
    print("coleta salva no Notion")


def avisar():
    achados = notion("POST", "databases/%s/query" % DB_PESQUISA,
                     {"filter": {"property": "Nome", "title": {"equals": "Pesquisa Instagram — " + HOJE.isoformat()}}})["results"]
    radar = notion("POST", "databases/%s/query" % DB_RADAR,
                   {"filter": {"property": "Data da pesquisa", "date": {"equals": HOJE.isoformat()}}})["results"]
    linhas = []
    if achados:
        linhas.append("📊 Pesquisa de concorrentes pronta: " + achados[0]["url"])
    else:
        linhas.append("SiCa: a pesquisa de concorrentes de hoje ainda não ficou pronta. Vale conferir.")
    if radar:
        linhas.append("🎬 Radar de Trends: %d ideias de gravação em https://www.notion.so/%s" % (len(radar), DB_RADAR))
    else:
        linhas.append("SiCa: o Radar de Trends de hoje não gerou cards. Vale conferir.")
    if DRY:
        print("teste: concorrentes %s | radar %d cards" % ("pronta" if achados else "nao existe", len(radar)))
        return
    whatsapp(chr(10).join(linhas))


if __name__ == "__main__":
    carregar_env()
    modos = {"relatorio": relatorio, "coletar": coletar, "avisar": avisar}
    pedido = [a for a in sys.argv[1:] if a != "--dry"]
    if len(pedido) != 1 or pedido[0] not in modos:
        sys.exit(__doc__)
    modos[pedido[0]]()
