#!/usr/bin/env python3
"""Leva a data do Calendario Postagem (card) para a Fila de publicacao. Sem IA.

Ligacao: a linha da Fila tem 'card:<id do card>' no campo "Pasta dos arquivos".
Regras (so no sentido seguro):
  - mudou a data/hora do card  -> muda "Publicar em" (nunca liga Auto nem muda Status)
  - card sem data, apagado ou marcado como Postado -> desliga Auto (evita publicar sem querer ou duplicado)
  - data nova no passado -> nao mexe
Uso: python sync_calendario.py [--dry]
"""
import json, os, re, sys, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
FILA = "41a74be6e5ad81949043f47792d414d6"
DRY = "--dry" in sys.argv


def load_env():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"'))


def api(method, path, body=None):
    h = {"Authorization": "Bearer " + os.environ["NOTION_TOKEN"], "Notion-Version": "2022-06-28",
         "Content-Type": "application/json", "User-Agent": "curl/8.0"}
    req = urllib.request.Request("https://api.notion.com/v1/" + path, method=method, headers=h,
                                 data=None if body is None else json.dumps(body).encode())
    return json.load(urllib.request.urlopen(req, timeout=60))


def txt(p):
    return "".join(x["plain_text"] for x in p.get("rich_text") or p.get("title") or [])


def quando(s, base=None):
    """datetime em Brasilia. Data sem hora usa a hora da linha (base); sem base, devolve None."""
    if not s:
        return None
    if len(s) == 10:
        if base is None:
            return None
        return datetime.fromisoformat(s).replace(hour=base.hour, minute=base.minute, tzinfo=BRT)
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.astimezone(BRT) if d.tzinfo else d.replace(tzinfo=BRT)


def decidir(row_when, auto, card, now):
    """Devolve (mudancas, motivo). card = None se apagado, senao (date_start, etapa)."""
    if card is None:
        return ({"Auto": False}, "card apagado") if auto else ({}, "")
    date, etapa = card
    if "postado" in (etapa or "").lower():
        return ({"Auto": False}, "card marcado como Postado") if auto else ({}, "")
    if not date:
        return ({"Auto": False}, "card sem data no calendario") if auto else ({}, "")
    novo = quando(date, row_when)
    if novo is None or novo == row_when:
        return {}, ""
    if novo < now - timedelta(minutes=15):
        return {}, "data nova ja passou (%s); nao mexi" % novo.strftime("%d/%m %H:%M")
    return {"Publicar em": novo}, "calendario mudou para %s" % novo.strftime("%d/%m %H:%M")


def main():
    load_env()
    now = datetime.now(BRT)
    rows = api("POST", "databases/%s/query" % FILA, {"page_size": 100, "filter": {"and": [
        {"property": "Status", "status": {"does_not_equal": "Publicado"}},
        {"property": "Pasta dos arquivos", "rich_text": {"contains": "card:"}}]}})["results"]
    mudou = 0
    for r in rows:
        p = r["properties"]
        m = re.search(r"card:\s*([0-9a-f-]{32,36})", txt(p["Pasta dos arquivos"]))
        if not m:
            continue
        nome = txt(p["Peça"])
        try:
            c = api("GET", "pages/" + m.group(1))
            if c.get("archived") or c.get("in_trash"):
                card = None
            else:
                cp = c["properties"]
                card = ((cp["Date"]["date"] or {}).get("start"), (cp["Etapa"]["select"] or {}).get("name"))
        except urllib.error.HTTPError as e:
            print("  ! %s: nao li o card (%s)" % (nome, e.code))
            continue
        row_when = quando((p["Publicar em"]["date"] or {}).get("start"))
        muda, motivo = decidir(row_when, p["Auto"]["checkbox"], card, now)
        if motivo:
            print("  - %s: %s" % (nome, motivo))
        if not muda:
            continue
        mudou += 1
        if DRY:
            continue
        props = {}
        if "Auto" in muda:
            props["Auto"] = {"checkbox": False}
            props["Resultado"] = {"rich_text": [{"text": {"content": "Pausado: %s (%s)" % (motivo, now.strftime("%d/%m %H:%M"))}}]}
        if "Publicar em" in muda:
            props["Publicar em"] = {"date": {"start": muda["Publicar em"].isoformat(timespec="seconds")}}
        api("PATCH", "pages/" + r["id"], {"properties": props})
    print("sync: %d linha(s) ligada(s), %d ajuste(s)%s" % (len(rows), mudou, " (simulacao)" if DRY else ""))


if __name__ == "__main__":
    main()
