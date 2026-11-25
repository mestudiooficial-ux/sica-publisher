#!/usr/bin/env python3
"""Relatorio semanal das contas da SC (somente leitura, API oficial da Meta) em .docx.

python relatorio_semanal.py coletar
     -> relatorios/AAAA-MM-DD_dados.json e imprime o resumo
python relatorio_semanal.py doc [conclusoes.txt] [--enviar]
     -> relatorios/AAAA-MM-DD_relatorio-semanal.docx (com --enviar manda pelo WhatsApp da SiCa)
Em conclusoes.txt: linhas que comecam com '# ' viram titulo; '- ' viram item.
"""
import datetime as dt
import glob
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from xml.sax.saxutils import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SAIDA = os.path.join(RAIZ, "relatorios")
BRT = dt.timezone(dt.timedelta(hours=-3))
HOJE = dt.datetime.now(BRT).date()


def env_de(*partes):
    e = {}
    for linha in open(os.path.join(RAIZ, *partes), encoding="utf-8-sig"):
        if "=" in linha and not linha.strip().startswith("#"):
            k, v = linha.split("=", 1)
            e[k.strip()] = v.strip().strip('"')
    return e


def graph(path, tok, **q):
    q["access_token"] = tok
    url = "https://graph.facebook.com/v21.0/%s?%s" % (path, urllib.parse.urlencode(q))
    try:
        return json.load(urllib.request.urlopen(url, timeout=60))
    except urllib.error.HTTPError as e:
        return {"erro": json.loads(e.read())["error"]["message"][:200]}


def coletar():
    e = env_de(".env")
    tok = e["META_ACCESS_TOKEN"]
    contas = [("Rede", e["INSTAGRAM_BUSINESS_ACCOUNT_ID"]), ("Arsenal", "17841474870891069"),
              ("Rocha", "17841443765713067"), ("Colubandê", "17841403718568949")]
    desde = dt.datetime.now(BRT) - dt.timedelta(days=7)
    dados = {"data": HOJE.isoformat(), "desde": desde.date().isoformat(), "contas": []}
    for nome, ig in contas:
        a = graph(ig, tok, fields="username,followers_count")
        if "erro" in a:
            dados["contas"].append({"nome": nome, "erro": "sem acesso pela API"})
            continue
        c = {"nome": nome, "usuario": a["username"], "seguidores": a["followers_count"], "posts": []}
        m = graph(ig + "/media", tok, limit=50,
                  fields="id,media_type,media_product_type,timestamp,like_count,comments_count,permalink,caption")
        for x in m.get("data", []):
            quando = dt.datetime.strptime(x["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(BRT)
            if quando < desde:
                continue
            ins = graph(x["id"] + "/insights", tok, metric="reach,saved,shares,total_interactions")
            v = {i["name"]: i["values"][0]["value"] for i in ins.get("data", [])}
            if x.get("media_product_type") == "REELS":
                tipo = "Reel"
            else:
                tipo = {"CAROUSEL_ALBUM": "Carrossel", "IMAGE": "Imagem", "VIDEO": "Vídeo"}.get(x["media_type"], x["media_type"])
            c["posts"].append({
                "quando": quando.strftime("%d/%m %Hh%M"), "tipo": tipo,
                "texto": (x.get("caption") or "").split("\n")[0][:70],
                "alcance": v.get("reach"), "interacoes": v.get("total_interactions"),
                "curtidas": x.get("like_count"), "comentarios": x.get("comments_count"),
                "salvos": v.get("saved"), "envios": v.get("shares"), "link": x.get("permalink")})
        c["posts"].sort(key=lambda p: -(p["alcance"] or 0))
        dados["contas"].append(c)
    # variacao de seguidores contra o relatorio anterior
    antigos = sorted(f for f in glob.glob(os.path.join(SAIDA, "*_dados.json"))
                     if os.path.basename(f)[:10] < HOJE.isoformat())
    if antigos:
        ant = {c["nome"]: c.get("seguidores") for c in json.load(open(antigos[-1], encoding="utf-8"))["contas"]}
        for c in dados["contas"]:
            if c.get("seguidores") is not None and ant.get(c["nome"]) is not None:
                c["variacao"] = c["seguidores"] - ant[c["nome"]]
    os.makedirs(SAIDA, exist_ok=True)
    with open(os.path.join(SAIDA, HOJE.isoformat() + "_dados.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    for c in dados["contas"]:
        if "erro" in c:
            print(c["nome"], "-", c["erro"])
            continue
        var = "(%+d)" % c["variacao"] if "variacao" in c else ""
        print("%s @%s | seguidores %s %s | posts 7d: %d | alcance somado %d" % (
            c["nome"], c["usuario"], c["seguidores"], var, len(c["posts"]), sum(p["alcance"] or 0 for p in c["posts"])))
        for p in c["posts"]:
            print("   %s %-9s alc %-6s int %-4s salv %-3s env %-3s | %s" % (
                p["quando"], p["tipo"], p["alcance"], p["interacoes"], p["salvos"], p["envios"], p["texto"]))


# ---------- .docx sem dependencias ----------
def par(texto, tam=11, negrito=False, cor=None, antes=0, depois=120, recuo=0):
    r = "<w:rFonts w:ascii='Calibri' w:hAnsi='Calibri'/>"
    if negrito:
        r += "<w:b/>"
    if cor:
        r += "<w:color w:val='%s'/>" % cor
    r += "<w:sz w:val='%d'/>" % (tam * 2)
    return ("<w:p><w:pPr><w:spacing w:before='%d' w:after='%d'/><w:ind w:left='%d'/></w:pPr>"
            "<w:r><w:rPr>%s</w:rPr><w:t xml:space='preserve'>%s</w:t></w:r></w:p>") % (antes, depois, recuo, r, escape(str(texto)))


def tabela(linhas, larguras):
    borda = "".join("<w:%s w:val='single' w:sz='4' w:color='BBBBBB'/>" % s
                    for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    x = "<w:tbl><w:tblPr><w:tblW w:w='%d' w:type='dxa'/><w:tblBorders>%s</w:tblBorders></w:tblPr><w:tblGrid>%s</w:tblGrid>" % (
        sum(larguras), borda, "".join("<w:gridCol w:w='%d'/>" % w for w in larguras))
    for i, linha in enumerate(linhas):
        x += "<w:tr>"
        for w, cel in zip(larguras, linha):
            fundo = "<w:shd w:val='clear' w:color='auto' w:fill='D8182A'/>" if i == 0 else ""
            x += "<w:tc><w:tcPr><w:tcW w:w='%d' w:type='dxa'/>%s</w:tcPr>%s</w:tc>" % (
                w, fundo, par(cel, 9, i == 0, "FFFFFF" if i == 0 else None, 20, 20))
        x += "</w:tr>"
    return x + "</w:tbl>"


def num(v):
    return "-" if v is None else v


def gerar(conclusoes, enviar):
    with open(os.path.join(SAIDA, HOJE.isoformat() + "_dados.json"), encoding="utf-8") as f:
        d = json.load(f)
    br = lambda s: dt.date.fromisoformat(s).strftime("%d/%m/%Y")
    corpo = par("Relatório semanal · Rede SC Academia", 18, True, "D8182A")
    corpo += par("Período: %s a %s · Instagram, dados da API oficial da Meta" % (br(d["desde"]), br(d["data"])), 10, cor="555555")
    if conclusoes and os.path.exists(conclusoes):
        for linha in open(conclusoes, encoding="utf-8").read().splitlines():
            if linha.startswith("# "):
                corpo += par(linha[2:], 13, True, antes=200)
            elif linha.startswith("- "):
                corpo += par("•  " + linha[2:], recuo=280, depois=60)
            elif linha.strip():
                corpo += par(linha)
    corpo += par("Visão geral", 13, True, antes=240)
    linhas = [["Conta", "Seguidores", "Variação", "Posts", "Alcance somado", "Interações"]]
    for c in d["contas"]:
        if "erro" in c:
            linhas.append([c["nome"], "sem acesso", "-", "-", "-", "-"])
        else:
            linhas.append([c["nome"], c["seguidores"], ("%+d" % c["variacao"]) if "variacao" in c else "-", len(c["posts"]),
                           sum(p["alcance"] or 0 for p in c["posts"]), sum(p["interacoes"] or 0 for p in c["posts"])])
    corpo += tabela(linhas, [1900, 1500, 1200, 900, 1900, 1500])
    for c in d["contas"]:
        if "erro" in c:
            continue
        corpo += par("%s (@%s)" % (c["nome"], c["usuario"]), 13, True, antes=280)
        if not c["posts"]:
            corpo += par("Nenhum post no feed ou Reel no período.")
            continue
        linhas = [["Quando", "Tipo", "Começo da legenda", "Alcance", "Interações", "Salvos", "Envios"]]
        linhas += [[p["quando"], p["tipo"], p["texto"], num(p["alcance"]), num(p["interacoes"]), num(p["salvos"]), num(p["envios"])]
                   for p in c["posts"]]
        corpo += tabela(linhas, [1100, 900, 3500, 900, 1100, 700, 700])
    corpo += par("Stories não entram: a Meta só mantém os números deles por 24 horas. O alcance é estimado e o alcance somado "
                 "conta a mesma pessoa mais de uma vez.", 9, cor="777777", antes=240)
    nome = os.path.join(SAIDA, HOJE.isoformat() + "_relatorio-semanal.docx")
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    cab = "<?xml version='1.0' encoding='UTF-8'?>"
    with zipfile.ZipFile(nome, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", cab + "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
                   "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
                   "<Default Extension='xml' ContentType='application/xml'/>"
                   "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>")
        z.writestr("_rels/.rels", cab + "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>")
        z.writestr("word/document.xml", cab + "<w:document xmlns:w='%s'><w:body>%s<w:sectPr><w:pgSz w:w='11906' w:h='16838'/>"
                   "<w:pgMar w:top='1000' w:bottom='1000' w:left='1000' w:right='1000' w:header='0' w:footer='0' w:gutter='0'/></w:sectPr></w:body></w:document>" % (w, corpo))
    print("gerado:", nome)
    if enviar:
        mandar(nome)


def mandar(arquivo):
    e = env_de("sica-whatsapp", ".env")
    base = "https://graph.facebook.com/v21.0/%s/" % e["WHATSAPP_PHONE_NUMBER_ID_TESTE"]
    h = {"Authorization": "Bearer " + e["WHATSAPP_TOKEN"], "User-Agent": "curl/8.0"}
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    nome = "Relatorio_semanal_SC_%s.docx" % HOJE.strftime("%d-%m")
    b = "----sica" + uuid.uuid4().hex
    corpo = b""
    for k, v in (("messaging_product", "whatsapp"), ("type", mime)):
        corpo += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode()
    corpo += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (b, nome, mime)).encode()
    with open(arquivo, "rb") as f:
        corpo += f.read() + ("\r\n--%s--\r\n" % b).encode()
    try:
        req = urllib.request.Request(base + "media", data=corpo, method="POST",
                                     headers={**h, "Content-Type": "multipart/form-data; boundary=" + b})
        mid = json.load(urllib.request.urlopen(req, timeout=90))["id"]
        msg = {"messaging_product": "whatsapp", "to": e["WHATSAPP_ALLOWED_NUMBER"], "type": "document",
               "document": {"id": mid, "filename": nome, "caption": "Relatório semanal das contas da SC"}}
        req = urllib.request.Request(base + "messages", data=json.dumps(msg).encode(), method="POST",
                                     headers={**h, "Content-Type": "application/json"})
        json.load(urllib.request.urlopen(req, timeout=60))
        print("enviado pelo WhatsApp (aceito pela Meta)")
    except urllib.error.HTTPError as ex:
        print("NAO ENVIADO:", ex.read().decode()[:300])
        sys.exit(2)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--enviar"]
    if a[:1] == ["coletar"]:
        coletar()
    elif a[:1] == ["doc"]:
        gerar(a[1] if len(a) > 1 else None, "--enviar" in sys.argv)
    else:
        print(__doc__)
