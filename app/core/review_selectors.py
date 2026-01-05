import json

def load_review_from_scrape_json(json_path: str, product_index: int, review_numero: int) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Single product
    if "avis" in data and "produits" not in data:
        avis_list = data.get("avis", [])
        for avis in avis_list:
            if int(avis.get("numero", -1)) == int(review_numero):
                return {
                    "product_title": data.get("titre", ""),
                    "brand": data.get("marque", "Marque non disponible"),
                    "avis": avis,
                }
        raise ValueError(f"Avis numero={review_numero} introuvable (single_product)")

    # Multi products
    produits = data.get("produits", [])
    if not produits:
        raise ValueError("JSON invalide: aucun produit")

    if product_index < 1 or product_index > len(produits):
        raise ValueError(f"product_index invalide: {product_index} (1..{len(produits)})")

    produit = produits[product_index - 1]
    avis_list = produit.get("avis", [])
    for avis in avis_list:
        if int(avis.get("numero", -1)) == int(review_numero):
            return {
                "product_title": produit.get("titre", ""),
                "brand": produit.get("marque", "Marque non disponible"),
                "avis": avis,
            }

    raise ValueError(f"Avis numero={review_numero} introuvable (multi-produits)")
