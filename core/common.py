import math
STD_A = [16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000, 6300]
STD_MVA = [1, 1.25, 1.6, 2, 2.5, 3.15, 4, 5, 6.3, 8, 10, 12.5, 16, 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250]
STD_KVA = [63, 100, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500]
ORDER = {"FAIL": 3, "UNVERIFIED": 2, "WARN": 1, "PASS": 0}


def cl(x):  # ceiling that ignores float noise (16.000000000000004 -> 16)
    return math.ceil(round(x, 6))


def nxt(v, table):
    return next((a for a in table if a >= v), table[-1])


def amps(s_mva, kv):
    return s_mva * 1e3 / (math.sqrt(3) * kv)


def worst(statuses):
    return max(statuses, key=ORDER.get) if statuses else "PASS"
