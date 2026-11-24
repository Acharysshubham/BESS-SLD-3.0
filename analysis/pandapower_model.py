"""Steady-state equivalent network: grid -> (MPT) -> MV bus -> IDTs -> PCS as static generators. Document assumptions."""
import copy, math


def run(P, R, mode="discharge"):
    try:
        import pandapower as pp, pandapower.shortcircuit as sc
    except ImportError:
        return dict(ok=False, error="pandapower not installed")
    try:
        net = pp.create_empty_network(f_hz=P["f_hz"]); gk, mv = P["grid_kv"], P["mv_kv"]
        bg = pp.create_bus(net, gk, name="POI")
        ssc = math.sqrt(3) * gk * max(P["isc_ka"], 0.1)
        pp.create_ext_grid(net, bg, vm_pu=1.0, s_sc_max_mva=ssc, s_sc_min_mva=0.7 * ssc, rx_max=0.1, rx_min=0.1)
        if abs(gk - mv) > 1e-6:
            bm = pp.create_bus(net, mv, name="MV Bus")
            pp.create_transformer_from_parameters(net, bg, bm, R["meta"]["mpt_mva"] or R["meta"]["s_tot"], gk, mv, 0.5, 10.0, 0.0, 0.0, name="MPT")
        else: bm = bg
        sign = 1 if mode == "discharge" else -1
        for r in R["idt"]["rows"]:
            lb = pp.create_bus(net, P["idt_kvs"], name=f"LV-{r['idt']}")
            pp.create_transformer_from_parameters(net, bm, lb, P["idt_s"], P["idt_kvp"], P["idt_kvs"], 0.5, P["idt_z"] or 8.0, 0.0, 0.0, name=f"IDT-{r['idt']}")
            pp.create_sgen(net, lb, p_mw=sign * r["p_mw"], q_mvar=r["q_mvar"] * sign)
        if P["aux_on"]: pp.create_load(net, bm, p_mw=R["meta"]["aux_kw"] / 1e3)
        pp.runpp(net)
        nsc = copy.deepcopy(net); nsc.sgen.drop(nsc.sgen.index, inplace=True)
        sc.calc_sc(nsc, case="max")
        ib = int(net.bus.index[net.bus.name == "MV Bus"][0]) if (net.bus.name == "MV Bus").any() else int(bg)
        return dict(ok=True, mode=mode, bus=net.res_bus.join(net.bus[["name", "vn_kv"]]), trafo=net.res_trafo.join(net.trafo[["name"]]),
                    grid=net.res_ext_grid, sc=nsc.res_bus_sc.join(nsc.bus[["name"]]), mv_ikss=float(nsc.res_bus_sc.ikss_ka.loc[ib]),
                    assumptions=["IDT/MPT losses and magnetising current neglected (vkr 0.5%)", "PCS modelled as constant P/Q static generators",
                                 "MPT impedance 10% assumed; grid X/R = 10", "Short-circuit excludes PCS fault contribution"])
    except Exception as e:
        return dict(ok=False, error=str(e))
