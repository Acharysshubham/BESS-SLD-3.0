"""BESS container sizing. Containers may differ in size/ratings (rows with qty)."""
import pandas as pd


def expand(df):
    """One dict per physical container, with id and DC power at the discharge C-rate."""
    out = []
    for _, r in pd.DataFrame(df).fillna(0).iterrows():
        for _ in range(int(r["qty"])):
            d = r.to_dict(); d["id"] = len(out) + 1; d["p_dc"] = d["mwh"] * d["c_dis"]; out.append(d)
    return out


def summary(df, ovr_dis=0.0, ovr_chg=0.0):
    u = expand(df)
    g = lambda f: sum(f(x) for x in u)
    s = dict(n=len(u), e_total=g(lambda x: x["mwh"]),
             e_bol=g(lambda x: x["mwh"] * x["dod"] * x["soh_bol"]), e_eol=g(lambda x: x["mwh"] * x["dod"] * x["soh_eol"]),
             p_dis_nameplate=g(lambda x: x["mwh"] * x["c_dis"]), p_chg_nameplate=g(lambda x: x["mwh"] * x["c_chg"]),
             p_dis_bol=g(lambda x: x["mwh"] * x["dod"] * x["soh_bol"] * x["c_dis"]),
             p_dis_eol=g(lambda x: x["mwh"] * x["dod"] * x["soh_eol"] * x["c_dis"]), aux_kw=g(lambda x: x["aux_kw"]))
    s["p_dis"] = ovr_dis or s["p_dis_nameplate"]; s["p_chg"] = ovr_chg or s["p_chg_nameplate"]
    s["overridden"] = [n for n, v in (("discharge power", ovr_dis), ("charge power", ovr_chg)) if v]
    s["duration_h"] = s["e_total"] / s["p_dis"] if s["p_dis"] else 0.0
    return s, u
