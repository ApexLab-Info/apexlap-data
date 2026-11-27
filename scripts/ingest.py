#!/usr/bin/env python3
"""ApexLap community ingest. One issue = one action, validated and written as JSON files.
Circuits publish automatically (unofficial). 'Oficial:' requests (1 per user per month) wait for label 'oficial'."""
import json, math, os, re, urllib.request

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
    if close: call(base, {"state": "closed", "state_reason": "completed"}, "PATCH")

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
    dlon = (g["a"][1] - g["b"][1]) * 111000 * max(0.1, abs(math.cos(math.radians(g["a"][0]))))
    w = (dlat ** 2 + dlon ** 2) ** 0.5
    if not (3 <= w <= 100): raise ValueError(f"ancho de línea absurdo ({w:.0f} m)")

def clean(s, n): return re.sub(r"[\x00-\x1f<>`]", "", str(s)).strip()[:n]
def user_ok(u): return bool(re.fullmatch(r"[A-Za-z0-9-]{1,39}", u or ""))
DEMO = json.loads('{"id": "c-demo", "name": "Demo (simulador)", "directional": true, "finish": {"a": [40.4168, -3.7019455], "b": [40.4168, -3.7021109]}, "sectors": [{"a": [40.4160176, -3.7038], "b": [40.4161435, -3.7038]}, {"a": [40.4168, -3.7056545], "b": [40.4168, -3.7054891]}, {"a": [40.4175824, -3.7038], "b": [40.4174565, -3.7038]}]}')

def ensure_demo():
    """The official Demo circuit (matches the in-app simulator) is always present."""
    index = jload(P("index.json"), [])
    if any(e["id"] == "c-demo" for e in index): return
    jsave(P("circuits", "c-demo.json"), DEMO)
    f = DEMO["finish"]
    index.append({"id": "c-demo", "name": DEMO["name"], "lat": round((f["a"][0] + f["b"][0]) / 2, 6), "lon": round((f["a"][1] + f["b"][1]) / 2, 6),
                  "sectors": 3, "stage": False, "file": "circuits/c-demo.json", "by": os.environ.get("REPO_OWNER", ""), "official": True})
    jsave(P("index.json"), index)

def tail(title): return title.split(":", 1)[1].strip()

def circuit(issue):
    o = block(issue["body"])
    by = issue["user"]["login"]
    name = clean(o["name"], 60)
    if len(name) < 3: raise ValueError("nombre demasiado corto")
    gate(o["finish"]); sectors = o.get("sectors", [])
    if len(sectors) > 20: raise ValueError("demasiados sectores")
    for g in sectors: gate(g)
    if o.get("end"): gate(o["end"])
    index = jload(P("index.json"), [])
    mine = [e for e in index if e.get("by") == by]
    officials = sum(1 for e in mine if e.get("official"))
    if len(mine) >= 30 + 5 * officials: raise ValueError(f"has alcanzado tu máximo de circuitos ({30 + 5 * officials}); cada oficial suma 5")
    quota = jload(P("meta", "quota.json"), {})
    qu = quota.get(by, {"day": "", "n": 0, "spent": 0})
    day = issue.get("created_at", "0000-00-00")[:10]
    if qu["day"] != day: qu["day"], qu["n"] = day, 0
    if qu["n"] >= 5:   # over the daily 5: spend one credit (1 per official circuit)
        if officials - qu["spent"] <= 0: raise ValueError("máximo de 5 circuitos al día; mañana puedes seguir (los oficiales dan créditos extra)")
        qu["spent"] += 1
    qu["n"] += 1; quota[by] = qu; jsave(P("meta", "quota.json"), quota)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "circuito"
    cid = f"c-{slug}-{issue['number']}"
    out = {"id": cid, "name": name, "directional": bool(o.get("directional", True)), "finish": o["finish"], "sectors": sectors}
    if o.get("end"): out["end"] = o["end"]
    jsave(P("circuits", cid + ".json"), out)
    lat = (o["finish"]["a"][0] + o["finish"]["b"][0]) / 2; lon = (o["finish"]["a"][1] + o["finish"]["b"][1]) / 2
    index.append({"id": cid, "name": name, "lat": round(lat, 6), "lon": round(lon, 6), "sectors": len(sectors),
                  "stage": bool(o.get("end")), "file": f"circuits/{cid}.json", "by": by, "official": False})
    jsave(P("index.json"), index)
    return f"Circuito publicado como `{cid}`."

def circuit_delete(issue):
    by = issue["user"]["login"]; cid = tail(issue["title"])
    if cid == "c-demo": raise ValueError("el circuito Demo no se puede eliminar")
    index = jload(P("index.json"), [])
    e = next((x for x in index if x["id"] == cid), None)
    if not e: raise ValueError("circuito no encontrado")
    if e.get("by", "").lower() != by.lower(): raise ValueError("solo el autor puede eliminarlo")
    jsave(P("index.json"), [x for x in index if x["id"] != cid])
    for path in (P("circuits", cid + ".json"), P("rankings", cid + ".json")):
        if os.path.exists(path): os.remove(path)
    d = P("profiles")
    if os.path.isdir(d):
        for fn in [x for x in os.listdir(d) if x != "index.json"]:
            pr = jload(os.path.join(d, fn), {})
            if cid in pr.get("bests", {}):
                del pr["bests"][cid]; jsave(os.path.join(d, fn), pr)
    return f"«{e['name']}» eliminado de la comunidad."

def official_request(issue):
    by = issue["user"]["login"]; cid = tail(issue["title"])
    e = next((x for x in jload(P("index.json"), []) if x["id"] == cid), None)
    if not e: raise ValueError("circuito no encontrado")
    if e.get("by") != by: raise ValueError("solo el autor puede pedir que sea oficial")
    if e.get("official"): raise ValueError("ya es oficial")
    month = issue.get("created_at", "0000-00")[:7]
    q = jload(P("meta", "official_requests.json"), {})
    if q.get(by) == month: raise ValueError("ya usaste tu solicitud de este mes")
    q[by] = month; jsave(P("meta", "official_requests.json"), q)
    owner = os.environ.get("REPO_OWNER", "")
    return (f"Solicitud recibida. @{owner} revisa «{e['name']}» y, si lo acepta, añade la etiqueta `oficial`.", False)

def official_grant(issue):
    cid = tail(issue["title"])
    index = jload(P("index.json"), [])
    e = next((x for x in index if x["id"] == cid), None)
    if not e: raise ValueError("circuito no encontrado")
    e["official"] = True; jsave(P("index.json"), index)
    return f"«{e['name']}» ahora es oficial ✓."

def profile(issue):
    o = block(issue["body"])
    login = issue["user"]["login"]
    if not user_ok(login): raise ValueError("usuario inválido")
    ids = {e["id"] for e in jload(P("index.json"), [])}
    bests = {}
    for k, v in (o.get("bests") or {}).items():
        if k in ids and isinstance(v, (int, float)) and 5000 <= v <= 3600000: bests[k] = int(v)
    name = clean(o.get("name", login), 30) or login
    prof = {"name": name, "bests": bests}
    av = str(o.get("avatar", ""))
    if av:
        if len(av) > 14000 or not re.fullmatch(r"[A-Za-z0-9+/=]+", av): raise ValueError("foto demasiado grande o inválida")
        prof["avatar"] = av
    jsave(P("profiles", login + ".json"), prof)
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

# ---- friendships: requests/{to}.json = pending senders, friends/{user}.json = accepted ----
def friends_of(u): return jload(P("friends", u + ".json"), [])
def requests_of(u): return jload(P("requests", u + ".json"), [])

def friend_request(issue):
    me, to = issue["user"]["login"], tail(issue["title"])
    if not user_ok(to) or to.lower() == me.lower(): raise ValueError("usuario inválido")
    if to in friends_of(me): raise ValueError("ya sois amigos")
    if me in requests_of(to): raise ValueError("solicitud ya enviada")
    if to in requests_of(me):  # they already asked me: that is an acceptance
        return friend_accept({**issue, "title": "x: " + to})
    r = requests_of(to) + [me]
    if len(r) > 50: raise ValueError("demasiadas solicitudes pendientes para ese usuario")
    jsave(P("requests", to + ".json"), r)
    return f"Solicitud enviada a {to}."

def friend_accept(issue):
    me, frm = issue["user"]["login"], tail(issue["title"])
    if not user_ok(frm) or frm not in requests_of(me): raise ValueError("no hay solicitud de ese usuario")
    jsave(P("requests", me + ".json"), [x for x in requests_of(me) if x != frm])
    for a, b in ((me, frm), (frm, me)):
        f = friends_of(a)
        if b not in f: jsave(P("friends", a + ".json"), (f + [b])[:500])
    return f"Ahora eres amigo de {frm}."

def friend_reject(issue):
    me, frm = issue["user"]["login"], tail(issue["title"])
    jsave(P("requests", me + ".json"), [x for x in requests_of(me) if x != frm])
    return "Solicitud rechazada."

def friend_remove(issue):
    me, other = issue["user"]["login"], tail(issue["title"])
    for a, b in ((me, other), (other, me)):
        jsave(P("friends", a + ".json"), [x for x in friends_of(a) if x != b])
    return "Amistad eliminada."

def main():
    ev = json.load(open(os.environ["EVENT_PATH"], encoding="utf-8"))
    issue, action = ev["issue"], ev["action"]
    title, num = issue.get("title", ""), issue["number"]
    labels = {l["name"] for l in issue.get("labels", [])}
    kind = title.split(":", 1)[0].strip()
    try:
        ensure_demo()
        if action == "opened":
            fn = {"Circuito": circuit, "Circuito-eliminar": circuit_delete, "Perfil": profile, "Amistad": friend_request, "Amistad-aceptar": friend_accept,
                  "Amistad-rechazar": friend_reject, "Amistad-quitar": friend_remove, "Oficial": official_request}.get(kind)
            if not fn: return
            res = fn(issue)
            if isinstance(res, tuple): reply(num, res[0], close=res[1])
            else: reply(num, res)
        elif action == "labeled" and kind == "Oficial" and ev.get("label", {}).get("name") == "oficial":
            reply(num, official_grant(issue))
    except Exception as e:
        reply(num, f"Rechazado: {e}")

if __name__ == "__main__": main()
