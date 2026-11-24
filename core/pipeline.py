import math
import pandas as pd
from . import bess_calculations as B, pcs_optimizer as PC, idt_optimizer as I
from .topology_generator import build_nodes
from .validation_engine import validate


def run(P):
    R = {}
    R["bess"], R["units"] = B.summary(P["containers"], P["ovr_pdis"], P["ovr_pchg"])
    if R["bess"]["n"] == 0 or not P["pcs_cat"]:
        R["error"] = "Add at least one container and one PCS model."; return R
    R["picks"], R["pcs_table"] = PC.configs(P, R["units"], R["bess"]["p_dis"])
    ch = R["picks"][P["pcs_choice"]]
    if P["pcs_nover"] > 0: ch = PC.evaluate(ch["m"], P, R["units"], R["bess"]["p_dis"], ch["red"], int(P["pcs_nover"]))
    R["pcs"] = ch
    q = P["pcs_q"] if P["pcs_q"] > 0 else math.sqrt(max(ch["s_req"] ** 2 - ch["p_ac"] ** 2, 0))
    R["q_tot"] = q
    R["idt"] = I.size(P, ch["n"], ch["m"]["s_mva"], ch["p_ac"], q)
    R["nodes"], R["meta"] = build_nodes(P, R)
    R["val"] = validate(P, R, R["nodes"])
    return R
