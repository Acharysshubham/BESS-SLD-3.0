"""IDT sizing and PCS-to-winding allocation, bounded by thermal and winding limits."""
import math
from .common import cl


def size(P, n_pcs, s_pcs, p_ac, q_tot):
    s_idt, nlv, ppw = P["idt_s"], int(P["idt_nlv"]), int(P["idt_ppw"])
    cap = s_idt * P["idt_derate"] * P["idt_lim"]
    s_tot = n_pcs * s_pcs
    k_th, k_w = int(cap / s_pcs + 1e-9), nlv * ppw
    k = min(k_th, k_w)
    out = dict(s_total=s_tot, n_prelim=cl(s_tot / s_idt), k_thermal=k_th, k_winding=k_w, per_idt=k, feasible=k >= 1, rows=[])
    if k < 1: return out
    n = cl(n_pcs / k) + int(P["idt_spare"])
    n = min(n, n_pcs)  # never more IDTs than PCS
    for i in range(n):
        m = n_pcs // n + (1 if i < n_pcs % n else 0)
        s = m * s_pcs; share = s / s_tot if s_tot else 0
        out["rows"].append(dict(idt=i + 1, n_pcs=m, windings_used=cl(m / ppw), s_conn=s, p_mw=p_ac * share, q_mvar=q_tot * share,
                                loading=s / (s_idt * P["idt_derate"]) * 100, spare_mva=cap - s))
    out["n"] = n
    return out
