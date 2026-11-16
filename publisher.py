#!/usr/bin/env python3
"""SiCa Publisher - publica no Instagram os posts aprovados na fila do Notion.

Seguro por padrao: sem --live nada e publicado (apenas mostra o que faria).
So publica linhas com: Status = Aprovado, Auto marcado, "Publicar em" ja vencido,
conta Instagram e URLs publicas das imagens preenchidas.

Uso:
  python publisher.py --mock mock_queue.json --now 2026-11-18T19:00:00-03:00   (teste local, sem rede)
  python publisher.py                       (le o Notion, simula, nao publica)
  python publisher.py --live                (publica de verdade; exige SICA_LIVE=1)

Variaveis de ambiente (nunca coloque no codigo):
  NOTION_TOKEN, NOTION_DB_ID, META_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BRT = timezone(timedelta(hours=-3))
GRAPH = "https://graph.facebook.com/v21.0"
NOTION = "https://api.notion.com/v1"
IG_ACCOUNT_LABEL = "Instagram @redescacademia"


def load_env(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def http(method, url, data=None, headers=None):
    body = None
    headers = dict(headers or {})
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError("HTTP %s em %s: %s" % (e.code, url.split("?")[0], detail))


def notion_headers():
    return {"Authorization": "Bearer " + os.environ["NOTION_TOKEN"], "Notion-Version": "2022-06-28"}


def text_of(prop):
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(i.get("plain_text", "") for i in items)


def parse_row(page):
    p = page["properties"]
    date = (p.get("Publicar em", {}).get("date") or {}).get("start")
    return {
        "id": page["id"],
        "titulo": text_of(p.get("Peça", {})),
        "status": (p.get("Status", {}).get("status") or {}).get("name"),
        "conta": (p.get("Conta", {}).get("select") or {}).get("name"),
        "formato": (p.get("Formato", {}).get("select") or {}).get("name"),
        "publicar_em": date,
        "auto": bool(p.get("Auto", {}).get("checkbox")),
        "legenda": text_of(p.get("Legenda", {})),
        "imagens": [u.strip() for u in text_of(p.get("Imagens (URLs públicas)", {})).splitlines() if u.strip()],
    }


def parse_when(value):
    if not value:
        return None
    if len(value) == 10:  # so a data: considera 08:00 de Brasilia
        return datetime.fromisoformat(value).replace(hour=8, tzinfo=BRT)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=BRT)


def check(row, now):
    """Devolve (pronto, motivo)."""
    if row["status"] != "Aprovado":
        return False, "status nao e Aprovado"
    if not row["auto"]:
        return False, "Auto desmarcado (publicacao manual)"
    when = parse_when(row["publicar_em"])
    if when is None:
        return False, "sem data em 'Publicar em'"
    if when > now:
        return False, "ainda nao chegou a hora (%s)" % when.strftime("%d/%m %H:%M")
    if row["conta"] != IG_ACCOUNT_LABEL:
        return False, "conta nao suportada ainda (%s)" % row["conta"]
    if row["formato"] not in ("Feed 4:5", "Carrossel", "Stories"):
        return False, "formato nao suportado (%s)" % row["formato"]
    if not row["imagens"]:
        return False, "faltam URLs publicas das imagens"
    if row["formato"] == "Carrossel" and not 2 <= len(row["imagens"]) <= 10:
        return False, "carrossel precisa de 2 a 10 imagens"
    if row["formato"] in ("Feed 4:5", "Stories") and len(row["imagens"]) != 1:
        return False, "este formato precisa de exatamente 1 imagem"
    return True, "ok"


def graph_post(path, params):
    params = dict(params)
    params["access_token"] = os.environ["META_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(GRAPH + "/" + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError("Meta HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:500]))


def wait_container(cid):
    for _ in range(20):
        q = urllib.parse.urlencode({"fields": "status_code", "access_token": os.environ["META_ACCESS_TOKEN"]})
        st = http("GET", "%s/%s?%s" % (GRAPH, cid, q)).get("status_code")
        if st == "FINISHED":
            return
        if st == "ERROR":
            raise RuntimeError("Meta recusou a midia (status ERROR)")
        time.sleep(3)
    raise RuntimeError("Tempo esgotado esperando a Meta processar a midia")


def publish_instagram(row):
    ig = os.environ["INSTAGRAM_BUSINESS_ACCOUNT_ID"]
    fmt = row["formato"]
    if fmt == "Carrossel":
        kids = []
        for url in row["imagens"]:
            c = graph_post(ig + "/media", {"image_url": url, "is_carousel_item": "true"})["id"]
            wait_container(c)
            kids.append(c)
        cid = graph_post(ig + "/media", {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": row["legenda"]})["id"]
    elif fmt == "Stories":
        cid = graph_post(ig + "/media", {"image_url": row["imagens"][0], "media_type": "STORIES"})["id"]
    else:
        cid = graph_post(ig + "/media", {"image_url": row["imagens"][0], "caption": row["legenda"]})["id"]
    wait_container(cid)
    return graph_post(ig + "/media_publish", {"creation_id": cid})["id"]


def notion_update(page_id, status, post_id, resultado):
    props = {
        "Status": {"status": {"name": status}},
        "Resultado": {"rich_text": [{"text": {"content": resultado[:1900]}}]},
    }
    if post_id:
        props["ID do post"] = {"rich_text": [{"text": {"content": str(post_id)}}]}
    http("PATCH", "%s/pages/%s" % (NOTION, page_id), {"properties": props}, notion_headers())


def fetch_queue():
    payload = {"filter": {"property": "Status", "status": {"equals": "Aprovado"}}, "page_size": 100}
    res = http("POST", "%s/databases/%s/query" % (NOTION, os.environ["NOTION_DB_ID"]), payload, notion_headers())
    return [parse_row(p) for p in res.get("results", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="publica de verdade (exige SICA_LIVE=1)")
    ap.add_argument("--mock", help="arquivo JSON com linhas de teste (sem rede)")
    ap.add_argument("--now", help="data/hora ISO para simular o relogio")
    args = ap.parse_args()

    load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(BRT)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BRT)

    live = args.live and os.environ.get("SICA_LIVE") == "1" and not args.mock
    if args.live and not live:
        print("AVISO: --live ignorado (precisa de SICA_LIVE=1 e nao funciona com --mock). Rodando em simulacao.")

    if not args.mock:
        faltando = [k for k in ("NOTION_TOKEN", "NOTION_DB_ID") if not os.environ.get(k)]
        if faltando:
            print("ERRO: falta preencher no .env: " + ", ".join(faltando))
            return 1
    rows = json.load(open(args.mock, encoding="utf-8")) if args.mock else fetch_queue()
    print("[%s] %d linha(s) aprovada(s) na fila. Modo: %s" % (now.strftime("%d/%m %H:%M"), len(rows), "AO VIVO" if live else "SIMULACAO"))

    done = 0
    for row in rows:
        ok, why = check(row, now)
        if not ok:
            print("  - PULA  %-45s %s" % (row["titulo"][:45], why))
            continue
        if not live:
            print("  - PUBLICARIA  %s (%s, %d imagem(ns))" % (row["titulo"], row["formato"], len(row["imagens"])))
            continue
        try:
            post_id = publish_instagram(row)
            notion_update(row["id"], "Publicado", post_id, "Publicado automaticamente em %s" % now.strftime("%d/%m/%Y %H:%M"))
            print("  - PUBLICADO  %s -> %s" % (row["titulo"], post_id))
            done += 1
        except Exception as e:  # nunca derruba a fila inteira
            print("  - ERRO  %s: %s" % (row["titulo"], e))
            try:
                notion_update(row["id"], "Erro", None, "Falha ao publicar: %s" % e)
            except Exception as e2:
                print("    (nao consegui registrar o erro no Notion: %s)" % e2)
    print("Fim. Publicados: %d" % done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
