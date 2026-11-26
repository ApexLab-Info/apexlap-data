#!/usr/bin/env python3
"""Validates ApexLap issues and writes circuits/profiles/rankings. Circuits need the label 'aprobado'."""
import json, os, re, sys, urllib.request

ROOT = os.environ.get("DATA_DIR", ".")
def P(*a): return os.path.join(ROOT, *a)

def jload(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return default

def jsave(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def reply(num, msg, close=True):
    if not (os.environ.get("GH_TOKEN") and os.environ.get("REPO")): print("[issue]", msg); return
    repo, h = os.environ["REPO"], {"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json"}
    def call(url, data, method="POST"):
        urllib.request.urlopen(urllib.request.Request(url, json.dumps(data).encode(), h, method=method))
    base = f"https://api.github.com/repos/{repo}/issues/{num}"
    call(base + "/comments", {"body": msg})
    if close: call(base, {"state": "closed"}, "PATCH")

def block(body):
    m = re.search(r"```json\s*(\{.*?\})\s*```", body or "", re.S)
    if not m or len(m.group(1)) > 20000: raise ValueError("JSON no encontrado o demasiado grande")
    return json.loads(m.group(1))

def pt(p):
    if not (isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)): raise ValueError("punto inválido")
    if not (-90 <= p[0] <= 90 and -180 <= p[1] <= 180): raise ValueError("coordenadas fuera de rango")

def gate(g):
    pt(g["a"]); pt(g["b"])
    dlat = (g["a"][0] - g["b"][0]) * 111000
    dlon = (g["a"][1] - g["b"][1]) * 111000 * max(0.1, abs(__import__("math").cos(__import__("math").radians(g["a"][0]))))
    w = (dlat ** 2 + dlon ** 2) ** 0.5
    if not (3 <= w <= 100): raise ValueError(f"ancho de línea absurdo ({w:.0f} m)")

def clean(s, n): return re.sub(r"[\x00-\x1f<>`]", "", str(s)).strip()[:n]

def circuit(issue):
    o = block(issue["body"])
    name = clean(o["name"], 60)
    if len(name) < 3: raise ValueError("nombre demasiado corto")
    gate(o["finish"]); sectors = o.get("sectors", [])
    if len(sectors) > 20: raise ValueError("demasiados sectores")
    for g in sectors: gate(g)
    if o.get("end"): gate(o["end"])
    index = jload(P("index.json"), [])
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "circuito"
    cid = f"c-{slug}-{issue['number']}"
    by = issue["user"]["login"]
    out = {"id": cid, "name": name, "directional": bool(o.get("directional", True)), "finish": o["finish"], "sectors": sectors}
    if o.get("end"): out["end"] = o["end"]
    jsave(P("circuits", cid + ".json"), out)
    lat = (o["finish"]["a"][0] + o["finish"]["b"][0]) / 2; lon = (o["finish"]["a"][1] + o["finish"]["b"][1]) / 2
    index.append({"id": cid, "name": name, "lat": round(lat, 6), "lon": round(lon, 6), "sectors": len(sectors),
                  "stage": bool(o.get("end")), "file": f"circuits/{cid}.json", "by": by})
    jsave(P("index.json"), index)
    return f"Circuito publicado como `{cid}`."

def profile(issue):
    o = block(issue["body"])
    login = issue["user"]["login"]
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login): raise ValueError("usuario inválido")
    ids = {e["id"] for e in jload(P("index.json"), [])}
    bests = {}
    for k, v in (o.get("bests") or {}).items():
        if k in ids and isinstance(v, (int, float)) and 5000 <= v <= 3600000: bests[k] = int(v)
    name = clean(o.get("name", login), 30) or login
    jsave(P("profiles", login + ".json"), {"name": name, "bests": bests})
    idx = [e for e in jload(P("profiles", "index.json"), []) if e.get("user") != login]
    idx.append({"user": login, "name": name})
    jsave(P("profiles", "index.json"), idx)
    for cid in bests:   # rebuild ranking from every profile
        rows = []
        d = P("profiles")
        for fn in [x for x in os.listdir(d) if x != "index.json"]:
            pr = jload(os.path.join(d, fn), {})
            if cid in pr.get("bests", {}): rows.append({"user": fn[:-5], "name": pr.get("name", ""), "ms": pr["bests"][cid]})
        rows.sort(key=lambda r: r["ms"])
        jsave(P("rankings", cid + ".json"), rows[:50])
    return f"Perfil actualizado ({len(bests)} circuitos)."

def main():
    ev = json.load(open(os.environ["EVENT_PATH"], encoding="utf-8"))
    issue, action = ev["issue"], ev["action"]
    title, num = issue.get("title", ""), issue["number"]
    labels = {l["name"] for l in issue.get("labels", [])}
    try:
        if title.startswith("Circuito:"):
            if "aprobado" not in labels:
                if action == "opened": reply(num, "Recibido. Un administrador debe revisarlo (etiqueta `aprobado`).", close=False)
                return
            reply(num, circuit(issue))
        elif title.startswith("Perfil:") and action == "opened":
            reply(num, profile(issue))
    except Exception as e:
        reply(num, f"Rechazado: {e}")

if __name__ == "__main__": main()
