import copy, json
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from core.defaults import DEFAULTS
from core.pipeline import run
from core.validation_engine import validate
from core.topology_generator import flags
from sld import drawing_engine as D
from analysis.pandapower_model import run as run_pp
from reports.excel_generator import to_excel
from reports.pdf_generator import report_pdf
from reports.equipment_schedule import schedule
import sizing_ui
from core import bess_sizing as SZ

st.set_page_config(page_title="BESS SLD Designer", page_icon="⚡", layout="wide")
ss = st.session_state
if "P" not in ss: ss.P = copy.deepcopy(DEFAULTS); ss.nodes = None; ss.edited = False; ss.pp = None; ss.sig = ""
P = ss.P
STEPS = ["Dashboard", "1 Project", "2a BESS sizing", "2 BESS containers", "3 PCS selection", "4 IDT selection", "5 Electrical equipment", "6 SLD editor", "7 Electrical analysis", "8 Reports & export"]
ICON = {"PASS": "🟢", "WARN": "🟡", "FAIL": "🔴", "UNVERIFIED": "⚪"}


def W(kind, label, k, c=None, **kw):
    """Widget bound to P[k] (state kept in P so moving between steps never loses data)."""
    key = "w_" + k
    if key not in ss: ss[key] = P[k]
    P[k] = getattr(c or st, kind)(label, key=key, **kw); return P[k]


def table(k, cols, key, **kw):
    df = pd.DataFrame(P[k], columns=cols)
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=key, **kw)
    for c in ed.columns: ed[c] = ed[c].fillna("" if ed[c].dtype == object else 0)
    P[k] = ed.to_dict("records"); return ed


def show(df, **kw): st.dataframe(df, hide_index=True, width="stretch", **kw)


def page(html):
    if hasattr(st, "iframe"): st.iframe(html, height=700)
    else: components.html(html, height=700, scrolling=True)


def simplify(df):
    d = df.fillna("").copy(); skip = set(d.id[d.id.str.match(r"^(ACB|DCCB|CMB)")]); par = dict(zip(d.id, d.parent))
    def up(p):
        while p in skip: p = par[p]
        return p
    d = d[~d.id.isin(skip)].copy(); d["parent"] = d.parent.map(up); return d


with st.sidebar:
    st.title("⚡ BESS SLD Designer")
    step = st.radio("Workflow", STEPS, label_visibility="collapsed")
    st.progress(STEPS.index(step) / (len(STEPS) - 1))
    title = st.text_input("Drawing title", f"{P['name']} - Single Line Diagram"); rev = st.text_input("Revision", "A"); by = st.text_input("Drawn by", "")
    detail = st.toggle("Detailed engineering SLD", True); zoom = st.slider("Preview zoom", 0.2, 1.5, 0.5, 0.05)

R = run(P)
if "error" in R: st.error(R["error"]); st.stop()
sig = json.dumps(P, sort_keys=True, default=str)
if ss.sig != sig:
    if ss.edited: ss.stale = True
    else: ss.nodes = R["nodes"]
    ss.sig = sig; ss.pp = None
if ss.nodes is None: ss.nodes = R["nodes"]
nodes = ss.nodes
val = validate(P, R, nodes, ss.pp)
b, ch, idt = R["bess"], R["pcs"], R["idt"]
cnt = val.Status.value_counts().to_dict()
if ss.get("stale") and ss.edited:
    st.warning("Design inputs changed but the diagram has manual edits and was not regenerated.")
    if st.button("Regenerate diagram from design (discard manual edits)"): ss.nodes = R["nodes"]; ss.edited = False; ss.stale = False; st.rerun()

if step == "Dashboard":
    st.header(P["name"])
    c = st.columns(6)
    for col, (l, v) in zip(c, [("Installed energy", f"{b['e_total']:.1f} MWh"), ("DC power", f"{b['p_dis']:.1f} MW"), ("Containers", b["n"]),
                               ("PCS units", ch["n"]), ("IDTs", idt.get("n", 0)), ("MV voltage", f"{P['mv_kv']:g} kV")]): col.metric(l, v)
    st.write(f"**Topology:** {P['ptype']}, {P['coupling']}, {ch['model']} x {ch['n']} ({ch['red']} redundancy), IDT {P['idt_s']:g} MVA {P['idt_kvp']:g}/{P['idt_kvs']:g} kV")
    st.subheader("Validation status"); c = st.columns(4)
    for col, s in zip(c, ICON): col.metric(f"{ICON[s]} {s.title()}", cnt.get(s, 0))
    show(val[val.Status != "PASS"])

elif step == "1 Project":
    c = st.columns(3)
    W("text_input", "Project name", "name", c[0]); W("text_input", "Client", "client", c[1]); W("text_input", "Location", "location", c[2])
    c = st.columns(3)
    W("selectbox", "Project type", "ptype", c[0], options=["BESS only", "Grid + BESS", "Solar PV + BESS", "Grid + Solar PV + BESS", "Grid + DG + BESS", "Solar PV + DG + BESS", "Complete industrial electrical distribution system"])
    W("selectbox", "BESS coupling", "coupling", c[1], options=["AC-coupled", "DC-coupled"])
    W("multiselect", "Applications", "apps", c[2], options=["Energy shifting", "Peak shaving", "Backup", "Frequency regulation", "Voltage regulation", "Renewable integration"])
    c = st.columns(4)
    W("number_input", "System / MV bus voltage (kV)", "mv_kv", c[0], min_value=0.4, max_value=765.0); W("number_input", "Grid connection voltage (kV)", "grid_kv", c[1], min_value=0.4, max_value=765.0)
    W("number_input", "Frequency (Hz)", "f_hz", c[2], min_value=50.0, max_value=60.0, step=10.0)
    if P["coupling"] == "DC-coupled": st.warning("DC-coupled architectures are not yet modelled: the SLD is drawn AC-coupled. DC-DC stages must be added manually.")

elif step == "2a BESS sizing":
    def apply_sizing(r, Z):
        c = r["c"]; yrs = int(Z["years"])
        P["containers"] = [dict(model=c.model, qty=int(r["n"]), mwh=float(c.mwh), chem="LFP", vdc_min=1000.0, vdc_nom=1200.0, vdc_max=1500.0, c_dis=float(c.c_rate), c_chg=float(c.c_rate),
                                dod=Z["dod"] / 100.0, soh_bol=float(r["soh"][1]), soh_eol=float(r["soh"][min(yrs, max(r["soh"]))]), aux_kw=float(c.aux_dis_mw) * 1000.0)]
        for k in ("w_ovr_pdis", "w_ovr_pchg", "ed_c"): ss.pop(k, None)
        P["ovr_pdis"] = P["ovr_pchg"] = 0.0
    sizing_ui.render(st, ss, P, apply_sizing)

elif step == "2 BESS containers":
    st.caption("One row per container model; mix different ratings freely. Illustrative defaults, replace with datasheet values.")
    table("containers", list(DEFAULTS["containers"][0]), "ed_c")
    c = st.columns(2)
    W("number_input", "Override DC discharge power (MW, 0 = from C-rate)", "ovr_pdis", c[0], min_value=0.0); W("number_input", "Override DC charge power (MW, 0 = from C-rate)", "ovr_pchg", c[1], min_value=0.0)
    for o in b["overridden"]: st.warning(f"Manual override active: {o}")
    show(pd.DataFrame([("Installed energy (MWh)", b["e_total"]), ("Usable BOL = E x DoD x SoH_BOL (MWh)", b["e_bol"]), ("Usable EOL (MWh)", b["e_eol"]), ("Max continuous discharge (MW)", b["p_dis"]),
                       ("Max continuous charge (MW)", b["p_chg"]), ("Discharge power from usable BOL / EOL energy (MW)", f"{b['p_dis_bol']:.2f} / {b['p_dis_eol']:.2f}"), ("Duration at rated power (h)", round(b["duration_h"], 2)), ("Container auxiliary (kW)", b["aux_kw"])], columns=["Item", "Value"]).astype(str))

elif step == "3 PCS selection":
    c = st.columns(4)
    W("selectbox", "Architecture", "pcs_arch", c[0], options=["Central PCS", "String PCS", "Modular PCS"]); W("number_input", "PCS AC voltage (kV)", "pcs_lv_kv", c[1], min_value=0.2, max_value=3.3, format="%.3f")
    W("number_input", "Required PF at full P", "pcs_pf", c[2], min_value=0.5, max_value=1.0, step=0.01); W("number_input", "Reactive power (MVAr, 0 = by PF)", "pcs_q", c[3], min_value=0.0)
    c = st.columns(5)
    W("number_input", "Target AC power (MW, 0 = battery x eff)", "pcs_ptarget", c[0], min_value=0.0); W("selectbox", "Redundancy", "pcs_red", c[1], options=["None", "N+1", "User"])
    W("number_input", "User spare PCS", "pcs_spare", c[2], min_value=0, max_value=20); W("number_input", "Max PCS loading (fraction)", "pcs_maxload", c[3], min_value=0.5, max_value=1.0, step=0.05); W("number_input", "Temperature derate (fraction)", "pcs_derate", c[4], min_value=0.5, max_value=1.0, step=0.05)
    with st.expander("PCS equipment catalogue (illustrative values)", expanded=False):
        up = st.file_uploader("Import catalogue (.xlsx with the same columns)", type="xlsx")
        if up and ss.get("pcs_up") != up.name:
            P["pcs_cat"] = pd.read_excel(up).to_dict("records"); ss.pcs_up = up.name; st.rerun()
        table("pcs_cat", list(DEFAULTS["pcs_cat"][0]), "ed_p")
    st.subheader("Feasible configurations"); show(R["pcs_table"])
    fig = px.bar(R["pcs_table"], x="Config", y="Installed MVA", color="Redundancy", text="Installed", title="Installed PCS capacity by configuration"); st.plotly_chart(fig, width="stretch")
    c = st.columns(2); W("selectbox", "Adopt configuration", "pcs_choice", c[0], options=list(R["picks"])); W("number_input", "Manual PCS count (0 = automatic)", "pcs_nover", c[1], min_value=0, max_value=500)
    why = {"Minimum cost": "lowest installed PCS capacity; may need DC paralleling that requires manufacturer confirmation",
           "Balanced": "lowest installed capacity among options that need no extra DC paralleling approval, preferring whole container:PCS ratios",
           "High reliability": "one spare unit of the smallest PCS, so one failure removes the least capacity"}[P["pcs_choice"]]
    st.info(f"**{P['pcs_choice']}**: {ch['n']} x {ch['model']} ({ch['n_op']} operating + {ch['spare']} spare). {why}. Loading {ch['loading']:.1f}%, capacity after one failure {ch['after_fail']:.2f} MVA vs {ch['s_req']:.2f} MVA required.")
    st.caption(f"AC power {ch['p_ac']:.2f} MW and apparent power {ch['s_req']:.2f} MVA are distinct from battery DC power {b['p_dis']:.2f} MW. Count by MVA: {ch['n_by_s']}, by MW: {ch['n_by_p']}.")
    show(pd.DataFrame([dict(PCS=f"PCS-{i + 1:02d}", Containers=", ".join(f"BESS-{u:02d}" + ("" if f == 1 else f" ({f:.2f})") for u, f in g), Status=ICON[__import__("core.common", fromlist=["worst"]).worst([x[0] for x in d])]) for i, (g, d) in enumerate(zip(ch["groups"], ch["dc"]))]))
    show(val[val.Category == "DC compatibility"][["Status", "Check", "Detail"]])

elif step == "4 IDT selection":
    c = st.columns(4)
    W("number_input", "IDT rating (MVA)", "idt_s", c[0], min_value=0.1); W("number_input", "Primary kV", "idt_kvp", c[1], min_value=1.0); W("number_input", "Secondary kV", "idt_kvs", c[2], min_value=0.2, format="%.3f")
    wt = c[3].selectbox("Winding arrangement", ["Two-winding (1 LV)", "Three-winding (2 LV)", "Five-winding (4 LV)", "Custom"], index={1: 0, 2: 1, 4: 2}.get(int(P["idt_nlv"]), 3))
    if wt != "Custom": P["idt_nlv"] = {"Two-winding (1 LV)": 1, "Three-winding (2 LV)": 2, "Five-winding (4 LV)": 4}[wt]
    else: W("number_input", "Number of LV windings", "idt_nlv", c[3], min_value=1, max_value=12)
    c = st.columns(5)
    W("number_input", "PCS per LV winding", "idt_ppw", c[0], min_value=1, max_value=4); W("text_input", "Vector group", "idt_vg", c[1]); W("number_input", "Impedance (%)", "idt_z", c[2], min_value=0.0)
    W("number_input", "Loading limit (fraction)", "idt_lim", c[3], min_value=0.5, max_value=1.0, step=0.05); W("number_input", "Ambient derate (fraction)", "idt_derate", c[4], min_value=0.5, max_value=1.0, step=0.05)
    c = st.columns(3); W("selectbox", "Cooling", "idt_cool", c[0], options=["ONAN", "ONAF", "KNAN", "Dry"]); W("number_input", "Efficiency (%)", "idt_eff", c[1], min_value=90.0, max_value=100.0); W("number_input", "Spare IDTs", "idt_spare", c[2], min_value=0, max_value=5)
    st.write(f"Total PCS {idt['s_total']:.2f} MVA. Capacity-only estimate: **{idt['n_prelim']}** IDT. Limits: thermal {idt['k_thermal']} PCS, windings {idt['k_winding']} PCS per IDT.")
    if idt["feasible"]: st.success(f"{idt['n']} IDT required."); show(pd.DataFrame(idt["rows"]).round(2))
    else: st.error("No feasible arrangement: the PCS does not fit the IDT.")

elif step == "5 Electrical equipment":
    F = flags(P)
    st.subheader("Grid interconnection"); c = st.columns(4)
    W("number_input", "Grid fault level (kA)", "isc_ka", c[0], min_value=0.0); W("number_input", "MV VCB breaking capacity (kA)", "vcb_ka", c[1], min_value=1.0); W("number_input", "Grid incomers", "n_incomers", c[2], min_value=1, max_value=4); W("number_input", "Export limit (MW, 0 = none)", "p_export", c[3], min_value=0.0)
    st.subheader("Auxiliary systems and options"); c = st.columns(4)
    W("checkbox", "Auxiliary transformer / LV aux bus", "aux_on", c[0]); W("checkbox", "Energy meter at POI", "opt_meter", c[1]); W("checkbox", "Surge arresters", "opt_arrester", c[2]); W("checkbox", "SCADA / EMS", "opt_scada", c[3])
    W("number_input", "Max MV blocks drawn (0 = all)", "max_draw", None, min_value=0, max_value=500)
    c = st.columns(2)
    with c[0]:
        st.subheader("Solar PV"); W("checkbox", "Include PV (also set by project type)", "pv_on")
        if F["pv"]:
            W("number_input", "PV DC capacity (MWp)", "pv_mwp", min_value=0.0); W("number_input", "Inverter AC capacity (MW)", "pv_inv_mw", min_value=0.0); W("number_input", "Number of inverters", "pv_n", min_value=1, max_value=500); W("number_input", "Inverter voltage (kV)", "pv_kv", min_value=0.2, format="%.3f")
    with c[1]:
        st.subheader("Diesel generators"); W("checkbox", "Include DG (also set by project type)", "dg_on")
        if F["dg"]:
            W("number_input", "Number of DG sets", "dg_n", min_value=1, max_value=50); W("number_input", "Rating each (kVA)", "dg_kva", min_value=10.0); W("number_input", "DG voltage (kV)", "dg_kv", min_value=0.2, format="%.3f")
    if F["ind"]: st.subheader("Industrial loads"); table("loads", ["name", "kw", "qty"], "ed_l")
    st.caption("Not yet modelled: DC combiner/cable sizing, RMUs, CT/PT/relay symbols, station transformer and multiple incomers. Add manually in the SLD editor.")

elif step == "6 SLD editor":
    st.caption("Each row is a device; `parent` is the feeding device. Layout is automatic. Edits update the network model used by the checks; a mismatch with the calculated design is flagged as FAIL.")
    c = st.columns(3)
    if c[0].button("Regenerate from design"): ss.nodes = R["nodes"]; ss.edited = False; ss.stale = False; st.rerun()
    ed = st.data_editor(ss.nodes, num_rows="dynamic", hide_index=True, width="stretch", key="ed_n", column_config={"type": st.column_config.SelectboxColumn(options=D.TYPES, required=True)}).fillna("")
    if not ed.equals(ss.nodes): ss.nodes = ed; ss.edited = True; st.rerun()
    view = nodes if detail else simplify(nodes)
    pr, Wd, Hd = D.primitives(view, title, R["meta"]["notes"], rev, by)
    page(f'<div style="overflow:auto;background:#fff">{D.to_svg(pr, Wd, Hd, zoom)}</div>')
    for m in val[val.Category.isin(["Connectivity", "Model consistency"]) & (val.Status != "PASS")].Detail: st.warning(m)
    st.caption("Drag-and-drop canvas, symbol rotation, undo/redo and multi-sheet drawings are not in this version.")

elif step == "7 Electrical analysis":
    mode = st.radio("Operating mode", ["discharge", "charge"], horizontal=True)
    if st.button("Run load flow and short circuit", type="primary"): ss.pp = run_pp(P, R, mode); st.rerun()
    pp = ss.pp
    if pp and pp.get("ok"):
        st.success(f"Converged ({pp['mode']}). MV bus Ik'' = {pp['mv_ikss']:.1f} kA (grid contribution only)")
        show(pp["bus"].round(4)); show(pp["trafo"].round(3)); show(pp["sc"].round(3))
        st.plotly_chart(px.bar(pp["bus"], x="name", y="vm_pu", title="Bus voltage (p.u.)"), width="stretch")
        for a in pp["assumptions"]: st.caption("- " + a)
    elif pp: st.error(pp.get("error"))
    c = st.columns(4)
    for col, s in zip(c, ICON): col.metric(f"{ICON[s]} {s.title()}", cnt.get(s, 0))
    show(val)
    st.caption("Steady-state results only. They do not validate protection coordination, transient behaviour or grid-forming performance.")

else:
    pr, Wd, Hd = D.primitives(nodes if detail else simplify(nodes), title, R["meta"]["notes"], rev, by)
    pj = json.dumps(dict(P=P, nodes=nodes.to_dict("records")), default=str)
    c = st.columns(4)
    c[0].download_button("SLD (PDF)", D.to_pdf(pr, Wd, Hd), "sld.pdf"); c[1].download_button("SLD (PNG)", D.to_png(pr, Wd, Hd, 2), "sld.png")
    c[2].download_button("SLD (SVG)", D.to_svg(pr, Wd, Hd), "sld.svg"); c[3].download_button("Project (JSON)", pj, "project.json")
    c = st.columns(3)
    c[0].download_button("Excel: sizing, schedule, validation", to_excel(P, R, nodes, val), "bess_design.xlsx"); c[1].download_button("Engineering report (PDF)", report_pdf(P, R, nodes, val), "report.pdf")
    c[2].download_button("Configuration only (JSON)", json.dumps(P, default=str), "config.json")
    if "db" in ss:
        _z = {**SZ.SZ, **P.get("sz", {})}
        try: st.download_button("BESS sizing workbook (Excel)", SZ.to_excel(SZ.run_all(ss.db, _z), _z), "bess_sizing.xlsx")
        except Exception as ex: st.caption(f"Sizing workbook unavailable: {ex}")
    up = st.file_uploader("Open project JSON", type="json")
    if up and ss.get("loaded") != up.name:
        d = json.loads(up.read()); ss.P = {**copy.deepcopy(DEFAULTS), **d.get("P", d)}
        for k in [k for k in ss if k.startswith("w_")]: del ss[k]
        ss.nodes = pd.DataFrame(d["nodes"], columns=D.COLS) if "nodes" in d else None; ss.edited = "nodes" in d; ss.loaded = up.name; ss.sig = ""; st.rerun()
    st.subheader("Equipment schedule"); show(schedule(nodes))
