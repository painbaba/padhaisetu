"""PARAMETRIC question generator for maths banks (brief section 7).

Each template takes rng params, computes the answer + 3 plausible distractors
(off-by patterns), emits bilingual text, and stores gen_params for regeneration.
Run:  python data/gen_math.py [--seed 42]
Writes data/qbank/maths_{8,9,10}.json  (12 variants per template).
"""
import argparse
import json
import random
from fractions import Fraction
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "qbank"
VARIANTS = 12


def _fmt_frac(fr: Fraction) -> str:
    fr = Fraction(fr)
    if fr.denominator == 1:
        return str(fr.numerator)
    return f"{fr.numerator}/{fr.denominator}"


def _mk(skill_id, difficulty, text_hi, text_en, answer, distractors,
        hint_hi, hint_en, sol_hi, sol_en, rng, gen_params):
    """Assemble one item; shuffle options; ensure 4 unique options."""
    opts = [answer]
    for d in distractors:
        d = _norm_opt(d)
        if len(opts) >= 4:
            break
        if all(_opt_key(o) != _opt_key(d) for o in opts):
            opts.append(d)
    filler = 0
    while len(opts) < 4:
        cand = _norm_opt(str(answer) + "0" * (filler + 1)) if isinstance(answer, str) else \
            (answer + (filler + 2))
        if all(_opt_key(cand) != _opt_key(o) for o in opts):
            opts.append(cand)
        filler += 1
    correct = opts.index(answer)
    rng.shuffle(opts)
    correct_idx = opts.index(answer)
    return {
        "skill_id": skill_id,
        "difficulty": difficulty,
        "text_hi": text_hi,
        "text_en": text_en,
        "options": [str(o) for o in opts],
        "correct_idx": correct_idx,
        "hint_hi": hint_hi,
        "hint_en": hint_en,
        "solution_hi": sol_hi,
        "solution_en": sol_en,
        "gen_params": gen_params,
    }


def _opt_key(x):
    s = str(x).replace(" ", "")
    try:
        f = Fraction(s)
        return ("f", float(f))
    except Exception:
        return ("s", s)


def _norm_opt(x):
    return x


# ---------------- class 8 templates ----------------

def t_rational_add(rng):
    b, d = rng.choice([(2, 3), (3, 4), (3, 5), (4, 5), (5, 6), (2, 5)])
    a = rng.randint(1, b - 1)
    c = rng.randint(1, d - 1)
    ans = Fraction(a, b) + Fraction(c, d)
    wrong_sum = Fraction(a + c, b + d)
    return _mk(
        "m8c1s1", 1,
        f"{a}/{b} + {c}/{d} = ?",
        f"{a}/{b} + {c}/{d} = ?",
        _fmt_frac(ans),
        [_fmt_frac(wrong_sum), _fmt_frac(ans - Fraction(1, b * d)), _fmt_frac(Fraction(a, b) - Fraction(c, d))],
        "हर समान बनाइए (LCM लें)।",
        "Make denominators equal first (take LCM).",
        f"LCM({b},{d}) पर ले जाकर जोड़ने पर {a}/{b}+{c}/{d} = {_fmt_frac(ans)}।",
        f"Convert to LCM({b},{d}) then add: {a}/{b}+{c}/{d} = {_fmt_frac(ans)}.",
        rng, {"tpl": "rational_add", "a": a, "b": b, "c": c, "d": d},
    )


def t_rational_sub(rng):
    b, d = rng.choice([(2, 3), (3, 4), (4, 5), (5, 6), (3, 8)])
    a = rng.randint(1, b - 1)
    c = rng.randint(1, d - 1)
    ans = Fraction(a, b) - Fraction(c, d)
    return _mk(
        "m8c1s1", 1,
        f"{a}/{b} - {c}/{d} = ?",
        f"{a}/{b} - {c}/{d} = ?",
        _fmt_frac(ans),
        [_fmt_frac(Fraction(a - c, b * d)), _fmt_frac(Fraction(a, b) + Fraction(c, d)), _fmt_frac(-ans) if ans != 0 else "0/1"],
        "पहले हर समान कीजिए, फिर घटाइए।",
        "Equalise denominators first, then subtract.",
        f"{a}/{b}-{c}/{d} को LCM हर पर लिखकर घटाने पर {_fmt_frac(ans)} मिलता है।",
        f"Writing {a}/{b}-{c}/{d} over the LCM and subtracting gives {_fmt_frac(ans)}.",
        rng, {"tpl": "rational_sub", "a": a, "b": b, "c": c, "d": d},
    )


def t_linear_eq(rng):
    x = rng.randint(2, 12)
    a = rng.randint(2, 6)
    b = rng.randint(-9, 9)
    c = a * x + b
    return _mk(
        "m8c2s1", 1,
        f"x निकालिए: {a}x {'+' if b >= 0 else '-'} {abs(b)} = {c}",
        f"Solve for x: {a}x {'+' if b >= 0 else '-'} {abs(b)} = {c}",
        str(x),
        [str(x + 1), str(x - 1), str(-x)],
        f"{b:+d} दूसरी ओर भेजिए, फिर {a} से भाग दीजिए।".replace("+-", "-"),
        f"Move {abs(b)} to the other side, then divide by {a}.",
        f"{a}x = {c-b}; x = {c-b}/{a} = {x}।",
        f"{a}x = {c-b}; x = {c-b}/{a} = {x}.",
        rng, {"tpl": "linear_eq", "x": x, "a": a, "b": b},
    )


def t_square_root(rng):
    n = rng.randint(11, 40)
    return _mk(
        "m8c5s1", 1,
        f"√{n*n} = ?",
        f"√{n*n} = ?",
        str(n),
        [str(n + 1), str(n - 1), str(n // 2 if n % 2 == 0 else n + 2)],
        "वह संख्या सोचिए जिसका वर्ग दी गई संख्या है।",
        "Think of the number whose square gives this value.",
        f"{n}×{n} = {n*n}, अतः √{n*n} = {n}।",
        f"{n}×{n} = {n*n}, so √{n*n} = {n}.",
        rng, {"tpl": "square_root", "n": n},
    )


def t_cube_value(rng):
    n = rng.randint(2, 10)
    return _mk(
        "m8c6s1", 1,
        f"{n}³ = ?",
        f"{n}³ = ?",
        str(n ** 3),
        [str(n * 3), str(n ** 2), str((n + 1) ** 2)],
        f"{n} को तीन बार गुणा कीजिए।",
        "Multiply the number by itself three times.",
        f"{n}³ = {n}×{n}×{n} = {n**3}।",
        f"{n}³ = {n}×{n}×{n} = {n**3}.",
        rng, {"tpl": "cube_value", "n": n},
    )


def t_percent_of(rng):
    p = rng.choice([5, 10, 15, 20, 25, 30, 40, 60, 75])
    base = rng.choice([40, 60, 80, 120, 150, 200, 240, 300, 400])
    ans = p * base // 100
    return _mk(
        "m8c7s1", 1,
        f"{base} का {p}% कितना है?",
        f"What is {p}% of {base}?",
        str(ans),
        [str(ans + 10), str(max(0, ans - 10)), str(p + base)],
        f"{p}% = {p}/100, फिर {base} से गुणा कीजिए।",
        f"{p}% means {p}/100; multiply by {base}.",
        f"{p}% × {base} = {p}/100 × {base} = {ans}।",
        f"{p}% × {base} = {p}/100 × {base} = {ans}.",
        rng, {"tpl": "percent_of", "p": p, "base": base},
    )


def t_exp_law(rng):
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    x = rng.choice(["x", "y", "a"])
    return _mk(
        "m8c9s1", 1,
        f"{x}^{a} · {x}^{b} = ?",
        f"{x}^{a} · {x}^{b} = ?",
        f"{x}^{a+b}",
        [f"{x}^{a*b}", f"{x}^{max(a,b)-min(a,b)}", f"{x}^{a}^{b}"],
        "समान आधारों के गुणन में घातें जुड़ती हैं।",
        "Same-base products add the exponents.",
        f"{x}^m·{x}^n = {x}^(m+n), अतः {x}^{a+b}।",
        f"{x}^m·{x}^n = {x}^(m+n), hence {x}^{a+b}.",
        rng, {"tpl": "exp_law", "a": a, "b": b},
    )


def t_direct_prop(rng):
    k = rng.randint(3, 9)
    x1 = rng.randint(2, 8)
    y1 = k * x1
    x2 = rng.randint(x1 + 1, x1 + 8)
    ans = k * x2
    return _mk(
        "m8c10s1", 2,
        f"x ∝ y. यदि x={x1} पर y={y1} है, तो x={x2} पर y = ?",
        f"If x is directly proportional to y, and y={y1} when x={x1}, find y when x={x2}.",
        str(ans),
        [str(y1 + x2), str(k + x2), str(ans + k)],
        "पहले k = y/x निकालिए, फिर y = kx लगाइए।",
        "Find k = y/x first, then use y = kx.",
        f"k = {y1}/{x1} = {k}; y = {k}×{x2} = {ans}।",
        f"k = {y1}/{x1} = {k}; y = {k}×{x2} = {ans}.",
        rng, {"tpl": "direct_prop", "k": k, "x1": x1, "y1": y1, "x2": x2},
    )


def t_inverse_prop(rng):
    x1 = rng.randint(2, 8)
    y1 = rng.randint(3, 9)
    k = x1 * y1
    x2 = rng.choice([v for v in range(2, 13) if k % v == 0 and v != x1] or [k])
    ans = k // x2
    return _mk(
        "m8c10s2", 2,
        f"x और y प्रतिलोम समानुपात में हैं। x={x1} पर y={y1}; x={x2} पर y = ?",
        f"x and y are in inverse proportion. If y={y1} when x={x1}, find y when x={x2}.",
        str(ans),
        [str(y1 * x2 // max(x1, 1)), str(y1 + x2), str(abs(y1 - x2))],
        "xy स्थिर रहता है — पहले xy निकालिए।",
        "xy stays constant - compute xy first.",
        f"k = {x1}×{y1} = {k}; y = {k}/{x2} = {ans}।",
        f"k = {x1}×{y1} = {k}; y = {k}/{x2} = {ans}.",
        rng, {"tpl": "inverse_prop", "x1": x1, "y1": y1, "x2": x2},
    )


def t_rect_area_perim(rng):
    l = rng.randint(5, 18)
    w = rng.randint(3, l - 1)
    ask_area = rng.random() < 0.5
    area = l * w
    perim = 2 * (l + w)
    if ask_area:
        return _mk(
            "m8c8s1", 1,
            f"आयत की लंबाई {l} से.मी. व चौड़ाई {w} से.मी. है। क्षेत्रफल = ?",
            f"A rectangle has length {l} cm and width {w} cm. Area = ?",
            f"{area}",
            [str(perim), str(l + w), str(area + w)],
            "क्षेत्रफल = लंबाई × चौड़ाई।",
            "Area = length × width.",
            f"क्षेत्रफल = {l}×{w} = {area} वर्ग से.मी.।",
            f"Area = {l}×{w} = {area} sq cm.",
            rng, {"tpl": "rect_area", "l": l, "w": w},
        )
    return _mk(
        "m8c8s1", 1,
        f"आयत की लंबाई {l} से.मी. व चौड़ाई {w} से.मी. है। परिमाप = ?",
        f"A rectangle has length {l} cm and width {w} cm. Perimeter = ?",
        f"{perim}",
        [str(area), str(l + w), str(perim + 2)],
        "परिमाप = 2(लंबाई + चौड़ाई)।",
        "Perimeter = 2(length + width).",
        f"परिमाप = 2×({l}+{w}) = {perim} से.मी.।",
        f"Perimeter = 2×({l}+{w}) = {perim} cm.",
        rng, {"tpl": "rect_perim", "l": l, "w": w},
    )


def t_factor_common(rng):
    hcf = rng.choice([3, 4, 5, 6, 7, 8, 9])
    m = rng.randint(2, 9)
    n = rng.randint(2, 9)
    while m == n:
        n = rng.randint(2, 9)
    A, B = hcf * m, hcf * n
    ans = f"{hcf}({m}x + {n})"
    return _mk(
        "m8c11s1", 2,
        f"{A}x + {B} के गुणनखंड चुनिए।",
        f"Factorise: {A}x + {B}",
        ans,
        [f"{hcf}({m+n}x)", f"{hcf-1}({m+1}x + {n})", f"{m}({hcf}x + {n*hcf//m})" if (n * hcf) % m == 0 else f"{A}(x + {B/A})"],
        "दोनों पदों का सबसे बड़ा समान गुणनखंड बाहर निकालिए।",
        "Take out the greatest common factor of both terms.",
        f"{A}x+{B} = {hcf}({m}x + {n})।",
        f"{A}x+{B} = {hcf}({m}x + {n}).",
        rng, {"tpl": "factor_common", "A": A, "B": B, "hcf": hcf, "m": m, "n": n},
    )


CLASS8_TEMPLATES = [
    t_rational_add, t_rational_sub, t_linear_eq, t_square_root, t_cube_value,
    t_percent_of, t_exp_law, t_direct_prop, t_inverse_prop, t_rect_area_perim,
    t_factor_common,
]


# ---------------- class 9 templates ----------------

def t_irrational_pick(rng):
    irrationals = ["√7", "√11", "√13", "√15", "√19", "√23"]
    rationals = ["√4", "√9", "√16", "√25", "√36", "0.333...", "22/7", "2/5", "0.75"]
    irr = rng.choice(irrationals)
    r1, r2, r3 = rng.sample(rationals, 3)
    opts = [irr, r1, r2, r3]
    hi = "इनमें से कौन-सी अपरिमेय संख्या है?"
    en = "Which of these is an irrational number?"
    rng.shuffle(opts)
    ci = opts.index(irr)
    return {
        "skill_id": "m9c1s1", "difficulty": 1,
        "text_hi": hi, "text_en": en,
        "options": opts, "correct_idx": ci,
        "hint_hi": "पूर्ण वर्ग का वर्गमूल परिमेय होता है।",
        "hint_en": "Square roots of perfect squares are rational.",
        "solution_hi": f"{irr} को p/q रूप में नहीं लिखा जा सकता, शेष सभी परिमेय हैं।",
        "solution_en": f"{irr} cannot be written as p/q; all others are rational.",
        "gen_params": {"tpl": "irrational_pick", "irr": irr},
    }


def t_neg_exponent(rng):
    b = rng.randint(2, 5)
    e = rng.randint(2, 3)
    mode = rng.random() < 0.5
    if mode:
        ans_val = Fraction(1, b ** e)
        q_hi, q_en = f"{b}^{-e} = ?", f"{b}^{-e} = ?"
        hint_hi, hint_en = "ऋणात्मक घात पर व्युत्क्रम लीजिए।", "Negative power means reciprocal."
        sol_hi = f"{b}^{-e} = 1/{b}^{e} = {_fmt_frac(ans_val)}।"
        sol_en = f"{b}^{-e} = 1/{b}^{e} = {_fmt_frac(ans_val)}."
        gp = {"tpl": "neg_exp_int", "b": b, "e": e}
    else:
        num, den = rng.randint(2, 5), rng.randint(2, 5)
        ans_val = Fraction(den, num) ** e
        q_hi, q_en = f"({num}/{den})^{-e} = ?", f"({num}/{den})^{-e} = ?"
        hint_hi, hint_en = "व्युत्क्रम लें, फिर घात लगाएँ।", "Take reciprocal, then raise to the power."
        sol_hi = f"({num}/{den})^{-e} = ({den}/{num})^{e} = {_fmt_frac(ans_val)}।"
        sol_en = f"({den}/{num})^{e} = {_fmt_frac(ans_val)}."
        gp = {"tpl": "neg_exp_frac", "num": num, "den": den, "e": e}
    ans = _fmt_frac(ans_val)
    if mode:
        dis = [_fmt_frac(-ans_val), f"{b**e}", _fmt_frac(Fraction(1, b))]
        gp_note = None
    else:
        dis = [_fmt_frac(Fraction(num, den) ** e), f"{num**e}/{den**e}", _fmt_frac(Fraction(den, num) ** (e + 1))]
    return _mk("m9c1s4", 2, q_hi, q_en, ans, dis, hint_hi, hint_en, sol_hi, sol_en, rng, gp)


def t_poly_value(rng):
    a = rng.randint(-4, 5)
    b = rng.randint(-6, 6)
    pt = rng.randint(-3, 4)
    val = pt * pt + a * pt + b
    return _mk(
        "m9c2s2", 2,
        f"यदि p(x) = x² {'+' if a>=0 else '-'} {abs(a)}x {'+' if b>=0 else '-'} {abs(b)}, तो p({pt}) = ?",
        f"If p(x) = x² {'+' if a>=0 else '-'} {abs(a)}x {'+' if b>=0 else '-'} {abs(b)}, find p({pt}).",
        str(val),
        [str(val + pt), str(pt*pt + a*pt - b), str(pt + a + b)],
        "x की जगह मान रखकर हल कीजिए।",
        "Substitute the value in place of x and simplify.",
        f"p({pt}) = {pt*pt} {'+' if a*pt>=0 else '-'} {abs(a*pt)} {'+' if b>=0 else '-'} {abs(b)} = {val}।",
        f"p({pt}) = {pt*pt} {'+' if a*pt>=0 else '-'} {abs(a*pt)} {'+' if b>=0 else '-'} {abs(b)} = {val}.",
        rng, {"tpl": "poly_value", "a": a, "b": b, "pt": pt},
    )


def t_lin_pair_solve(rng):
    x = rng.randint(-5, 9)
    y = rng.randint(-5, 9)
    s = x + y
    df = x - y
    return _mk(
        "m9c3s1", 2,
        f"x + y = {s} और x - y = {df} हो, तो x = ?",
        f"If x + y = {s} and x - y = {df}, find x.",
        str(x),
        [str(y), str(s), str(df)],
        "दोनों समीकरण जोड़िए।",
        "Add the two equations.",
        f"जोड़ने पर 2x = {s+df}; x = {(s+df)//2} = {x}।",
        f"Adding: 2x = {s+df}; x = {(s+df)//2} = {x}.",
        rng, {"tpl": "lin_pair", "x": x, "y": y},
    )


def t_quadrant_fixed(rng):
    x, y = rng.randint(1, 9), rng.randint(1, 9)
    sx, sy = rng.choice([1, -1]), rng.choice([1, -1])
    px, py = sx * x, sy * y
    quad = {(1, 1): 1, (-1, 1): 2, (-1, -1): 3, (1, -1): 4}[(sx, sy)]
    labels = [("I", "I"), ("II", "II"), ("III", "III"), ("IV", "IV")]
    correct_label = ["I", "II", "III", "IV"][quad - 1]
    opts = ["I", "II", "III", "IV"]
    return {
        "skill_id": "m9c4s1", "difficulty": 1,
        "text_hi": f"बिंदु ({px}, {py}) किस चतुर्थांश में है?",
        "text_en": f"Which quadrant does the point ({px}, {py}) lie in?",
        "options": opts, "correct_idx": quad - 1,
        "hint_hi": "(+,+) I | (−,+) II | (−,−) III | (+,−) IV",
        "hint_en": "(+,+) QI | (-,+) QII | (-,-) QIII | (+,-) QIV",
        "solution_hi": f"x={'धनात्मक' if px>0 else 'ऋणात्मक'}, y={'धनात्मक' if py>0 else 'ऋणात्मक'} → चतुर्थांश {correct_label}",
        "solution_en": f"x is {'positive' if px>0 else 'negative'}, y is {'positive' if py>0 else 'negative'} -> Quadrant {correct_label}",
        "gen_params": {"tpl": "quadrant", "x": px, "y": py},
    }


def t_triangle_angle(rng):
    a = rng.randint(25, 80)
    b = rng.randint(25, 170 - a)
    c = 180 - a - b
    while c <= 0:
        a, b = rng.randint(20, 70), rng.randint(20, 60)
        c = 180 - a - b
    return _mk(
        "m9c5s1", 1,
        f"एक त्रिभुज के दो कोण {a}° और {b}° हैं। तीसरा कोण = ?",
        f"Two angles of a triangle are {a}° and {b}°. The third angle = ?",
        f"{c}°",
        [f"{c+2}°", f"{a+b}°", f"{90}°"],
        "त्रिभुज के कोणों का योग 180° होता है।",
        "Angles of a triangle sum to 180°.",
        f"तीसरा कोण = 180° − ({a}°+{b}°) = {c}°।",
        f"Third angle = 180° - ({a}°+{b}°) = {c}°.",
        rng, {"tpl": "triangle_angle", "a": a, "b": b},
    )


def t_heron_area(rng):
    fam = rng.choice([(3, 4, 5), (6, 8, 10), (5, 12, 13), (9, 12, 15), (7, 24, 25)])
    a, b, c = fam
    s = (a + b + c) / 2
    area2 = int(s * (s - a) * (s - b) * (s - c))
    area = int(area2 ** 0.5)
    return _mk(
        "m9c6s1", 2,
        f"उन भुजाओं वाले त्रिभुज का क्षेत्रफल ज्ञात कीजिए: {a}, {b}, {c} (इकाई)।",
        f"Find the area of a triangle with sides {a}, {b}, {c} units.",
        str(area),
        [str(int(s)), str(area * 2), str(a * b)],
        "हीरोन सूत्र: A = √(s(s−a)(s−b)(s−c)), s = अर्धपरिमाप।",
        "Heron: A = sqrt(s(s-a)(s-b)(s-c)), s = semi-perimeter.",
        f"s = {(a+b+c)}/2 = {int(s)}; A = √({int(s)}×{int(s)-a}×{int(s)-b}×{int(s)-c}) = {area}।",
        f"s = {(a+b+c)}/2 = {int(s)}; A = sqrt({int(s)}x{int(s)-a}x{int(s)-b}x{int(s)-c}) = {area}.",
        rng, {"tpl": "heron", "a": a, "b": b, "c": c},
    )


def t_cylinder_volume(rng):
    r = rng.choice([7, 14, 21])
    h = rng.randint(3, 15)
    vol = Fraction(22, 7) * r * r * h
    return _mk(
        "m9c7s3", 2,
        f"π = 22/7 लेते हुए, r = {r} से.मी., h = {h} से.मी. वाले बेलन का आयतन = ?",
        f"Taking π = 22/7, find the volume of a cylinder with r = {r} cm and h = {h} cm.",
        f"{int(vol)}",
        [str(int(vol) * 2), str(int(vol / 2)), str(r * h)],
        "V = πr²h।",
        "V = pi*r^2*h.",
        f"V = (22/7)×{r}×{r}×{h} = {int(vol)} घन से.मी.।",
        f"V = (22/7)x{r}x{r}x{h} = {int(vol)} cubic cm.",
        rng, {"tpl": "cyl_vol", "r": r, "h": h},
    )


def t_mean_raw(rng):
    xs = [rng.randint(2, 30) for _ in range(5)]
    mean = sum(xs) / len(xs)
    if mean != int(mean):
        xs[-1] += 5 - int(sum(xs)) % 5 if sum(xs) % 5 else 0
        mean = sum(xs) / len(xs)
    while mean != int(mean):
        xs[-1] += 1
        mean = sum(xs) / len(xs)
    return _mk(
        "m9c8s1", 1,
        f"{', '.join(map(str, xs))} का माध्य (औसत) = ?",
        f"Find the mean of: {', '.join(map(str, xs))}",
        str(int(mean)),
        [str(int(mean) + 1), str(int(mean) - 1), str(sum(xs))],
        "माध्य = सभी मानों का योग ÷ संख्या।",
        "Mean = sum of values divided by count.",
        f"योग = {sum(xs)}; माध्य = {sum(xs)}/5 = {int(mean)}।",
        f"Sum = {sum(xs)}; mean = {sum(xs)}/5 = {int(mean)}.",
        rng, {"tpl": "mean_raw", "xs": xs},
    )


CLASS9_TEMPLATES = [
    t_irrational_pick, t_neg_exponent, t_poly_value, t_lin_pair_solve,
    t_quadrant_fixed, t_triangle_angle, t_heron_area, t_cylinder_volume, t_mean_raw,
]


# ---------------- class 10 templates ----------------

def t_hcf(rng):
    a = rng.randint(12, 60)
    b = rng.randint(12, 60)
    def hcf(x, y):
        while y:
            x, y = y, x % y
        return x
    h = hcf(a, b)
    while h == 1 or a == b:
        a, b = rng.randint(12, 60), rng.randint(12, 60)
        h = hcf(a, b)
        if h > 1 and a != b:
            break
    return _mk(
        "m10c1s1", 2,
        f"{a} और {b} का महत्तम समापवर्तक (HCF) = ?",
        f"HCF of {a} and {b} = ?",
        str(h),
        [str(hcf(a, b) + 1), str(h * 2), str(abs(a - b))],
        "अभाज्य गुणनखंड निकालकर सामान्य गुणनखंडों का गुणनफल लीजिए।",
        "Prime factorise and multiply common factors.",
        f"{a}, {b} के सामान्य अभाज्य गुणनखंडों का गुणनफल HCF = {h} है।",
        f"Common prime factors of {a} and {b} give HCF = {h}.",
        rng, {"tpl": "hcf", "a": a, "b": b},
    )


def t_quad_roots(rng):
    r1 = rng.randint(-7, 8)
    r2 = rng.randint(-7, 8)
    while r2 == r1:
        r2 = rng.randint(-7, 8)
    big, small = max(r1, r2), min(r1, r2)
    B = -(r1 + r2)
    C = r1 * r2
    ask = rng.random() < 0.5
    if ask:
        return _mk(
            "m10c3s1", 2,
            f"x² {'+' if B>=0 else '-'} {abs(B)}x {'+' if C>=0 else '-'} {abs(C)} = 0 का बड़ा मूल = ?",
            f"The larger root of x² {'+' if B>=0 else '-'} {abs(B)}x {'+' if C>=0 else '-'} {abs(C)} = 0 is ?",
            str(big),
            [str(small), str(B), str(big + 1)],
            "गुणनखंड कीजिए: (x−p)(x−q) रूप सोचिए।",
            "Factorise: think of the form (x-p)(x-q).",
            f"गुणनखंड से मूल {r1}, {r2} मिलते हैं; बड़ा मूल {big} है।",
            f"Factorising gives roots {r1} and {r2}; larger root is {big}.",
            rng, {"tpl": "quad_roots", "r1": r1, "r2": r2},
        )
    return _mk(
        "m10c2s2", 2,
        f"x² {'+' if B>=0 else '-'} {abs(B)}x {'+' if C>=0 else '-'} {abs(C)} = 0 के मूलों का योग = ?",
        f"Sum of roots of x² {'+' if B>=0 else '-'} {abs(B)}x {'+' if C>=0 else '-'} {abs(C)} = 0 is ?",
        str(r1 + r2),
        [str(C), str(-(r1 + r2)), str(r1 + r2 + 1)],
        "मूलों का योग = −b/a।",
        "Sum of roots = -b/a.",
        f"a=1, b={B} → योग = −({B})/1 = {r1+r2}।",
        f"a=1, b={B} -> sum = -({B}) = {r1+r2}.",
        rng, {"tpl": "root_sum", "r1": r1, "r2": r2},
    )


def t_discriminant(rng):
    a = 1
    r1 = rng.randint(-6, 6)
    d = rng.choice(["pos", "zero", "neg"])
    if d == "pos":
        r2 = rng.randint(-6, 6)
        while r2 == r1:
            r2 = rng.randint(-6, 6)
        b = -(r1 + r2); c = r1 * r2
        D = b * b - 4 * a * c
        ans_hi, ans_en = "दो भिन्न वास्तविक मूल", "two distinct real roots"
    elif d == "zero":
        r = rng.randint(-6, 6)
        b = -2 * r; c = r * r
        D = 0
        ans_hi, ans_en = "दो बराबर वास्तविक मूल", "two equal real roots"
    else:
        b = rng.randint(-6, 6)
        c = (b * b // 4) + rng.randint(1, 6)
        D = b * b - 4 * a * c
        while D >= 0:
            c = (b * b // 4) + rng.randint(1, 6)
            D = b * b - 4 * a * c
        ans_hi, ans_en = "कोई वास्तविक मूल नहीं", "no real roots"
    return _mk(
        "m10c3s2", 2,
        f"D = b²−4ac ज्ञात किए बिना बताइए — x² {'+' if b>=0 else '-'} {abs(b)}x {'+' if c>=0 else '-'} {abs(c)} = 0 के मूलों की प्रकृति?",
        f"Without computing D = b²-4ac, state the nature of roots of x² {'+' if b>=0 else '-'} {abs(b)}x {'+' if c>=0 else '-'} {abs(c)} = 0.",
        ans_hi,
        ["दो भिन्न वास्तविक मूल", "दो बराबर वास्तविक मूल", "कोई वास्तविक मूल नहीं"],
        "D>0 → भिन्न वास्तविक; D=0 → बराबर; D<0 → वास्तविक नहीं।",
        "D>0 distinct real; D=0 equal real; D<0 no real roots.",
        f"D = {b*b} − 4×1×{c} = {D} → {ans_hi} ({ans_en})।",
        f"D = {b*b} - 4x1x{c} = {D} -> {ans_en}.",
        rng, {"tpl": "discriminant", "b": b, "c": c},
    )


def t_ap_nth(rng):
    a = rng.randint(2, 12)
    d = rng.randint(2, 9)
    n = rng.randint(5, 20)
    an = a + (n - 1) * d
    return _mk(
        "m10c4s2", 2,
        f"AP: a = {a}, d = {d} हो तो {n} वाँ पद = ?",
        f"In an AP with a = {a} and d = {d}, find the {n}th term.",
        str(an),
        [str(a + n * d), str(a + (n - 2) * d), str(an + d)],
        "an = a + (n−1)d।",
        "an = a + (n-1)d.",
        f"a{n} = {a} + ({n}−1)×{d} = {an}।",
        f"a(n) = {a} + ({n}-1)x{d} = {an}.",
        rng, {"tpl": "ap_nth", "a": a, "d": d, "n": n},
    )


def t_ap_sum(rng):
    a = rng.randint(1, 10)
    d = rng.randint(2, 7)
    n = rng.randint(6, 15)
    sn = n * (2 * a + (n - 1) * d) // 2
    while n * (2 * a + (n - 1) * d) % 2:
        n += 1
        sn = n * (2 * a + (n - 1) * d) // 2
    return _mk(
        "m10c4s3", 3,
        f"AP {a}, {a+d}, {a+2*d}, ... के पहले {n} पदों का योग = ?",
        f"Find the sum of the first {n} terms of the AP {a}, {a+d}, {a+2*d}, ...",
        str(sn),
        [str(sn + n), str(sn - d), str(n * (a + d))],
        "Sn = n/2 [2a + (n−1)d]।",
        "Sn = n/2 [2a + (n-1)d].",
        f"Sn = {n}/2 × [2×{a} + {n-1}×{d}] = {sn}।",
        f"Sn = {n}/2 x [2x{a} + {n-1}x{d}] = {sn}.",
        rng, {"tpl": "ap_sum", "a": a, "d": d, "n": n},
    )


def t_trig_values(rng):
    combos = [
        ("sin30° + cos60°", "sin30° + cos60°", Fraction(1, 2) + Fraction(1, 2)),
        ("tan45° × sin90°", "tan45° x sin90°", Fraction(1)),
        ("cos0° + sin0°", "cos0° + sin0°", Fraction(1)),
        ("sin30° × cos30°", "sin30° x cos30°", Fraction(3, 4)),
        ("tan45° + cot45°", "tan45° + cot45°", Fraction(2)),
        ("cos60° + sin30°", "cos60° + sin30°", Fraction(1)),
    ]
    label_hi, label_en, val = rng.choice(combos)
    return _mk(
        "m10c5s1", 1,
        f"मान ज्ञात कीजिए: {label_hi}",
        f"Evaluate: {label_en}",
        _fmt_frac(val),
        [_fmt_frac(val + 1), _fmt_frac(Fraction(1, 2)), _fmt_frac(Fraction(3, 2))],
        "मानक कोणों की सारणी याद कीजिए।",
        "Recall the standard-angle table.",
        f"{label_en} = {_fmt_frac(val)}।",
        f"{label_en} = {_fmt_frac(val)}.",
        rng, {"tpl": "trig_values", "label": label_en},
    )


def t_trig_identity(rng):
    which = rng.choice(["sq", "sec"])
    if which == "sq":
        return _mk(
            "m10c5s3", 2,
            "sin²θ + cos²θ = ?",
            "sin²θ + cos²θ = ?",
            "1",
            ["0", "2", "θ"],
            "मूल त्रिकोणमितीय सर्वसमिका याद कीजिए।",
            "Recall the fundamental trigonometric identity.",
            "sin²θ+cos²θ = 1 (सभी θ के लिए)।",
            "sin^2(theta)+cos^2(theta) = 1 for all theta.",
            rng, {"tpl": "trig_sq"},
        )
    return _mk(
        "m10c5s3", 2,
        "sec²θ − tan²θ = ?",
        "sec²θ − tan²θ = ?",
        "1",
        ["0", "-1", "2"],
        "1 + tan²θ = sec²θ से रूपांतरित कीजिए।",
        "Rearrange 1 + tan²(theta) = sec²(theta).",
        "sec²θ−tan²θ = 1।",
        "sec^2(theta)-tan^2(theta) = 1.",
        rng, {"tpl": "trig_sec"},
    )


def t_distance(rng):
    dx, dy = rng.choice([(3, 4), (6, 8), (5, 12), (8, 15), (9, 12), (7, 24)])
    x1, y1 = rng.randint(-5, 5), rng.randint(-5, 5)
    dist = int((dx * dx + dy * dy) ** 0.5)
    return _mk(
        "m10c6s1", 2,
        f"बिंदुओं ({x1}, {y1}) और ({x1+dx}, {y1+dy}) के बीच की दूरी = ?",
        f"Distance between ({x1}, {y1}) and ({x1+dx}, {y1+dy}) = ?",
        str(dist),
        [str(dist + 1), str(dx + dy), str(dist * 2)],
        "d = √((Δx)²+(Δy)²)।",
        "d = sqrt(dx² + dy²).",
        f"d = √({dx}²+{dy}²) = √{dx*dx+dy*dy} = {dist}।",
        f"d = sqrt({dx*dx+dy*dy}) = {dist}.",
        rng, {"tpl": "distance", "dx": dx, "dy": dy},
    )


def t_grouped_mean(rng):
    xs = sorted(rng.sample(range(5, 40), 4))
    freqs = [rng.randint(1, 6) for _ in xs]
    total = sum(freqs)
    fx = sum(x * f for x, f in zip(xs, freqs))
    while fx % total != 0:
        freqs[-1] += 1
        total = sum(freqs)
        fx = sum(x * f for x, f in zip(xs, freqs))
    mean = fx / total
    table_hi = ", ".join(f"{x}×{f}" for x, f in zip(xs, freqs))
    return _mk(
        "m10c7s1", 3,
        f"मान व बारंबारता: {table_hi}। माध्य = ?",
        f"Values & frequencies: {table_hi}. Mean = ?",
        f"{mean:g}",
        [f"{mean+1:g}", f"{mean-1:g}", f"{sum(xs)//4}"],
        "माध्य = Σfx / Σf।",
        "Mean = sum(fx) / sum(f).",
        f"Σfx = {fx}, Σf = {total} → माध्य = {mean:g}।",
        f"sum fx = {fx}, sum f = {total} -> mean = {mean:g}.",
        rng, {"tpl": "grouped_mean", "xs": xs, "freqs": freqs},
    )


def t_prob_die(rng):
    target = rng.choice([4, 5, 6, 7, 8, 9, 10])
    count = sum(1 for i in range(1, 7) for j in range(1, 7) if i + j == target)
    ans = f"{count}/36"
    return _mk(
        "m10c8s2", 2,
        f"दो पासे एक साथ फेंके जाते हैं। योग {target} आने की प्रायिकता = ?",
        f"Two dice are thrown together. Probability that the sum is {target} = ?",
        ans,
        [f"{count+1}/36", f"{max(1,count-1)}/36", f"1/{target}" if target <= 6 else f"6/36"],
        "36 सम-प्रायिक परिणाम गिनिए।",
        "Count favourable outcomes out of 36 equally likely results.",
        f"योग {target}: {count} अनुकूल परिणाम → {ans}।",
        f"Sum {target}: {count} favourable outcomes -> {ans}.",
        rng, {"tpl": "prob_die", "target": target},
    )


CLASS10_TEMPLATES = [
    t_hcf, t_quad_roots, t_discriminant, t_ap_nth, t_ap_sum,
    t_trig_values, t_trig_identity, t_distance, t_grouped_mean, t_prob_die,
]

TEMPLATES = {8: CLASS8_TEMPLATES, 9: CLASS9_TEMPLATES, 10: CLASS10_TEMPLATES}


def generate_class(cls: int, seed: int = 42) -> list[dict]:
    items: list[dict] = []
    seen_texts: set[tuple] = set()
    for tpl in TEMPLATES[cls]:
        made = 0
        attempts = 0
        while made < VARIANTS and attempts < VARIANTS * 12:
            attempts += 1
            rng = random.Random(seed + cls * 10000 + id(tpl) % 9973 + attempts)
            item = tpl(rng)
            key = (item["skill_id"], item["text_en"], item["options"][item["correct_idx"]])
            if key in seen_texts:
                continue
            seen_texts.add(key)
            items.append(item)
            made += 1
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for cls in (8, 9, 10):
        items = generate_class(cls, args.seed)
        path = OUT_DIR / f"maths_{cls}.json"
        path.write_text(
            json.dumps({
                "subject": "maths",
                "grade": cls,
                "generator": f"gen_math.py seed={args.seed}",
                "items": items,
            }, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"maths_{cls}.json: {len(items)} items")


if __name__ == "__main__":
    main()
