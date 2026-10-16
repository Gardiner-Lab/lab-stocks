"""
A primer's sequence, and what can be worked out from it.

Melting temperature by SantaLucia's unified nearest-neighbour parameters
(1998), at 50 mM Na+ and 250 nM primer, as primer design tools report it. A
degenerate primer (IUPAC codes beyond A, C, G, T) gets the simpler salt-adjusted
formula instead, counting S as G/C and W as A/T.
"""

import math
import re
from typing import Dict, Optional

IUPAC = set('ACGTRYSWKMBDHVN')
# Nearest-neighbour enthalpy (kcal/mol) and entropy (cal/K/mol), SantaLucia 1998.
NN = {
    'AA': (-7.9, -22.2), 'TT': (-7.9, -22.2), 'AT': (-7.2, -20.4), 'TA': (-7.2, -21.3),
    'CA': (-8.5, -22.7), 'TG': (-8.5, -22.7), 'GT': (-8.4, -22.4), 'AC': (-8.4, -22.4),
    'CT': (-7.8, -21.0), 'AG': (-7.8, -21.0), 'GA': (-8.2, -22.2), 'TC': (-8.2, -22.2),
    'CG': (-10.6, -27.2), 'GC': (-9.8, -24.4), 'GG': (-8.0, -19.9), 'CC': (-8.0, -19.9),
}
INIT = {'G': (0.1, -2.8), 'C': (0.1, -2.8), 'A': (2.3, 4.1), 'T': (2.3, 4.1)}


def clean(sequence: str) -> str:
    """A primer as letters only, upper case: 5' to 3', spaces and dashes gone."""
    s = re.sub(r'[\s\-]', '', (sequence or '').upper())
    s = re.sub(r"^5'?|3'?$", '', s)
    if not s:
        raise ValueError('A primer needs a sequence')
    bad = sorted(set(s) - IUPAC)
    if bad:
        raise ValueError(f'Not a DNA letter: {"".join(bad)} (write modifications in their own field)')
    if len(s) > 300:
        raise ValueError('Longer than 300 nt: is this a primer?')
    return s


def gc(sequence: str) -> float:
    s = sequence.upper()
    strong = sum(s.count(c) for c in 'GCS') + 0.5 * sum(s.count(c) for c in 'RYKMBDHVN')
    return round(100 * strong / len(s), 1) if s else 0.0


def tm(sequence: str, na_mm: float = 50.0, primer_nm: float = 250.0) -> Optional[float]:
    s = sequence.upper()
    if len(s) < 8:
        return None
    if set(s) - set('ACGT'):
        # Degenerate: salt-adjusted basic formula.
        return round(81.5 + 16.6 * math.log10(na_mm / 1000) + 0.41 * gc(s) - 600 / len(s), 1)
    dh = INIT[s[0]][0] + INIT[s[-1]][0]
    ds = INIT[s[0]][1] + INIT[s[-1]][1]
    for i in range(len(s) - 1):
        h, e = NN[s[i:i + 2]]
        dh += h
        ds += e
    ds += 0.368 * (len(s) - 1) * math.log(na_mm / 1000)            # salt correction
    t = (1000 * dh) / (ds + 1.987 * math.log(primer_nm * 1e-9 / 4)) - 273.15
    return round(t, 1)


def describe(sequence: str) -> Dict:
    return {'length': len(sequence), 'gc': gc(sequence), 'tm': tm(sequence)}
