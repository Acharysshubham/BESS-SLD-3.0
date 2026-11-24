"""PCS sizing, container pairing, DC compatibility and configuration comparison."""
import math
import pandas as pd
from .common import cl, worst


def required(p_dc, eff, p_target, q_mvar, pf):
    """Battery DC power -> AC active power -> required apparent power (distinct quantities)."""
    p_ac = p_target if p_target > 0 else p_dc * eff
    s = math.hypot(p_ac, q_mvar) if q_mvar > 0 else (p_ac / pf if 0 < pf < 1 else p_ac)
    return p_ac, s


def allocate(units, n):
    """Pair containers with n PCS. n<=containers: balanced grouping (central PCS, heterogeneous-safe).
    n>containers: containers are split into rack groups feeding several PCS (string/modular)."""
    if n <= len(units):
        g, load = [[] for _ in range(n)], [0.0] * n
        for u in sorted(units, key=lambda u: -u["p_dc"]):
            j = load.index(min(load)); g[j].append((u["id"], 1.0)); load[j] += u["p_dc"]
        return sorted((sorted(x) for x in g), key=lambda x: x[0][0])
    k = {u["id"]: 1 for u in units}
    for _ in range(n - len(units)):
        u = max(units, key=lambda u: u["p_dc"] / k[u["id"]]); k[u["id"]] += 1
    return [[(u["id"], 1.0 / k[u["id"]])] for u in units for _ in range(k[u["id"]])]


def dc_check(group, ub, m):
    cs = [ub[i] for i, _ in group]; p = min(sum(ub[i]["p_dc"] * f for i, f in group), m["p_mw"] / m["eff"])
    r = []
    vlo, vhi = min(c["vdc_min"] for c in cs), max(c["vdc_max"] for c in cs)
    if max(c["vdc_min"] for c in cs) >= min(c["vdc_max"] for c in cs): r.append(("FAIL", "DC voltage", "Paralleled containers have no common voltage window"))
    elif m["vdc_min"] <= 0 or m["vdc_max"] <= 0: r.append(("UNVERIFIED", "DC voltage", "PCS DC window not provided"))
    elif vlo < m["vdc_min"] or vhi > m["vdc_max"]: r.append(("FAIL", "DC voltage", f"Battery window {vlo:g}-{vhi:g} V outside PCS {m['vdc_min']:g}-{m['vdc_max']:g} V"))
    else: r.append(("PASS", "DC voltage", "Battery window inside PCS DC window"))
    i = p * 1e6 / max(vlo, 1)
    if m["idc_max"] <= 0: r.append(("UNVERIFIED", "DC current", "PCS max DC current not provided"))
    elif i > m["idc_max"]: r.append(("FAIL", "DC current", f"{i:.0f} A at min DC voltage exceeds PCS limit {m['idc_max']:g} A"))
    else: r.append(("PASS", "DC current", f"{i:.0f} A <= {m['idc_max']:g} A"))
    n = len(group)
    if n > m["max_cont"]: r.append(("FAIL", "Containers per PCS", f"{n} containers > permitted {int(m['max_cont'])}"))
    if n > m["n_ch"]: r.append(("WARN", "DC channels", f"{n} containers on {int(m['n_ch'])} DC input channel(s): DC combiner required"))
    if n > 1: r.append(("WARN", "DC paralleling", "Manufacturer confirmation required for paralleled containers"))
    return r


def evaluate(m, P, units, p_dc, red=None, n_ovr=0):
    red = red or P["pcs_red"]
    p_ac, s_req = required(p_dc, m["eff"], P["pcs_ptarget"], P["pcs_q"], P["pcs_pf"])
    d, ml = P["pcs_derate"], P["pcs_maxload"]
    n_s, n_p = cl(s_req / (m["s_mva"] * d * ml)), cl(p_ac / (m["p_mw"] * d * ml))
    n_op = max(n_s, n_p, 1)
    n = n_ovr if n_ovr > 0 else n_op + {"None": 0, "N+1": 1, "User": int(P["pcs_spare"])}[red]
    groups = allocate(units, n); ub = {u["id"]: u for u in units}
    dc = [dc_check(g, ub, m) for g in groups]
    s1 = m["s_mva"]
    return dict(model=m["model"], m=m, red="Manual" if n_ovr > 0 else red, p_ac=p_ac, s_req=s_req, n_by_s=n_s, n_by_p=n_p, n_op=n_op,
                spare=n - n_op, n=n, s_inst=n * s1, p_inst=n * m["p_mw"], loading=s_req / (n * s1 * d) * 100 if n else 0,
                after_fail=(n - 1) * s1 * d, margin=(n - 1) * s1 * d - s_req, ratio_ok=(n % len(units) == 0 or len(units) % n == 0),
                groups=groups, dc=dc, dc_status=worst([x[0] for g in dc for x in g]))


def configs(P, units, p_dc):
    reds = ["None", "N+1"] + (["User"] if P["pcs_red"] == "User" else [])
    ev = [evaluate(m, P, units, p_dc, r) for m in P["pcs_cat"] for r in reds]
    feas = [e for e in ev if e["dc_status"] != "FAIL"] or ev
    pick = lambda c, k: min(c, key=k) if c else None
    cost = pick([e for e in feas if e["spare"] == 0], lambda e: (e["s_inst"], e["n"])) or pick(feas, lambda e: e["s_inst"])
    bal = pick([e for e in feas if e["red"] == P["pcs_red"]], lambda e: (e["dc_status"] != "PASS", e["s_inst"] * (1 if e["ratio_ok"] else 1.05), e["n"])) or cost
    hi = pick([e for e in feas if e["spare"] >= 1], lambda e: (e["m"]["s_mva"] / e["s_inst"], e["s_inst"])) or bal
    picks = {"Minimum cost": cost, "Balanced": bal, "High reliability": hi}
    tab = pd.DataFrame([dict(Config=k, Model=e["model"], Redundancy=e["red"], Operating=e["n_op"], Installed=e["n"], **{
        "Installed MVA": round(e["s_inst"], 2), "Loading %": round(e["loading"], 1), "After 1 failure (MVA)": round(e["after_fail"], 2),
        "Containers:PCS": f"{len(units)}:{e['n']}", "DC check": e["dc_status"]}) for k, e in picks.items()])
    return picks, tab
