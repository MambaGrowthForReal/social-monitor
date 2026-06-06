import json

RELEVANCE_WORDS = [
    "weight", "loss", "fat", "pounds", "slim", "ozempic", "mounjaro",
    "belly", "diet", "lose", "burn", "melt", "calories", "obesity",
    "overweight", "glp", "tirzepatide", "semaglutide", "bariatric",
    "metaboli", "appetite", "hunger", "crave", "slimming",
]

def is_relevant(text):
    t = text.lower()
    return any(w in t for w in RELEVANCE_WORDS)

with open("data/2026-06-04.json", encoding="utf-8") as f:
    data = json.load(f)

ads = data.get("facebook", [])
kept = [a for a in ads if is_relevant(a.get("texto", ""))]
removed = [a for a in ads if not is_relevant(a.get("texto", ""))]

print(f"Total FB ads today : {len(ads)}")
print(f"Relevant (kept)    : {len(kept)}")
print(f"Irrelevant (removed): {len(removed)}")
print()
print("Sample removed ads:")
for a in removed[:8]:
    page = a.get("page", "")[:30]
    texto = a.get("texto", "")[:90]
    pais = a.get("pais", "")
    print(f"  [{pais}] {page:<30} | {texto}")
