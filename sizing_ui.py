"""Streamlit page: BESS sizing (energy / power / both), database upload, discharge/charge tables, augmentation, analyser."""
import copy
import pandas as pd
import plotly.graph_objects as go
from core import bess_sizing as S


def _style(df, cols):
    f = lambda v: "background-color:#c8f7c5;color:#0b5d1e" if v == "MATCHED" else ("background-color:#f9c6c6;color:#8a0f0f" if v == "NOT MATCHED" else "")
    s = df.style.format(precision=3); return getattr(s, "map", getattr(s, "applymap", None))(f, subset=cols)


def render(st, ss, P, apply_cb):
    Z = P["sz"] = {**copy.deepcopy(S.SZ), **P.get("sz", {})}
    if "db" not in ss: ss.db, ss.db_name = S.sample_db(), "Built-in illustrative sample (not manufacturer data)"

    def w(kind, label, k, c=None, **kw):
        key = "w_sz_" + k
        if key not in ss: ss[key] = Z[k]
        Z[k] = getattr(c or st, kind)(label, key=key, **kw); return Z[k]

    def ytable(cols, key):
        N = int(Z["years"]); yt = S.ytab(Z); df = pd.DataFrame([{"year": y, **{c: yt[y][c] for c in cols}} for y in range(1, N + 1)])
        ed = st.data_editor(df, hide_index=True, disabled=["year"], width="stretch", key=key)
        Z["ytab"] = [{**yt[int(r["year"])], **{c: float(r[c]) for c in cols}, "year": int(r["year"])} for _, r in ed.iterrows()]

    st.caption("Sizing for energy, power or both, driven by the product database. The result can be applied to the container list that feeds PCS / IDT / SLD design.")
    t = st.tabs(["1 Database", "2 Inputs", "3 Sizing result", "4 Discharge", "5 Charge", "6 Required vs calculated", "7 Analyser"])

    with t[0]:
        up = st.file_uploader("Upload product database (.xlsx: sheets Containers, SOH, Calendar)", type="xlsx", key="db_up")
        if up and ss.get("db_file") != up.name:
            try: ss.db, ss.db_name, ss.db_file = S.load_db(up), f"Uploaded: {up.name}", up.name; st.rerun()
            except Exception as ex: st.error(f"Database rejected: {ex}")
        c = st.columns(2)
        if c[0].button("Use built-in sample database"): ss.db, ss.db_name, ss.db_file = S.sample_db(), "Built-in illustrative sample (not manufacturer data)", None; st.rerun()
        c[1].download_button("Download database template (with sample rows)", S.template_db(), "bess_database_template.xlsx")
        st.info(f"Active database: **{ss.db_name}**")
        st.dataframe(ss.db["cont"], hide_index=True, width="stretch")
        with st.expander("SOH and calendar-degradation tables"):
            st.dataframe(ss.db["soh"], hide_index=True, width="stretch"); st.dataframe(ss.db["cal"], hide_index=True, width="stretch")
    db = ss.db

    with t[1]:
        st.subheader("Project requirement")
        c = st.columns(3)
        w("radio", "What must be fulfilled?", "fulfil", c[0], options=["Energy", "Power", "Both"], horizontal=True)
        w("selectbox", "Energy requirement is given as", "basis", c[1], options=["BOL only", "EOL only", "BOL and EOL", "Percentage per year"])
        c = st.columns(4)
        if Z["fulfil"] != "Power":
            if Z["basis"] == "BOL and EOL": w("number_input", "BOL energy at POI (MWh)", "e_bol", c[0], min_value=0.1); w("number_input", "EOL energy at POI (MWh)", "e_eol", c[1], min_value=0.1)
            else: w("number_input", {"BOL only": "BOL energy (MWh)", "EOL only": "EOL energy (MWh)"}.get(Z["basis"], "Reference energy, 100 % (MWh)"), "e_mwh", c[0], min_value=0.1)
        if Z["fulfil"] != "Energy": w("number_input", "Required power at POI (MW)", "p_mw", c[2], min_value=0.1)
        bol, eol = S.ref_energy(Z)
        if Z["fulfil"] != "Power" and Z["basis"] == "BOL only": st.caption(f"EOL assumed = 80 % of BOL = {eol:.2f} MWh; oversizing is computed on BOL = {bol:.2f} MWh.")
        if Z["fulfil"] != "Power" and Z["basis"] == "EOL only": st.caption(f"BOL assumed = 125 % of EOL = {bol:.2f} MWh; oversizing is computed on that BOL.")
        c = st.columns(4)
        w("radio", "Duration basis", "time_mode", c[0], options=["C-rate", "Duration (h)"])
        if Z["time_mode"] == "C-rate": w("number_input", "C-rate", "c_rate", c[1], min_value=0.05, max_value=4.0, step=0.05)
        else: w("number_input", "Discharge/charge time (h)", "t_h", c[1], min_value=0.25, step=0.25)
        c[2].metric("Effective C-rate / time", f"{S.c_user(Z):.3f} C / {S.duration(Z):.2f} h")
        c = st.columns(4)
        w("number_input", "Project duration (years)", "years", c[0], min_value=1, max_value=30); w("number_input", "Cycles per year", "cycles", c[1], min_value=1, max_value=730)
        w("number_input", "DOD (%)", "dod", c[2], min_value=50.0, max_value=100.0); w("number_input", "BESS availability (%)", "avail", c[3], min_value=50.0, max_value=100.0)
        c = st.columns(4)
        w("number_input", "Operating temperature (°C)", "temp", c[0], min_value=-40.0, max_value=80.0); w("number_input", "Min RTE at EOL (%)", "min_rte", c[1], min_value=50.0, max_value=100.0)
        w("number_input", "POI voltage (kV)", "poi_kv", c[2], min_value=0.4, max_value=765.0); w("number_input", "LV cable stages counted (DC cable + PCS-IDT)", "lv_stages", c[3], min_value=1, max_value=2)
        st.caption("POI ≤ 33 kV: PCS, LV cable, IDT, interconnecting cable, measurement. POI > 33 kV: also MV cable & switchgear and main power transformer.")
        c = st.columns(3)
        w("radio", "Mismatch losses", "mm_mode", c[0], options=["Same every year", "Varies by year"])
        if Z["mm_mode"] == "Same every year": w("number_input", "Mismatch loss (%/yr)", "mm_const", c[1], min_value=0.0, max_value=20.0, step=0.1)
        w("selectbox", "Container", "model_pick", c[2], options=[S.AUTO] + list(db["cont"].model))
        st.subheader("Auxiliary, standby and DC-DC RTE")
        c = st.columns(4)
        w("checkbox", "Auxiliary consumption applicable", "aux_on", c[0]); w("checkbox", "Additional auxiliary energy", "extra_aux_on", c[1]); w("checkbox", "Standby energy", "standby_on", c[2]); w("checkbox", "Year-wise DC-DC RTE", "var_rte_on", c[3])
        c = st.columns(2)
        if Z["extra_aux_on"]: w("number_input", "Additional auxiliary energy (MWh per cycle)", "extra_aux", c[0], min_value=0.0)
        if Z["standby_on"]: w("number_input", "Standby energy (MWh per cycle)", "standby", c[1], min_value=0.0)
        st.subheader("FAT / SAT period")
        w("checkbox", "FAT/SAT applicable (before Year 1)", "fatsat_on")
        if Z["fatsat_on"]:
            c = st.columns(3); w("number_input", "Duration (months, max 6)", "fatsat_m", c[0], min_value=1, max_value=6); w("number_input", "SOH at FAT/SAT (%)", "fat_soh", c[1], min_value=50.0, max_value=100.0); w("number_input", "Calendar factor at FAT/SAT (%)", "fat_cal", c[2], min_value=50.0, max_value=100.0)
        st.subheader("Year-wise inputs")
        cols = ["mismatch_pct"] * (Z["mm_mode"] != "Same every year") + ["dcdc_rte_pct"] * bool(Z["var_rte_on"]) + ["pct_of_req"] * (Z["basis"] == "Percentage per year") + ["plant_mw"]
        st.caption("mismatch_pct: % loss that year | dcdc_rte_pct: % (0 = database) | pct_of_req: % of reference energy | plant_mw: AC MV power to plant infrastructure (user input)")
        ytable(cols, "ed_sz_y")
        st.subheader("Augmentation")
        w("checkbox", "Augmentation capacity applicable", "aug_on")
        if Z["aug_on"]:
            df = pd.DataFrame(Z["aug_tbl"] or [{"year": max(2, int(Z["years"]) // 2), "containers": 2}], columns=["year", "containers"])
            ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key="ed_sz_aug", column_config={"year": st.column_config.NumberColumn(min_value=1, max_value=int(Z["years"]), step=1), "containers": st.column_config.NumberColumn(min_value=0, step=1)})
            Z["aug_tbl"] = ed.dropna().astype(int).to_dict("records")
        st.subheader("AC efficiencies (from database, editable)")
        for _, c in S.candidates(db, Z).iterrows():
            with st.expander(c.model, expanded=False):
                dflt = S.eff_defaults(c); cols = st.columns(4); Z["eff"].setdefault(c.model, {})
                for i, (k, lab) in enumerate(S.eff_fields(Z["poi_kv"])):
                    key = f"w_sz_eff_{c.model}_{k}"
                    if key not in ss: ss[key] = float(dflt[k])
                    Z["eff"][c.model][k] = cols[i % 4].number_input(lab, key=key, min_value=0.0, max_value=100.0, format="%.3f")

    res = S.run_all(db, Z)
    if not res: st.error("No container in the database."); return
    models = list(res)

    with t[2]:
        if len(models) > 1: st.warning(f"{len(models)} containers share the nearest C-rate; sized separately: " + ", ".join(models))
        for m, r in res.items():
            c_, n = r["c"], r["n"]; st.subheader(m)
            if r["note"]: st.caption(r["note"])
            k = st.columns(5)
            for col, (l, v) in zip(k, [("DC capacity / container (MWh)", f"{c_.mwh:.3f}"), ("Initial containers", n), ("Initial installed (MWh)", f"{n * c_.mwh:.2f}"),
                                       ("Aux / container dis (MW)", f"{c_.aux_dis_mw:.3f}"), ("Aux / container chg (MW)", f"{c_.aux_chg_mw:.3f}")]): col.metric(l, v)
            if r["x"] is not None:
                bol, _ = S.ref_energy(Z)
                st.write(f"Oversizing on BOL requirement: **{r['x_actual']:.1f} %** (search value {r['x']:.1f} %, target band {S.BAND[0]:g}-{S.BAND[1]:g} %). Calendar factor {r['cal'] * 100:.2f} %.")
                if not r["found"]: st.error(f"Energy requirement not met even at {S.SEARCH_MAX:g} % oversizing. Reduce requirement, add augmentation or choose another container.")
                elif not r["band_ok"]: st.warning(f"Minimum oversizing that meets every year is {r['x']:.1f} %, outside the {S.BAND[0]:g}-{S.BAND[1]:g} % band. Consider augmentation or a lower DOD/mismatch.")
            else: st.write(f"Power sizing: {r['n_power']} containers for {Z['p_mw']:g} MW at POI.")
            if Z["fulfil"] == "Both": st.write(f"Energy needs {r['n_energy']} containers, power needs {r['n_power']}; the larger governs.")
            if r["df"]["RTE"].iloc[-1] == "NOT MATCHED": st.error(f"EOL RTE (incl aux) {r['df']['RTE incl aux %'].iloc[-1]:.2f} % < {Z['min_rte']:g} %. Oversizing barely changes RTE; use a container with higher DC RTE or revise efficiencies.")
            (st.success if r["ok"] else st.error)("All requirements met." if r["ok"] else "Requirements not met for every year.")
            if st.button(f"Apply {m} to container design (step 3)", key="ap_" + m): apply_cb(r, Z); st.toast("Containers updated. Review steps 3-6.")

    D_COLS = ["Containers", "Installed DC (MWh)", "Availability %", "DC discharge eff %", "SOH %", "Calendar %", "Mismatch %", "DOD %", "DC discharge cap (MWh)", "POI excl aux (MWh)", "Aux energy dis (MWh)", "POI incl aux (MWh)", "Augmented energy (MWh)", "Plant infra (MW)", "AC MV energy dis (MWh)"]
    C_COLS = ["Containers", "DC charge cap (MWh)", "DC-DC RTE %", "POI chg excl aux (MWh)", "Aux energy chg (MWh)", "POI chg incl aux (MWh)", "Augmented chg energy (MWh)", "Plant infra (MW)", "AC MV energy chg (MWh)", "RTE excl aux %", "RTE incl aux %", "AC RTE (AC MV) %"]
    with t[3]:
        for m, r in res.items(): st.markdown(f"**{m}**"); st.dataframe(r["df"][["Year"] + D_COLS].style.format(precision=3), hide_index=True, width="stretch")
        st.caption("DC cap = installed x availability x sqrt(DC RTE) x SOH x calendar x DOD x (1 - mismatch). POI excl aux = DC cap x AC chain. Incl aux = excl - aux load x discharge time (+ additional aux + standby). Augmented cohorts age from their own installation year.")
    with t[4]:
        for m, r in res.items(): st.markdown(f"**{m}**"); st.dataframe(r["df"][["Year"] + C_COLS].style.format(precision=3), hide_index=True, width="stretch")
        st.caption("Charge excl aux = DC cap / (AC chain x DC-DC RTE). Incl aux = excl + aux load x charge time. RTE = discharge / charge.")
    with t[5]:
        for m, r in res.items():
            st.markdown(f"**{m}**"); cols = ["Required energy (MWh)", "AC MV energy dis (MWh)", "Energy", "Required power (MW)", "POI power net (MW)", "Power", "RTE incl aux %", "RTE"]
            st.dataframe(_style(r["df"][["Year"] + cols], ["Energy", "Power", "RTE"]), hide_index=True, width="stretch")
            d = r["df"][r["df"].Year != "FAT/SAT"]; fig = go.Figure()
            fig.add_scatter(x=d.Year, y=d["Required energy (MWh)"], name="Required", mode="lines+markers"); fig.add_scatter(x=d.Year, y=d["AC MV energy dis (MWh)"], name="Calculated", mode="lines+markers")
            fig.update_layout(title=f"{m}: energy at POI by year", xaxis_title="Year", yaxis_title="MWh", height=320); st.plotly_chart(fig, width="stretch", key="pl_" + m)
        st.caption("Required values come from the BOL/EOL profile unless overridden: enter req_energy_mwh / req_power_mw per year in the table below.")
        ytable(["req_energy_mwh", "req_power_mw"], "ed_sz_req")

    with t[6]:
        m = st.selectbox("Container to analyse", models, key="an_m"); st.caption("Compares the design before and after a parameter change: with the existing containers, and re-sized.")
        PARAM = {"dod": ("DOD (%)", Z["dod"], 50.0, 100.0), "avail": ("BESS availability (%)", Z["avail"], 50.0, 100.0), "temp": ("Operating temperature (°C)", Z["temp"], -40.0, 80.0),
                 "soh_scale": ("SOH multiplier (%)", Z["soh_scale"], 50.0, 110.0), "dcrte_delta": ("DC RTE change (points)", Z["dcrte_delta"], -10.0, 5.0), "mm_const": ("Mismatch loss (%/yr, all years)", Z["mm_const"], 0.0, 20.0)}
        c = st.columns(2); k = c[0].selectbox("Parameter", list(PARAM), format_func=lambda x: PARAM[x][0]); lab, cur, lo, hi = PARAM[k]
        new = c[1].number_input(f"New value (current {cur:g})", min_value=lo, max_value=hi, value=float(min(max(cur - (5.0 if k in ("dod", "avail", "soh_scale") else 1.0), lo), hi)), key=f"an_v_{k}")
        chg = {k: new}
        if k == "mm_const": chg["mm_mode"] = "Same every year"
        wi = S.whatif(db, Z, m, chg); b, f, r = wi["before"], wi["fixed"], wi["resized"]
        st.dataframe(pd.DataFrame({"Metric": list(b), "Before": [b[x] for x in b], "After (same containers)": [f[x] for x in b], "After (re-sized)": [r[x] for x in b]}).astype(str), hide_index=True, width="stretch")
        st.markdown("#### Engineering analysis")
        for line in S.explain(k, wi, Z): st.markdown("- " + line)
        st.caption("Rule-based analysis computed from the model, not a language-model chat. It explains only effects the model contains.")
        st.download_button("Download sizing workbook", S.to_excel(res, Z), "bess_sizing.xlsx")
