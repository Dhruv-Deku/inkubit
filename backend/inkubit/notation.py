"""Dirac notation, both ways: exact state vectors <-> kets a person can read.

``dirac`` writes a state the way a textbook does: qubits that are on their own are factored out (and the
factoring is checked by rebuilding the state), a magnitude shared by every term goes in front, amplitudes
are recognised as surds (1/√2, √3/2) and phases as multiples of π (i, −1, e^(iπ/4)), with a LaTeX twin.
``parse_ket`` reads such expressions back into a normalised vector, including LaTeX pasted from a paper.

Qubit order follows Qiskit: in |q2 q1 q0⟩ the rightmost digit is qubit 0.
"""

from __future__ import annotations

import cmath
import math
import re
from fractions import Fraction
from itertools import combinations
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

MAX_TERMS = 16  # terms written out before "… (k more)"
MAX_FACTOR_QUBITS = 8  # factoring is an exhaustive search over subsets, so it stops here
MAX_KET_QUBITS = 8
_EPS = 1e-10
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_S = 1 / math.sqrt(2)


class NotationError(ValueError):
    """The text is not a state Inkubit can read; the message says why."""


class DiracForm(BaseModel):
    text: str
    latex: str
    terms: int  # basis states with a nonzero amplitude
    groups: list[list[int]] = Field(default_factory=list)  # entangled groups (qubits high to low), size >= 2
    product: bool = False  # every qubit is on its own
    expanded: str | None = None  # the plain sum, when ``text`` is factored


# ---------------------------------------------------------------- numbers

def _surd(n: int) -> tuple[int, int]:
    """n = a² · b with b square-free: (a, b)."""
    a, b, k = 1, n, 2
    while k * k <= b:
        while b % (k * k) == 0:
            b //= k * k
            a *= k
        k += 1
    return a, b


def _root(n: int) -> tuple[str, str]:
    a, b = _surd(n)
    if b == 1:
        return str(a), str(a)
    return (f"√{b}" if a == 1 else f"{a}√{b}"), (rf"\sqrt{{{b}}}" if a == 1 else rf"{a}\sqrt{{{b}}}")


def _decimal(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def magnitude(m: float) -> tuple[str, str]:
    """A magnitude as an exact surd when m² is a simple fraction, else 3 decimals: (text, latex)."""
    f = Fraction(m * m).limit_denominator(1024)
    if f <= 0 or abs(float(f) - m * m) > 1e-9:
        return _decimal(m), _decimal(m)
    nt, nl = _root(f.numerator)
    if f.denominator == 1:
        return nt, nl
    dt, dl = _root(f.denominator)
    if "√" in dt and dt[0].isdigit():
        dt = f"({dt})"
    return f"{nt}/{dt}", rf"\frac{{{nl}}}{{{dl}}}"


def phase(phi: float) -> tuple[int, str, str]:
    """A phase factor e^(iφ) as (sign, text, latex): sign -1 is a plain minus; text '' means no factor."""
    phi = math.remainder(phi, 2 * math.pi)
    f = Fraction(phi / math.pi).limit_denominator(12)
    if abs(float(f) * math.pi - phi) > 1e-9:
        return 1, f"e^({_decimal(phi)}i)", rf"e^{{{_decimal(phi)}i}}"
    if f == 0:
        return 1, "", ""
    if abs(f) == 1:
        return -1, "", ""
    if abs(f) == Fraction(1, 2):
        return (1 if f > 0 else -1), "i", "i"
    num, den = abs(f.numerator), f.denominator
    sign = "−" if f < 0 else ""
    k = "" if num == 1 else str(num)
    return 1, f"e^({sign}{k}iπ/{den})", rf"e^{{{'-' if f < 0 else ''}{k}i\pi/{den}}}"


def _coef(mag: tuple[str, str] | None, factor: tuple[str, str]) -> tuple[str, str]:
    ft, fl = factor
    if mag is None or mag[0] == "1":
        return ft, fl
    mt, ml = mag
    if not ft:
        return mt, ml
    if "/" in mt:
        return f"({mt}){ft}", f"{ml}\\,{fl}"
    return (f"{mt}·{ft}" if ft.startswith("e") else f"{mt}{ft}"), f"{ml}\\,{fl}"


def _sum(v: np.ndarray, k: int) -> tuple[str, str, int, bool]:
    """(text, latex, terms, has_prefactor) for a k-qubit vector, global phase removed."""
    p = np.abs(v) ** 2
    nz = [i for i in range(len(v)) if p[i] > _EPS]
    v = v * cmath.exp(-1j * cmath.phase(v[nz[0]]))  # the first term real and positive, as textbooks write it
    shown = nz if len(nz) <= MAX_TERMS else sorted(sorted(nz, key=lambda i: -p[i])[:MAX_TERMS])
    mags = [abs(v[i]) for i in nz]
    common = len(nz) > 1 and max(mags) - min(mags) < 1e-9
    ts, ls = [], []
    for j, i in enumerate(shown):
        sign, ft, fl = phase(cmath.phase(v[i]))
        ct, cl = _coef(None if common else magnitude(abs(v[i])), (ft, fl))
        bits = format(i, f"0{k}b")
        if j == 0:
            ts.append(f"{'−' if sign < 0 else ''}{ct}|{bits}⟩")
            ls.append(f"{'-' if sign < 0 else ''}{cl}|{bits}\\rangle")
        else:
            ts.append(f" {'−' if sign < 0 else '+'} {ct}|{bits}⟩")
            ls.append(f" {'-' if sign < 0 else '+'} {cl}|{bits}\\rangle")
    if len(shown) < len(nz):
        ts.append(f" + … ({len(nz) - len(shown)} more)")
        ls.append(r" + \dots")
    bt, bl = "".join(ts), "".join(ls)
    if common:
        pt, pl = magnitude(mags[0])
        return f"{pt} ({bt})", rf"{pl}\left({bl}\right)", len(nz), True
    return bt, bl, len(nz), False


_NAMED_ONE = {"0": (1, 0), "1": (0, 1), "+": (_S, _S), "−": (_S, -_S), "+i": (_S, 1j * _S), "−i": (_S, -1j * _S)}


def named_qubit(v: np.ndarray) -> str | None:
    """'0', '1', '+', '−', '+i' or '−i' when a one-qubit state is one of those (up to global phase)."""
    for name, w in _NAMED_ONE.items():
        if abs(np.vdot(np.array(w, dtype=complex), v)) ** 2 > 1 - 1e-9:
            return name
    return None


# ---------------------------------------------------------------- factoring

def reduced(psi: np.ndarray, n: int, qubits: list[int]) -> np.ndarray:
    """Reduced density matrix of ``qubits`` (first listed = most significant) from a pure state."""
    axes = [n - 1 - q for q in qubits]
    t = np.moveaxis(psi.reshape([2] * n), axes, list(range(len(axes))))
    m = t.reshape(2 ** len(qubits), -1)
    return m @ m.conj().T


def _pure(rho: np.ndarray) -> bool:
    return abs(float(np.trace(rho @ rho).real) - 1.0) < 1e-9


def blocks(psi: np.ndarray, n: int) -> list[list[int]] | None:
    """Split the qubits into the smallest groups that are each in a pure state of their own (high to low)."""
    if n > MAX_FACTOR_QUBITS:
        return None
    rem = list(range(n - 1, -1, -1))
    singles = [q for q in rem if _pure(reduced(psi, n, [q]))]
    rem = [q for q in rem if q not in singles]
    found_blocks = [[q] for q in singles]
    while rem:
        block = None
        if len(rem) >= 4:  # two groups of at least two each are possible
            for k in range(1, len(rem) - 2):
                for combo in combinations(rem[1:], k):
                    s = sorted([rem[0], *combo], reverse=True)
                    if _pure(reduced(psi, n, s)):
                        block = s
                        break
                if block:
                    break
        block = block or list(rem)
        found_blocks.append(block)
        rem = [q for q in rem if q not in block]
    return sorted(found_blocks, key=lambda b: -b[0])


def _block_vector(psi: np.ndarray, n: int, qubits: list[int]) -> np.ndarray:
    _, vecs = np.linalg.eigh(reduced(psi, n, qubits))
    return vecs[:, -1]


def rebuild(n: int, parts: list[tuple[list[int], np.ndarray]]) -> np.ndarray:
    """The full state from per-group states (each group's qubits listed high to low)."""
    idx = np.arange(2 ** n)
    out = np.ones(2 ** n, dtype=complex)
    for qs, v in parts:
        sub = np.zeros(2 ** n, dtype=int)
        for j, q in enumerate(qs):
            sub |= ((idx >> q) & 1) << (len(qs) - 1 - j)
        out *= v[sub]
    return out


def factor(psi: np.ndarray, n: int) -> list[tuple[list[int], np.ndarray]] | None:
    """Per-group states whose tensor product is exactly ``psi`` (checked), or None when it cannot be split."""
    bl = blocks(psi, n)
    if not bl:
        return None
    parts = [(b, _block_vector(psi, n, b)) for b in bl]
    if abs(np.vdot(rebuild(n, parts), psi)) ** 2 < 1 - 1e-9:
        return None
    return parts


def dirac(psi: Any, n: int | None = None) -> DiracForm:
    """A state vector written in Dirac notation, factored where the qubits are independent."""
    psi = np.asarray(psi, dtype=complex)
    n = n or int(round(math.log2(len(psi))))
    st, sl, terms, _ = _sum(psi, n)
    parts = factor(psi, n) if n > 1 else None
    groups = [qs for qs, _ in parts if len(qs) > 1] if parts else ([] if n > MAX_FACTOR_QUBITS else [list(range(n - 1, -1, -1))])
    if n == 1:
        groups = []
    if not parts or len(parts) == 1 or terms == 1:
        return DiracForm(text=st, latex=sl, terms=terms, groups=groups,
                         product=n == 1 or (parts is not None and not groups))
    names = [named_qubit(v) if len(qs) == 1 else None for qs, v in parts]
    contiguous = [q for qs, _ in parts for q in qs] == list(range(n - 1, -1, -1))
    if contiguous and all(x in ("0", "1", "+", "−") for x in names):  # |+0−⟩
        word = "".join(names)  # type: ignore[arg-type]
        return DiracForm(text=f"|{word}⟩", latex=f"|{word.replace('−', '-')}\\rangle", terms=terms, groups=[],
                         product=True, expanded=st)
    ts, ls = [], []
    for qs, v in parts:
        name = named_qubit(v) if len(qs) == 1 else None
        if name:
            bt, bl = f"|{name}⟩", f"|{name.replace('−', '-')}\\rangle"
        else:
            bt, bl, k, pre = _sum(v, len(qs))
            if k > 1 and not pre:
                bt, bl = f"({bt})", rf"\left({bl}\right)"
        if not contiguous:
            sub = "".join(str(q) for q in qs)
            bt, bl = bt + sub.translate(_SUB), bl + f"_{{{sub}}}"
        ts.append(bt)
        ls.append(bl)
    return DiracForm(text=" ⊗ ".join(ts), latex=r" \otimes ".join(ls), terms=terms, groups=groups,
                     product=not groups, expanded=st)


# ---------------------------------------------------------------- reading kets

_LATEX = [(r"\left", ""), (r"\right", ""), (r"\rangle", "⟩"), (r"\otimes", "⊗"), (r"\cdot", "*"),
          (r"\times", "*"), (r"\pi", "π"), (r"\,", " "), (r"\;", " "), (r"\!", "")]
_TOKEN = re.compile(r"\s*(?:(?P<ket>\|[^|⟩>]{1,24}[⟩>])|(?P<num>\d+\.\d*|\.\d+|\d+)|(?P<name>[A-Za-zα-ω]+)"
                    r"|(?P<op>[-+*/^(){}⊗√π]))")
_WORDS = ("sqrt", "cos", "sin", "tan", "exp", "pi", "e", "i", "j")
_FUNCS = {"sqrt": cmath.sqrt, "cos": cmath.cos, "sin": cmath.sin, "tan": cmath.tan, "exp": cmath.exp}


def _clean(text: str) -> str:
    s = text.strip()
    for a, b in _LATEX:
        s = s.replace(a, b)
    s = re.sub(r"\\ket\{([^{}]*)\}", r"|\1⟩", s)
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", s)
    for _ in range(6):  # \frac{a}{b}, innermost first
        s2 = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
        if s2 == s:
            break
        s = s2
    s = (s.replace("〉", "⟩").replace("−", "-").replace("–", "-").replace("·", "*").replace("×", "*")
         .replace("**", "^").replace("π", " pi ").replace("np.", "").replace("numpy.", "").replace("math.", "").replace("cmath.", ""))
    if "=" in s:  # "|ψ⟩ = (|00⟩ + |11⟩)/√2": keep the right-hand side
        s = s.rsplit("=", 1)[1]
    if "\\" in s:
        raise NotationError("I could not read some LaTeX in it: write kets as |01⟩ and roots as √2 or sqrt(2).")
    return s


def _split_name(name: str) -> list[str]:
    """'ipi' -> ['i', 'pi']: names glued together from the known words."""
    if name.lower() in _WORDS:
        return [name.lower()]
    for w in sorted(_WORDS, key=len, reverse=True):
        if name.lower().startswith(w):
            rest = _split_name(name[len(w):]) if len(name) > len(w) else []
            if len(name) == len(w) or rest:
                return [w, *rest]
    raise NotationError(f"I don't know the symbol '{name}'. Use numbers, i, π, √, sqrt, cos, sin and exp.")


def _tokens(s: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(s):
        if s[pos:].strip() == "":
            break
        m = _TOKEN.match(s, pos)
        if not m or m.end() == pos:
            bad = s[pos:].strip()[:12]
            raise NotationError(f"I could not read '{bad}'. Kets look like |0⟩, |01⟩, |+⟩ or |Φ+⟩.")
        kind = m.lastgroup or ""
        val = m.group(kind)
        if kind == "name":
            out.extend(("name", w) for w in _split_name(val))
        else:
            out.append((kind, val))
        pos = m.end()
    return out


_KET_NAMES = {
    "+i": np.array([_S, 1j * _S]), "-i": np.array([_S, -1j * _S]),
    "φ+": np.array([_S, 0, 0, _S]), "phi+": np.array([_S, 0, 0, _S]),
    "φ-": np.array([_S, 0, 0, -_S]), "phi-": np.array([_S, 0, 0, -_S]),
    "ψ+": np.array([0, _S, _S, 0]), "psi+": np.array([0, _S, _S, 0]),
    "ψ-": np.array([0, _S, -_S, 0]), "psi-": np.array([0, _S, -_S, 0]),
}
_ONE_KET = {"0": np.array([1, 0]), "1": np.array([0, 1]), "+": np.array([_S, _S]), "-": np.array([_S, -_S])}


def _ket(content: str) -> np.ndarray:
    c = content.replace(" ", "").replace("−", "-")
    low = c.lower()
    if low in _KET_NAMES:
        return _KET_NAMES[low].astype(complex)
    m = re.fullmatch(r"(ghz|w)(\d?)", low)
    if m:
        k = int(m.group(2) or 3)
        if not 2 <= k <= MAX_KET_QUBITS:
            raise NotationError(f"|{content}⟩ needs 2 to {MAX_KET_QUBITS} qubits.")
        v = np.zeros(2 ** k, dtype=complex)
        if m.group(1) == "ghz":
            v[0] = v[-1] = _S
        else:
            for q in range(k):
                v[1 << q] = 1 / math.sqrt(k)
        return v
    if not c or not re.fullmatch(r"[01+\-]+", c):
        raise NotationError(f"|{content}⟩ is a name, not a state I can compute. Write it out, e.g. (|00⟩ + |11⟩)/√2, "
                            "or use 0, 1, +, − and the named states |Φ+⟩, |Φ−⟩, |Ψ+⟩, |Ψ−⟩, |+i⟩, |GHZ⟩, |W⟩.")
    if len(c) > MAX_KET_QUBITS:
        raise NotationError(f"Kets up to {MAX_KET_QUBITS} qubits, please.")
    v = np.array([1], dtype=complex)
    for ch in c:
        v = np.kron(v, _ONE_KET[ch])
    return v


class _Ket:
    def __init__(self, v: np.ndarray):
        self.v = v
        self.n = int(round(math.log2(len(v))))


Value = Any  # complex or _Ket


def _add(a: Value, b: Value, sign: int) -> Value:
    if isinstance(a, _Ket) and isinstance(b, _Ket):
        if a.n != b.n:
            raise NotationError(f"I can't add a {a.n}-qubit ket to a {b.n}-qubit ket.")
        return _Ket(a.v + sign * b.v)
    if isinstance(a, _Ket) or isinstance(b, _Ket):
        raise NotationError("I can't add a number to a ket: every term needs a ket, like 0.6|0⟩ + 0.8|1⟩.")
    return a + sign * b


def _mul(a: Value, b: Value) -> Value:
    if isinstance(a, _Ket) and isinstance(b, _Ket):
        if a.n + b.n > MAX_KET_QUBITS:
            raise NotationError(f"Kets up to {MAX_KET_QUBITS} qubits, please.")
        return _Ket(np.kron(a.v, b.v))
    if isinstance(a, _Ket):
        return _Ket(a.v * b)
    if isinstance(b, _Ket):
        return _Ket(b.v * a)
    return a * b


class _Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.toks, self.i = toks, 0

    def peek(self) -> tuple[str, str] | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise NotationError("The expression ends too early: is a bracket or a term missing?")
        self.i += 1
        return tok

    def expr(self) -> Value:
        v = self.term()
        while (t := self.peek()) and t[1] in "+-" and t[0] == "op":
            self.take()
            v = _add(v, self.term(), 1 if t[1] == "+" else -1)
        return v

    def _starts_atom(self, t: tuple[str, str] | None) -> bool:
        return bool(t) and (t[0] in ("num", "ket", "name") or t[1] in ("(", "{", "√", "π"))  # type: ignore[index]

    def term(self) -> Value:
        v = self.unary()
        while True:
            t = self.peek()
            if t and t[0] == "op" and t[1] in "*⊗":
                self.take()
                v = _mul(v, self.unary())
            elif t and t[0] == "op" and t[1] == "/":
                self.take()
                d = self.unary()
                if isinstance(d, _Ket):
                    raise NotationError("I can't divide by a ket.")
                if abs(d) < 1e-15:
                    raise NotationError("That divides by zero.")
                v = _mul(v, 1 / d)
            elif self._starts_atom(t):  # implicit product: 1/√2 (|00⟩ + |11⟩), 0.8i|1⟩, |0⟩|1⟩
                v = _mul(v, self.power())
            else:
                return v

    def unary(self) -> Value:
        t = self.peek()
        if t and t[0] == "op" and t[1] in "+-":
            self.take()
            v = self.unary()
            return v if t[1] == "+" else _mul(v, -1)
        return self.power()

    def power(self) -> Value:
        base = self.atom()
        t = self.peek()
        if t and t[0] == "op" and t[1] == "^":
            self.take()
            exp = self.unary()
            if isinstance(base, _Ket) or isinstance(exp, _Ket):
                raise NotationError("Powers work on numbers only.")
            return cmath.exp(exp) if base == math.e else complex(base) ** exp
        return base

    def atom(self) -> Value:
        kind, val = self.take()
        if kind == "num":
            return complex(float(val))
        if kind == "ket":
            return _Ket(_ket(val[1:-1]))
        if val == "π" or val == "pi":
            return complex(math.pi)
        if val == "√":
            arg = self.atom()
            if isinstance(arg, _Ket):
                raise NotationError("√ works on numbers only.")
            return cmath.sqrt(arg)
        if val in ("(", "{"):
            v = self.expr()
            close = self.take()[1]
            if close not in (")", "}"):
                raise NotationError("A bracket is not closed.")
            return v
        if kind == "name":
            if val in ("i", "j"):
                return 1j
            if val == "e":
                return math.e
            if val in _FUNCS:
                arg = self.power()
                if isinstance(arg, _Ket):
                    raise NotationError(f"{val} works on numbers only.")
                return _FUNCS[val](arg)
        raise NotationError(f"I did not expect '{val}' there.")


def evaluate(text: str) -> Value:
    s = _clean(text)
    toks = _tokens(s)
    if not toks:
        raise NotationError("There is nothing to read.")
    p = _Parser(toks)
    v = p.expr()
    if p.peek() is not None:
        rest = "".join(t[1] for t in p.toks[p.i:p.i + 4])
        raise NotationError(f"I stopped reading at '{rest}': is an operator missing?")
    return v


def scalar(text: str) -> float:
    """A real number written as an expression: 'pi/4', '-np.pi/2', '2*π/3', '0.25'."""
    v = evaluate(text)
    if isinstance(v, _Ket):
        raise NotationError(f"'{text}' is a state, not a number.")
    if abs(complex(v).imag) > 1e-12:
        raise NotationError(f"'{text}' is not a real number.")
    return float(complex(v).real)


def parse_ket(text: str) -> tuple[np.ndarray, float]:
    """(normalised state vector, the norm as written) for a Dirac expression."""
    v = evaluate(text)
    if not isinstance(v, _Ket):
        raise NotationError("That is a number, not a state: include at least one ket such as |0⟩.")
    norm = float(np.linalg.norm(v.v))
    if norm < 1e-12:
        raise NotationError("The amplitudes cancel to zero, so this is not a state.")
    return v.v / norm, norm


def looks_like_ket(text: str) -> bool:
    return bool(re.search(r"\|[^|\n]{1,24}(?:⟩|>|〉|\\rangle)|\\ket\{", text))
