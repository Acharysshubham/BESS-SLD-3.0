import math
from . import connectivity_engine as CE
from sld.drawing_engine import check as erc


def validate(P, R, nodes, pp=None):
    v = []; add = lambda s, c, i, d: v.append(dict(Status=s, Category=c, Check=i, Detail=d))
    b, ch, idt, m, meta = R["bess"], R["pcs"], R["idt"], R["pcs"]["m"], R["meta"]
    add("PASS", "BESS", "Containers", f"{b['n']} containers, {b['e_total']:.1f} MWh installed, {b['p_dis']:.1f} MW DC discharge")
    for o in b["overridden"]: add("WARN", "BESS", "Manual override", f"{o} overridden by user; not derived from C-rate")
    # PCS
    ok = ch["n"] * m["p_mw"] * P["pcs_derate"] >= ch["p_ac"] - 1e-9
    add("PASS" if ok else "FAIL", "PCS", "Active power sufficiency", f"{ch['n']} x {m['p_mw']:g} MW (derate {P['pcs_derate']:g}) vs {ch['p_ac']:.2f} MW AC required")
    ok = ch["n"] * m["s_mva"] * P["pcs_derate"] >= ch["s_req"] - 1e-9
    add("PASS" if ok else "FAIL", "PCS", "Apparent power", f"{ch['n'] * m['s_mva']:.2f} MVA installed vs {ch['s_req']:.2f} MVA required")
    lim = P["pcs_maxload"] * 100
    add("FAIL" if ch["loading"] > lim + 1e-6 else "WARN" if ch["loading"] < 50 else "PASS", "PCS", "Loading", f"{ch['loading']:.1f}% of installed PCS MVA (limit {lim:.0f}%)")
    add("UNVERIFIED" if m["pf_min"] <= 0 else ("PASS" if P["pcs_pf"] >= m["pf_min"] else "FAIL"), "PCS", "Power-factor range", f"required PF {P['pcs_pf']:g}, PCS minimum {m['pf_min']:g}")
    qcap = ch["n_op"] * math.sqrt(max((m["s_mva"] * P["pcs_derate"]) ** 2 - (ch["p_ac"] / ch["n_op"]) ** 2, 0))
    add("PASS" if qcap >= R["q_tot"] - 1e-6 else "FAIL", "PCS", "Reactive capability at full P", f"{qcap:.2f} MVAr available vs {R['q_tot']:.2f} MVAr required")
    if ch["spare"] >= 1: add("PASS" if ch["margin"] >= 0 else "FAIL", "PCS", "Redundancy", f"After one PCS failure {ch['after_fail']:.2f} MVA vs {ch['s_req']:.2f} MVA required")
    else: add("PASS" if ch["margin"] >= 0 else "WARN", "PCS", "Redundancy", f"No spare PCS; after one failure {ch['after_fail']:.2f} MVA vs {ch['s_req']:.2f} MVA required")
    seen = set()
    for g in ch["dc"]:
        for s, i, d in g:
            if s != "PASS" and (s, i, d) not in seen: seen.add((s, i, d)); add(s, "DC compatibility", i, d)
    if not seen: add("PASS", "DC compatibility", "Voltage, current, containers per PCS", "All PCS-container groups pass the entered data")
    # IDT
    if not idt["feasible"]: add("FAIL", "IDT", "Feasibility", f"PCS {m['s_mva']:g} MVA does not fit IDT {P['idt_s']:g} MVA (thermal {idt['k_thermal']}, windings {idt['k_winding']})")
    else:
        add("PASS", "IDT", "Quantity", f"{idt['n']} IDT x {P['idt_s']:g} MVA (capacity-only estimate {idt['n_prelim']}); max {idt['per_idt']} PCS per IDT")
        worst_l = max(r["loading"] for r in idt["rows"])
        add("PASS" if worst_l <= P["idt_lim"] * 100 + 1e-6 else "FAIL", "IDT", "Loading", f"max {worst_l:.1f}% (limit {P['idt_lim'] * 100:.0f}%)")
        add("PASS" if m["s_mva"] * P["idt_ppw"] <= P["idt_s"] / P["idt_nlv"] * P["idt_lim"] * P["idt_derate"] + 1e-9 else "FAIL", "IDT", "LV winding rating", f"winding {P['idt_s'] / P['idt_nlv']:.2f} MVA (equal split assumed) vs {m['s_mva'] * P['idt_ppw']:.2f} MVA connected")
        if P["idt_ppw"] > 1: add("WARN", "IDT", "AC paralleling", "Several PCS per winding: manufacturer approval required")
    add("PASS" if abs(P["idt_kvs"] - P["pcs_lv_kv"]) < 1e-6 else "FAIL", "IDT", "LV voltage match", f"IDT {P['idt_kvs']:g} kV vs PCS {P['pcs_lv_kv']:g} kV")
    add("PASS" if abs(P["idt_kvp"] - P["mv_kv"]) < 1e-6 else "FAIL", "IDT", "MV voltage match", f"IDT {P['idt_kvp']:g} kV vs MV bus {P['mv_kv']:g} kV")
    add("PASS" if P["idt_z"] > 0 else "UNVERIFIED", "IDT", "Impedance data", f"{P['idt_z']:g}% entered" if P["idt_z"] > 0 else "Not entered")
    add("PASS" if P["idt_derate"] < 1 else "UNVERIFIED", "IDT", "Ambient derating", "Applied" if P["idt_derate"] < 1 else "No ambient derating applied; confirm against site temperature")
    add("UNVERIFIED", "IDT", "Harmonics / power quality", "Not assessed")
    # POI
    net = ch["p_ac"] - meta["aux_kw"] / 1e3 if P["aux_on"] else ch["p_ac"]
    if P["p_export"] > 0: add("PASS" if net <= P["p_export"] + 1e-9 else "FAIL", "POI", "Export limit", f"net {net:.2f} MW vs limit {P['p_export']:g} MW")
    else: add("UNVERIFIED", "POI", "Export limit", "No export limit entered")
    add("PASS" if P["isc_ka"] > 0 and P["vcb_ka"] >= P["isc_ka"] else ("FAIL" if P["isc_ka"] > 0 else "UNVERIFIED"), "POI", "Breaker breaking capacity", f"VCB {P['vcb_ka']:g} kA vs grid fault level {P['isc_ka']:g} kA")
    # Connectivity and model/diagram consistency
    g = CE.graph(nodes)
    import networkx as nx
    add("PASS" if nx.is_directed_acyclic_graph(g) else "FAIL", "Connectivity", "No loops", "Radial topology" if nx.is_directed_acyclic_graph(g) else "Cycle detected")
    for w in erc(nodes): add("WARN", "Connectivity", "Rule check", w)
    for w in CE.energy_paths(g): add("FAIL", "Connectivity", "Energy path", w)
    ids = nodes["id"].astype(str)
    exp = dict(PCS=meta["n_pcs_drawn"], IDT=meta["n_idt_drawn"])
    got = dict(PCS=int(ids.str.startswith("PCS").sum()), IDT=int(ids.str.startswith("IDT").sum()))
    for k in exp: add("PASS" if exp[k] == got[k] else "FAIL", "Model consistency", f"{k} count", f"design {exp[k]} vs diagram {got[k]}" + ("" if exp[k] == got[k] else ": diagram edited away from calculated design"))
    # Analysis
    if pp and pp.get("ok"):
        vm = pp["bus"]["vm_pu"]; add("PASS" if vm.between(0.95, 1.05).all() else "FAIL", "Analysis", "Bus voltages", f"{vm.min():.3f}-{vm.max():.3f} p.u. ({pp['mode']})")
        tl = pp["trafo"]["loading_percent"].max(); add("PASS" if tl <= 100 else "FAIL", "Analysis", "Transformer loading (load flow)", f"max {tl:.1f}%")
        ik = pp["mv_ikss"]; add("PASS" if ik <= P["vcb_ka"] else "FAIL", "Analysis", "MV bus Ik'' vs VCB rating", f"{ik:.1f} kA vs {P['vcb_ka']:g} kA (grid contribution only)")
        add("WARN", "Analysis", "PCS fault contribution", "Not modelled; Ik'' is grid-only and may be understated")
    else:
        for i in ("Load flow", "Voltage drop", "Short circuit"): add("UNVERIFIED", "Analysis", i, "Run Electrical Analysis")
    add("UNVERIFIED", "Analysis", "Cable loading", "Cables not specified"); add("UNVERIFIED", "Analysis", "Protection coordination", "Needs relay settings; not performed")
    add("UNVERIFIED", "Analysis", "Earthing", "Not assessed"); add("UNVERIFIED", "Analysis", "Dynamic / grid-forming behaviour", "Steady-state tools do not validate this")
    return __import__("pandas").DataFrame(v)
