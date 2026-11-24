"""BESS sizing engine (energy / power / both), database-driven. No Streamlit imports: fully testable.

Database = .xlsx with sheets  Containers | SOH | Calendar  (see template_db()).
All percentages are entered/stored as percent numbers (98.5 = 98.5 %), converted to factors inside.
"""
import io, math, re
import numpy as np
import pandas as pd

AUTO = "Auto (nearest C-rate)"
BAND = (14.0, 20.0)      # target oversizing band (%) on required BOL energy
SEARCH_MAX = 60.0        # search beyond the band only if the band cannot meet the requirement (flagged)

SZ = dict(  # sizing inputs (kept in P["sz"])
    fulfil="Energy", e_mwh=100.0, p_mw=50.0, basis="BOL only", e_bol=100.0, e_eol=80.0,
    time_mode="C-rate", c_rate=0.5, t_h=2.0, mm_mode="Same every year", mm_const=1.0,
    temp=25.0, avail=98.0, min_rte=84.0, years=10, cycles=365, dod=95.0, poi_kv=33.0, lv_stages=2,
    aux_on=True, extra_aux_on=False, extra_aux=0.0, standby_on=False, standby=0.0, var_rte_on=False,
    fatsat_on=False, fatsat_m=3, fat_soh=100.0, fat_cal=100.0, model_pick=AUTO,
    soh_scale=100.0, dcrte_delta=0.0, ytab=[], aug_on=False, aug_tbl=[], eff={})

# ------------------------------------------------------------------ database
def norm(s): return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


ALIAS = {"container": "model", "dc_installed_capacity_per_container_mwh": "mwh", "capacity_mwh": "mwh", "crate": "c_rate",
         "auxiliary_consumption_per_container_discharge_mw": "aux_dis_mw", "auxiliary_consumption_per_container_charge_mw": "aux_chg_mw",
         "lv_dc_ac_cable_efficiency": "lv_cable_eff", "pcs_efficiency_discharging": "pcs_eff_dis", "pcs_efficiency_charging": "pcs_eff_chg",
         "transformer_efficiency_discharging": "trafo_eff_dis", "transformer_efficiency_charging": "trafo_eff_chg",
         "hv_transformer": "hv_transformer_eff", "hv_cable": "hv_cable_eff", "measurement_error": "meas_error", "soh_pct": "soh", "soh_percent": "soh"}
REQ_C = ["model", "mwh", "c_rate", "aux_dis_mw", "aux_chg_mw", "dc_rte", "lv_cable_eff", "pcs_eff_dis", "trafo_eff_dis", "hv_transformer_eff", "hv_cable_eff", "meas_error"]
EFF_COLS = ["dc_rte", "dc_dc_rte", "lv_cable_eff", "pcs_eff_dis", "pcs_eff_chg", "trafo_eff_dis", "trafo_eff_chg", "hv_transformer_eff", "hv_cable_eff", "dc_db_eff"]


def _cols(df): return df.rename(columns=lambda c: ALIAS.get(norm(c), norm(c)))


def _pct(s):  # fractions (<=1) -> percent
    s = pd.to_numeric(s, errors="coerce"); return s.where(s > 1.0, s * 100.0)


def load_db(src):
    """Read and validate the product database. Raises ValueError with a readable message."""
    sh = {norm(k): _cols(v) for k, v in pd.read_excel(src, sheet_name=None).items()}
    for k in ("containers", "soh", "calendar"):
        if k not in sh: raise ValueError(f"Sheet '{k}' not found. Found: {list(sh)}")
    c = sh["containers"].dropna(subset=["model"]).copy()
    miss = [x for x in REQ_C if x not in c]
    if miss: raise ValueError(f"Containers sheet is missing columns: {miss}")
    for k, d in (("pcs_eff_chg", "pcs_eff_dis"), ("trafo_eff_chg", "trafo_eff_dis"), ("dc_dc_rte", "dc_rte")):
        if k not in c: c[k] = c[d]
    if "dc_db_eff" not in c: c["dc_db_eff"] = 100.0
    for k in EFF_COLS: c[k] = _pct(c[k])
    for k in ("mwh", "c_rate", "aux_dis_mw", "aux_chg_mw", "meas_error"): c[k] = pd.to_numeric(c[k], errors="coerce")
    c["model"] = c["model"].astype(str)
    if c[REQ_C[1:]].isna().any().any(): raise ValueError("Containers sheet has empty or non-numeric cells in required columns.")
    soh = sh["soh"].dropna(subset=["model", "year"]).copy(); soh["model"] = soh["model"].astype(str)
    if "soh" not in soh: raise ValueError("SOH sheet needs columns: model, year, soh")
    soh["soh"] = _pct(soh["soh"])
    cal = sh["calendar"].dropna(subset=["temp_min", "temp_max"]).copy(); cal["model"] = cal.get("model", "*").fillna("*").astype(str)
    cc = [x for x in cal if x.startswith("cal_")]
    if not cc: raise ValueError("Calendar sheet needs one or more columns starting with 'cal_' (degradation %)")
    cal["loss"] = cal[cc].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    return dict(cont=c.reset_index(drop=True), soh=soh, cal=cal)


def soh_curve(db, model, N, cycles=None):
    d = db["soh"]; d = d[d.model.isin([model, "*"])]
    if d.empty: raise ValueError(f"No SOH rows for {model}")
    if "cycles_per_year" in d and d["cycles_per_year"].notna().any() and cycles:
        k = d.loc[(d["cycles_per_year"] - cycles).abs().idxmin(), "cycles_per_year"]; d = d[d["cycles_per_year"] == k]
    d = d.sort_values("year"); y = d["year"].astype(float).values; v = d["soh"].values
    return {i: float(np.interp(i, y, v)) / 100.0 for i in range(1, max(int(N), int(y.max())) + 1)}


def cal_factor(db, model, temp):
    d = db["cal"]; d = d[d.model.isin([model, "*"])]
    hit = d[(d.temp_min <= temp) & (temp <= d.temp_max)]; note = ""
    if hit.empty:
        mid = (d.temp_min + d.temp_max) / 2; hit = d.loc[[(mid - temp).abs().idxmin()]]
        note = f"{temp:g} °C is outside the database ranges; nearest range {hit.temp_min.iloc[0]:g}-{hit.temp_max.iloc[0]:g} °C used."
    return 1 - float(hit["loss"].iloc[0]) / 100.0, note


def sample_db():
    """Illustrative database (NOT manufacturer data). Two 0.5C containers deliberately tie to demonstrate dual sizing."""
    base = dict(dc_rte=94.0, lv_cable_eff=99.5, pcs_eff_dis=98.5, pcs_eff_chg=98.5, trafo_eff_dis=99.0, trafo_eff_chg=99.0,
                hv_transformer_eff=99.7, hv_cable_eff=99.8, meas_error=0.2, dc_db_eff=100.0)
    rows = [dict(model="Sample-5.0MWh-0.5C", mwh=5.015, c_rate=0.5, aux_dis_mw=0.030, aux_chg_mw=0.025, **base),
            dict(model="Sample-5.5MWh-0.5C", mwh=5.504, c_rate=0.5, aux_dis_mw=0.033, aux_chg_mw=0.028, **{**base, "dc_rte": 95.0}),
            dict(model="Sample-3.7MWh-0.25C", mwh=3.727, c_rate=0.25, aux_dis_mw=0.022, aux_chg_mw=0.018, **{**base, "dc_rte": 96.0}),
            dict(model="Sample-4.2MWh-1C", mwh=4.2, c_rate=1.0, aux_dis_mw=0.045, aux_chg_mw=0.040, **{**base, "dc_rte": 92.0})]
    c = pd.DataFrame(rows); c["dc_dc_rte"] = c["dc_rte"]
    soh = pd.DataFrame([dict(model="*", year=y, soh=round(100 - 2.0 * y, 2)) for y in range(1, 26)])
    cal = pd.DataFrame([dict(model="*", temp_min=a, temp_max=b, cal_storage=s, cal_ageing=g)
                        for a, b, s, g in [(-50, 15, 1.0, 0.5), (15, 25, 1.5, 0.8), (25, 35, 2.5, 1.2), (35, 45, 4.0, 2.0), (45, 80, 6.0, 3.0)]])
    return dict(cont=c, soh=soh, cal=cal.assign(loss=cal.cal_storage + cal.cal_ageing))


def template_db(db=None):
    db = db or sample_db(); buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        db["cont"].to_excel(w, sheet_name="Containers", index=False); db["soh"].to_excel(w, sheet_name="SOH", index=False)
        db["cal"].drop(columns=["loss"], errors="ignore").to_excel(w, sheet_name="Calendar", index=False)
        pd.DataFrame({"Notes": ["ILLUSTRATIVE values: replace with the product-team data.",
                                "Containers: one row per model. Efficiencies and dc_rte in %. meas_error in % (factor = 1 - error).",
                                "hv_transformer_eff feeds 'MV cable & MV switchgear'; hv_cable_eff feeds the interconnecting-point cable.",
                                "Optional columns: pcs_eff_chg, trafo_eff_chg, dc_dc_rte, dc_db_eff (default to discharge / 100 %).",
                                "SOH: model ('*' = all), year, soh (%), optional cycles_per_year.",
                                "Calendar: model ('*' = all), temp_min, temp_max (deg C), then any columns starting cal_ (%); they are summed and 100 - sum is the factor held for all years."]}
                     ).to_excel(w, sheet_name="Notes", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = min(60, max(10, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()


# ------------------------------------------------------------------ inputs -> numbers
def duration(sz): return 1.0 / sz["c_rate"] if sz["time_mode"] == "C-rate" else sz["t_h"]
def c_user(sz): return sz["c_rate"] if sz["time_mode"] == "C-rate" else 1.0 / sz["t_h"]


def candidates(db, sz):
    c = db["cont"]
    if sz["model_pick"] != AUTO and sz["model_pick"] in set(c.model): return c[c.model == sz["model_pick"]]
    d = (c.c_rate - c_user(sz)).abs(); return c[d <= d.min() + 1e-9]   # ties -> several containers, each sized


def eff_defaults(c):
    return dict(lv=c.lv_cable_eff, pcs_d=c.pcs_eff_dis, pcs_c=c.pcs_eff_chg, idt_d=c.trafo_eff_dis, idt_c=c.trafo_eff_chg, mv=c.hv_transformer_eff,
                mpt_d=c.trafo_eff_dis, mpt_c=c.trafo_eff_chg, hv=c.hv_cable_eff, meas=c.meas_error, db=c.dc_db_eff)


def eff_fields(poi_kv):
    """AC efficiencies asked from the user depend on the POI voltage (<=33 kV: no MV switchgear / main transformer)."""
    f = [("lv", "LV cable (DC & PCS-IDT) %"), ("pcs_d", "PCS discharge %"), ("pcs_c", "PCS charge %"), ("idt_d", "IDT discharge %"), ("idt_c", "IDT charge %")]
    if poi_kv > 33: f += [("mv", "MV cable & switchgear %"), ("mpt_d", "Main transformer discharge %"), ("mpt_c", "Main transformer charge %")]
    return f + [("hv", "Interconnecting-point cable %"), ("meas", "Measurement error %"), ("db", "DC DB %")]


def chain(e, sz, mode):
    d = mode == "dis"; f = lambda k: e[k] / 100.0
    p = f("lv") ** int(sz["lv_stages"]) * f("pcs_d" if d else "pcs_c") * f("idt_d" if d else "idt_c") * f("hv") * (1 - e["meas"] / 100.0) * f("db")
    if sz["poi_kv"] > 33: p *= f("mv") * f("mpt_d" if d else "mpt_c")
    return p


def ref_energy(sz):
    """(BOL, EOL) required energy. BOL only -> EOL = 80 % BOL; EOL only -> BOL = 125 % EOL."""
    E = sz["e_mwh"]; b = sz["basis"]
    if b == "BOL only": return E, 0.8 * E
    if b == "EOL only": return 1.25 * E, E
    if b == "BOL and EOL": return sz["e_bol"], sz["e_eol"]
    return E, E


def ytab(sz):
    N = int(sz["years"]); old = {r["year"]: r for r in sz.get("ytab", [])}
    return {y: {"mismatch_pct": sz["mm_const"], "dcdc_rte_pct": 0.0, "pct_of_req": 100.0, "req_energy_mwh": 0.0, "req_power_mw": 0.0, "plant_mw": 0.0, **old.get(y, {})}
            for y in range(1, N + 1)}


def req_energy(sz, y):
    r = ytab(sz)[y]
    if r["req_energy_mwh"] > 0: return r["req_energy_mwh"]
    bol, eol = ref_energy(sz); N = int(sz["years"])
    if sz["basis"] == "Percentage per year": return sz["e_mwh"] * r["pct_of_req"] / 100.0
    return bol if N == 1 else bol + (eol - bol) * (y - 1) / (N - 1)


# ------------------------------------------------------------------ calculation
def evaluate(c, sz, e, n, soh, cal, aug_rows=None):
    """Year-by-year discharge / charge / RTE / power table for n initial containers plus augmentation rows [(year, k)]."""
    N = int(sz["years"]); t = duration(sz); yt = ytab(sz); aug = [(int(a["year"]), int(a["containers"])) for a in (aug_rows or []) if a.get("containers", 0) > 0]
    dc_rte = c.dc_rte + sz["dcrte_delta"]; dce = math.sqrt(max(dc_rte, 0) / 100.0); chd, chc = chain(e, sz, "dis"), chain(e, sz, "chg")
    ad, ac = (c.aux_dis_mw, c.aux_chg_mw) if sz["aux_on"] else (0.0, 0.0)
    extra = (sz["extra_aux"] if sz["extra_aux_on"] else 0.0) + (sz["standby"] if sz["standby_on"] else 0.0)
    scale = sz["soh_scale"] / 100.0; av = sz["avail"] / 100.0; dod = sz["dod"] / 100.0
    rows = []
    for y in ([0] if sz["fatsat_on"] else []) + list(range(1, N + 1)):
        r = yt.get(y, {}); mm = (sz["mm_const"] if sz["mm_mode"] == "Same every year" else r.get("mismatch_pct", sz["mm_const"])) / 100.0
        rte = ((r.get("dcdc_rte_pct", 0) or 0) if sz["var_rte_on"] else 0) or (c.dc_dc_rte + sz["dcrte_delta"]); rte /= 100.0
        s_of = (lambda age: sz["fat_soh"] / 100.0) if y == 0 else (lambda age: min(1.0, soh[min(age, max(soh))] * scale))
        cf = sz["fat_cal"] / 100.0 if y == 0 else cal
        dc = lambda k, age: k * c.mwh * av * dce * s_of(age) * cf * dod * (1 - mm)
        dcb = dc(n, max(y, 1)); na = sum(k for a, k in aug if a <= y and y > 0)
        dca = sum(dc(k, y - a + 1) for a, k in aug if a <= y and y > 0)
        plant = r.get("plant_mw", 0.0) or 0.0
        dis_b = dcb * chd; aux_b = n * ad * t + extra; inc_b = dis_b - aux_b
        aug_dis = dca * chd - na * ad * t
        chg_b = dcb / (chc * rte); aux_cb = n * ac * t; chi_b = chg_b + aux_cb
        aug_chg = dca / (chc * rte) + na * ac * t
        tot_d = inc_b + aug_dis - plant * t; tot_c = chi_b + aug_chg + plant * t
        rte_ex = (dis_b + dca * chd) / (chg_b + dca / (chc * rte)); rte_in = (inc_b + aug_dis) / (chi_b + aug_chg)
        pw = (n + na) * c.mwh * c.c_rate * av * dce * chd - (n + na) * ad
        req_e = req_energy(sz, y) if y > 0 else np.nan
        req_p = (r.get("req_power_mw", 0) or sz["p_mw"]) if y > 0 else np.nan
        rows.append({"Year": y if y else "FAT/SAT", "Containers": n + na, "Installed DC (MWh)": (n + na) * c.mwh, "Availability %": sz["avail"], "DC discharge eff %": dce * 100,
                     "SOH %": s_of(max(y, 1)) * 100, "Calendar %": cf * 100, "Mismatch %": mm * 100, "DOD %": sz["dod"],
                     "DC discharge cap (MWh)": dcb + dca, "POI excl aux (MWh)": dis_b + dca * chd, "Aux energy dis (MWh)": aux_b + na * ad * t,
                     "POI incl aux (MWh)": inc_b, "Augmented energy (MWh)": aug_dis, "Plant infra (MW)": plant, "AC MV energy dis (MWh)": tot_d,
                     "Required energy (MWh)": req_e, "Energy": _m(tot_d, req_e),
                     "DC charge cap (MWh)": dcb + dca, "DC-DC RTE %": rte * 100, "POI chg excl aux (MWh)": chg_b + dca / (chc * rte), "Aux energy chg (MWh)": aux_cb + na * ac * t,
                     "POI chg incl aux (MWh)": chi_b, "Augmented chg energy (MWh)": aug_chg, "AC MV energy chg (MWh)": tot_c,
                     "RTE excl aux %": rte_ex * 100, "RTE incl aux %": rte_in * 100, "AC RTE (AC MV) %": tot_d / tot_c * 100,
                     "POI power net (MW)": pw, "Required power (MW)": req_p, "Power": _m(pw, req_p)})
    df = pd.DataFrame(rows)
    df["RTE"] = ["—"] * len(df); last = len(df) - 1
    df.loc[last, "RTE"] = "MATCHED" if df.loc[last, "RTE incl aux %"] >= sz["min_rte"] - 1e-9 else "NOT MATCHED"
    return df


def _m(v, req):
    if req is None or (isinstance(req, float) and math.isnan(req)): return "—"
    return "MATCHED" if v >= req - 1e-9 else "NOT MATCHED"


def passes(df, sz, rte=True):
    ok = (df["RTE"].iloc[-1] == "MATCHED") if rte else True
    if sz["fulfil"] in ("Energy", "Both"): ok &= (df["Energy"] != "NOT MATCHED").all()
    if sz["fulfil"] in ("Power", "Both"): ok &= (df["Power"] != "NOT MATCHED").all()
    return bool(ok)


def auto_size(c, sz, e, soh, cal):
    """Pick n. Energy: smallest oversizing (14-20 % band first) on required BOL energy that meets every year + EOL RTE. Power: ceil(P / container POI power)."""
    aug = sz["aug_tbl"] if sz["aug_on"] else []
    one = evaluate(c, sz, e, 1, soh, cal)   # per-container POI power
    p1 = one["POI power net (MW)"].iloc[-1]; n_p = math.ceil(round(sz["p_mw"] / p1, 6)) if sz["fulfil"] in ("Power", "Both") and p1 > 0 else 0
    bol, _ = ref_energy(sz); res = dict(n_power=n_p, n_energy=0, band_ok=True, found=True)
    if sz["fulfil"] == "Power":
        n = max(n_p, 1); df = evaluate(c, sz, e, n, soh, cal, aug); return {**res, "n": n, "x": None, "df": df, "ok": passes(df, sz)}
    x = BAND[0]
    while x <= SEARCH_MAX + 1e-9:
        n = max(math.ceil(round(bol * (1 + x / 100) / c.mwh, 6)), n_p, 1); df = evaluate(c, sz, e, n, soh, cal, aug)
        if passes(df, sz, rte=False): break   # RTE is nearly independent of n, so it is checked and reported, not searched
        x += 0.5
    else:
        res["found"] = False
    act = (n * c.mwh / bol - 1) * 100 if bol else 0.0
    return {**res, "n": n, "n_energy": math.ceil(round(bol * (1 + x / 100) / c.mwh, 6)), "x": x, "x_actual": act, "df": df, "ok": passes(df, sz),
            "band_ok": BAND[0] - 1e-9 <= x <= BAND[1] + 1e-9 and res["found"]}


def run_all(db, sz):
    out = {}
    for _, c in candidates(db, sz).iterrows():
        e = {**eff_defaults(c), **sz.get("eff", {}).get(c.model, {})}; cal, note = cal_factor(db, c.model, sz["temp"])
        soh = soh_curve(db, c.model, sz["years"] + 1, sz["cycles"])
        out[c.model] = dict(c=c, e=e, soh=soh, cal=cal, note=note, **auto_size(c, sz, e, soh, cal))
    return out


def metrics(r, sz, df=None):
    df = r["df"] if df is None else df; y1, yl = df[df.Year != "FAT/SAT"].iloc[0], df.iloc[-1]; c = r["c"]
    marg = (df["AC MV energy dis (MWh)"] - df["Required energy (MWh)"]).dropna()
    return {"Containers (nos.)": int(y1["Containers"]), "Initial installed DC (MWh)": y1["Installed DC (MWh)"],
            "Year-1 DC discharge cap (MWh)": y1["DC discharge cap (MWh)"], "Year-1 POI energy incl aux (MWh)": y1["POI incl aux (MWh)"],
            "Final-year POI energy incl aux (MWh)": yl["POI incl aux (MWh)"], "Final-year AC MV energy (MWh)": yl["AC MV energy dis (MWh)"],
            "Aux energy / cycle, year 1 (MWh)": y1["Aux energy dis (MWh)"], "Final-year RTE excl aux (%)": yl["RTE excl aux %"], "Final-year RTE incl aux (%)": yl["RTE incl aux %"],
            "Final-year POI power (MW)": yl["POI power net (MW)"], "Worst-year energy margin (MWh)": float(marg.min()) if len(marg) else float("nan"),
            "All requirements met": "YES" if passes(df, sz) else "NO"}


def whatif(db, sz, model, change):
    """Before / after (same containers) and before / after (re-sized) for a parameter change."""
    base = run_all(db, sz).get(model); s2 = {**sz, **change}
    c = base["c"]; e = base["e"]; cal, _ = cal_factor(db, model, s2["temp"]); soh = soh_curve(db, model, s2["years"] + 1, s2["cycles"])
    aug = s2["aug_tbl"] if s2["aug_on"] else []
    n0 = base["n"]; fixed = evaluate(c, s2, e, n0, soh, cal, aug); re_ = {"c": c, **auto_size(c, s2, e, soh, cal)}
    return dict(before=metrics(base, sz), fixed=metrics(base, s2, fixed), resized=metrics(re_, s2), n0=n0, n1=re_["n"], base=base, resized_res=re_)


NOTES = {
    "dod": "DOD scales usable DC energy linearly on both charge and discharge paths. A lower DOD lowers cycle stress but needs more containers for the same POI energy, which also raises auxiliary load. RTE moves only slightly: the DC/AC chain multiplies both directions equally, so only the fixed auxiliary share changes.",
    "avail": "BESS availability derates installed capacity (out-of-service racks/containers). It scales DC and POI energy and power directly and leaves efficiency ratios unchanged; the cost shows up as extra containers or a guarantee shortfall.",
    "temp": "Operating temperature selects the calendar-degradation band in the database. The factor is held constant for the contract, so the effect is a flat shift in capacity every year; it is not a faster fade, which is carried by the SOH curve.",
    "soh_scale": "The SOH multiplier scales the fade curve. A lower SOH reduces the end-of-life guaranteed capacity the most, so it drives the oversizing and the augmentation requirement.",
    "dcrte_delta": "DC RTE enters twice: its square root derates discharge, and the full value divides the charge energy. A drop of a few points therefore hits RTE roughly twice as hard as discharge capacity.",
    "mm_const": "Mismatch losses reduce usable DC energy in the years they apply. When they vary by year, the late years usually set the oversizing.",
}


def explain(param, w, sz):
    b, f, r = w["before"], w["fixed"], w["resized"]; L = []
    pct = lambda a, z: (z / a - 1) * 100 if a else 0.0
    L.append(NOTES.get(param, ""))
    L.append(f"**Complete system (installed DC):** {b['Initial installed DC (MWh)']:.1f} MWh with {w['n0']} containers → re-sized {r['Initial installed DC (MWh)']:.1f} MWh with {w['n1']} containers ({w['n1'] - w['n0']:+d}).")
    L.append(f"**DC side:** year-1 DC discharge capacity {b['Year-1 DC discharge cap (MWh)']:.2f} → {f['Year-1 DC discharge cap (MWh)']:.2f} MWh ({pct(b['Year-1 DC discharge cap (MWh)'], f['Year-1 DC discharge cap (MWh)']):+.1f} %) with the existing containers.")
    L.append(f"**AC side / guaranteed capacity:** final-year POI energy incl aux {b['Final-year POI energy incl aux (MWh)']:.2f} → {f['Final-year POI energy incl aux (MWh)']:.2f} MWh ({pct(b['Final-year POI energy incl aux (MWh)'], f['Final-year POI energy incl aux (MWh)']):+.1f} %); worst-year margin {b['Worst-year energy margin (MWh)']:+.2f} → {f['Worst-year energy margin (MWh)']:+.2f} MWh.")
    L.append(f"**RTE (end of life, incl aux):** {b['Final-year RTE incl aux (%)']:.2f} → {f['Final-year RTE incl aux (%)']:.2f} % ({f['Final-year RTE incl aux (%)'] - b['Final-year RTE incl aux (%)']:+.2f} pp); excl aux {b['Final-year RTE excl aux (%)']:.2f} → {f['Final-year RTE excl aux (%)']:.2f} %.")
    L.append(f"**Auxiliary energy:** {b['Aux energy / cycle, year 1 (MWh)']:.3f} → {r['Aux energy / cycle, year 1 (MWh)']:.3f} MWh per cycle after re-sizing.")
    L.append(f"**Requirements with existing containers:** {f['All requirements met']}. " + ("Augmentation or more initial containers would be needed." if f["All requirements met"] == "NO" else "Still compliant."))
    return [x for x in L if x]


def to_excel(res, sz):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([(k, str(v)) for k, v in sz.items() if k not in ("ytab", "aug_tbl", "eff")], columns=["Input", "Value"]).to_excel(w, sheet_name="Inputs", index=False)
        for m, r in res.items():
            s = re.sub(r"[^A-Za-z0-9]", "", m)[:18]
            pd.DataFrame([("Container", m), ("DC installed per container (MWh)", r["c"].mwh), ("C-rate", r["c"].c_rate), ("Initial containers", r["n"]),
                          ("Initial installed (MWh)", r["n"] * r["c"].mwh), ("Aux per container discharge (MW)", r["c"].aux_dis_mw), ("Aux per container charge (MW)", r["c"].aux_chg_mw),
                          ("Calendar factor", r["cal"]), ("All requirements met", r["ok"])], columns=["Item", "Value"]).to_excel(w, sheet_name=s + "_sum", index=False)
            r["df"].to_excel(w, sheet_name=s + "_years", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = min(40, max(10, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()
