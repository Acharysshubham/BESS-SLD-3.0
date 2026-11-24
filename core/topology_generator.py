"""Sizing results -> node table (single source of truth for the SLD and the connectivity model)."""
import pandas as pd
from .common import STD_A, STD_MVA, STD_KVA, nxt, amps
from sld.drawing_engine import COLS


def flags(P):
    t = P["ptype"]
    return dict(grid=("Grid" in t or "industrial" in t), pv=P["pv_on"] or "Solar PV" in t, dg=P["dg_on"] or "DG" in t, ind="industrial" in t)


def build_nodes(P, R):
    a = []; add = lambda *r: a.append(dict(zip(COLS, r)))
    F, mv, gk, ch, idt, U = flags(P), P["mv_kv"], P["grid_kv"], R["pcs"], R["idt"], {u["id"]: u for u in R["units"]}
    m = ch["m"]; pv_mw = P["pv_inv_mw"] if F["pv"] else 0.0
    s_tot = ch["s_req"] + pv_mw / 0.95; i_bus = amps(s_tot, mv); bus_a = nxt(1.25 * i_bus, STD_A)
    meta = dict(s_tot=s_tot, i_bus=i_bus, bus_a=bus_a, notes=[], mpt_mva=0.0)
    up = ""
    if F["grid"]:
        add("G", "grid", "Grid / POI", f"{gk:g} kV", f"Isc {P['isc_ka']:g} kA", "", ""); up = "G"
        if P["opt_meter"]: add("MTR", "meter", "Energy meter", "", "", "", up); up = "MTR"
        if abs(gk - mv) > 1e-6:
            mpt = nxt(s_tot, STD_MVA); meta["mpt_mva"] = mpt
            add("HVCB", "breaker", "HV CB", f"{gk:g} kV", f"In {nxt(1.25 * amps(mpt, gk), STD_A)} A", "", up)
            add("MPT", "transformer", "MPT", f"{mpt:g} MVA", f"{gk:g}/{mv:g} kV YNd11", "", "HVCB"); up = "MPT"
        add("MCB", "breaker", "Main CB", f"{mv:g} kV", f"In {bus_a} A", "", up); up = "MCB"
        if P["n_incomers"] > 1: meta["notes"].append(f"{int(P['n_incomers'])} grid incomers specified; one incomer drawn")
    add("MVB", "bus", "MV Bus", f"{mv:g} kV", f"{bus_a} A, {P['isc_ka']:g} kA", "", up)
    if P["opt_arrester"]: add("SA01", "arrester", "Surge arrester", f"{mv:g} kV", "", "", "MVB")
    rows = idt["rows"][: int(P["max_draw"])] if P["max_draw"] > 0 else idt["rows"]
    if len(rows) < len(idt["rows"]): meta["notes"].append(f"Representative drawing: {len(rows)} of {len(idt['rows'])} MV blocks shown")
    pn, seen = 0, {}
    for row in rows if idt["feasible"] else []:
        i = row["idt"]; iv = amps(P["idt_s"], mv)
        add(f"VCB{i:02d}", "breaker", f"VCB-{i:02d}", f"{mv:g} kV", f"In {nxt(1.25 * iv, STD_A)} A", f"I = {iv:.0f} A", "MVB")
        add(f"IDT{i:02d}", "transformer", f"IDT-{i:02d}", f"{P['idt_s']:g} MVA", f"{P['idt_kvp']:g}/{P['idt_kvs']:g} kV {P['idt_vg']}", "", f"VCB{i:02d}")
        for _ in range(row["n_pcs"]):
            pn += 1; il = amps(m["s_mva"], P["pcs_lv_kv"]); par = f"ACB{pn:02d}"
            add(par, "breaker", f"ACB-{pn:02d}", f"{P['pcs_lv_kv']:g} kV", f"In {nxt(1.25 * il, STD_A)} A", f"I = {il:.0f} A", f"IDT{i:02d}")
            add(f"PCS{pn:02d}", "pcs", f"PCS-{pn:02d}", f"{m['p_mw']:g} MW / {m['s_mva']:g} MVA", f"AC {P['pcs_lv_kv']:g} kV", "", par); par = f"PCS{pn:02d}"
            grp = ch["groups"][pn - 1]
            if len(grp) > 1: add(f"CMB{pn:02d}", "combiner", f"DC Combiner-{pn:02d}", f"{len(grp)} inputs", "", "", par); par = f"CMB{pn:02d}"
            for uid, f in grp:
                c, k = U[uid], round(1 / f); seen[uid] = seen.get(uid, 0) + 1
                idc = min(c["p_dc"] * f, m["p_mw"] / m["eff"]) * 1e6 / max(c["vdc_min"], 1)
                add(f"DCCB{pn:02d}_{uid:02d}", "breaker", f"DCCB-{pn:02d}.{uid:02d}", f"{c['vdc_max']:g} V DC", f"In >= {1.25 * idc:.0f} A", f"I = {idc:.0f} A", par)
                add(f"BESS{uid:02d}" + (f"_{seen[uid]}" if k > 1 else ""), "battery", f"BESS-{uid:02d}" + (f" ({seen[uid]}/{k})" if k > 1 else ""),
                    f"{c['mwh'] * f:g} MWh", f"{c['chem']}, {c['vdc_min']:g}-{c['vdc_max']:g} V DC", "", f"DCCB{pn:02d}_{uid:02d}")
    meta["aux_kw"] = R["bess"]["aux_kw"]
    if P["aux_on"]:
        kva = nxt(max(meta["aux_kw"], 1) * 1.25 / 0.9, STD_KVA); meta["aux_kva"] = kva
        add("AUXCB", "breaker", "AUX CB", f"{mv:g} kV", "In 63 A", "", "MVB")
        add("AUXTR", "transformer", "AUX TR", f"{kva:g} kVA", f"{mv:g}/0.415 kV Dyn11", "", "AUXCB")
        add("AUXB", "bus", "LV Aux Bus", "415 V", "", "", "AUXTR")
        add("AUX1", "load", "HVAC / liquid cooling", f"{meta['aux_kw']:.0f} kW", "", "", "AUXB")
        add("AUX2", "load", "Fire detection & suppression", "", "", "", "AUXB"); add("UPS1", "ups", "UPS / DC aux", "", "", "", "AUXB")
        if P["opt_scada"]: add("EMS1", "ems", "SCADA / EMS", "", "", "", "AUXB")
    if F["pv"] and pv_mw > 0:
        add("VCBPV", "breaker", "VCB-PV", f"{mv:g} kV", "", "", "MVB"); add("TRPV", "transformer", "TR-PV", f"{nxt(pv_mw / 0.95, STD_MVA):g} MVA", f"{mv:g}/{P['pv_kv']:g} kV", "", "VCBPV")
        add("PV01", "pv", "PV inverters", f"{int(P['pv_n'])} x {pv_mw / P['pv_n']:.2f} MW", f"{P['pv_mwp']:g} MWp, {P['coupling']}", "", "TRPV")
    if F["dg"]:
        add("VCBDG", "breaker", "VCB-DG", f"{mv:g} kV", "", "", "MVB"); par = "VCBDG"
        if abs(P["dg_kv"] - mv) > 1e-6: add("TRDG", "transformer", "TR-DG", f"{nxt(P['dg_n'] * P['dg_kva'] / 1e3, STD_MVA):g} MVA", f"{mv:g}/{P['dg_kv']:g} kV", "", par); par = "TRDG"
        add("DG01", "generator", f"DG x{int(P['dg_n'])}", f"{P['dg_kva']:g} kVA each", f"{P['dg_kv']:g} kV", "", par)
    if F["ind"] and P["loads"]:
        tot = sum(l["kw"] * l["qty"] for l in P["loads"])
        add("DTR", "transformer", "Dist. TR", f"{nxt(tot * 1.2, STD_KVA):g} kVA", f"{mv:g}/0.415 kV Dyn11", "", "MVB"); add("MDB", "bus", "MDB", "415 V", f"{tot:.0f} kW connected", "", "DTR")
        for n, l in enumerate(P["loads"], 1):
            add(f"FDR{n}", "breaker", f"MCCB-{n}", "", "", "", "MDB"); add(f"LD{n}", "load", l["name"], f"{int(l['qty'])} x {l['kw']:g} kW", "", "", f"FDR{n}")
    meta.update(n_pcs_drawn=pn, n_idt_drawn=len(rows) if idt["feasible"] else 0, notes=meta["notes"])
    return pd.DataFrame(a, columns=COLS), meta
