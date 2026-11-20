"""Medicine search over the catalog (names in Uzbek and Russian, INN, aliases) and brand <-> generic analogs.

A brand is found by its own name and, a little lower, by its active ingredient (INN); a generic is found by the
INN. Analogs are other products with the same INN, dose and form.
"""

from __future__ import annotations

from .text import MAX_QUERY, word_score, words

LIMIT = 8
INN_PENALTY = 3  # a brand found only through its ingredient ranks below the generic itself


def med_keys(med: dict) -> tuple[list[list[str]], list[list[str]]]:
    """(own names, ingredient names) of a medicine, each as a list of word-key lists."""
    own = [words(med["name"]["uz"]), words(med["name"]["ru"])] + [words(a) for a in med.get("aliases", [])]
    inn = [words(med["inn"])]
    if med.get("brand"):
        return own, inn
    return own + inn, []


def name_score(query: list[str], name: list[str]) -> int | None:
    """Every query word must match a different word of the name. Lower is better."""
    total = 0
    used: set[int] = set()
    for q in query:
        best: tuple[int, int] | None = None
        for i, w in enumerate(name):
            if i in used:
                continue
            s = word_score(q, w)
            if s is not None and (best is None or s < best[0]):
                best = (s, i)
        if best is None:
            return None
        total += best[0]
        used.add(best[1])
    return total


def med_score(query: list[str], med: dict) -> int | None:
    own, inn = med_keys(med)
    scores = [s for s in (name_score(query, n) for n in own) if s is not None]
    scores += [s + INN_PENALTY for s in (name_score(query, n) for n in inn) if s is not None]
    return min(scores) if scores else None


def search(meds: list[dict], text: str, limit: int = LIMIT) -> list[dict]:
    """Medicines matching ``text``, best first: [{"id", "score"}]. Digits in the query (a dose) must appear in it."""
    text = (text or "")[:MAX_QUERY]
    query = [w for w in words(text) if not w.isdigit()]
    digits = [w for w in words(text) if w.isdigit()]
    if not query or sum(len(q) for q in query) < 2:
        return []
    hits = []
    for med in meds:
        if digits and not all(d in words(med["strength"]) for d in digits):
            continue
        score = med_score(query, med)
        if score is not None:
            hits.append({"id": med["id"], "score": score, "_brand": 1 if med.get("brand") else 0})
    hits.sort(key=lambda h: (h["score"], h["_brand"], h["id"]))
    return [{"id": h["id"], "score": h["score"]} for h in hits[:limit]]


def analogs(meds: list[dict], med_id: str) -> list[str]:
    """Other products with the same active ingredient, dose and form (ids, catalog order)."""
    base = next((m for m in meds if m["id"] == med_id), None)
    if base is None:
        return []
    return [m["id"] for m in meds if m["id"] != med_id and m["inn"] == base["inn"]
            and m["strength"] == base["strength"] and m["form"] == base["form"]]


def cheaper_analogs(meds: list[dict], med_id: str, min_price: dict[str, int]) -> list[dict]:
    """Analogs whose lowest price in stock is below this medicine's lowest price: the "arzonroq analog" label.

    ``min_price`` maps medicine id -> lowest available price (missing = not in stock anywhere nearby).
    """
    own = min_price.get(med_id)
    out = []
    for aid in analogs(meds, med_id):
        p = min_price.get(aid)
        if p is not None and (own is None or p < own):
            out.append({"id": aid, "price": p, "saving": (own - p) if own is not None else 0})
    out.sort(key=lambda a: (a["price"], a["id"]))
    return out
