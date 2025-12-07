from src.scraper.trustpilot_scraper import scrape_trustpilot_page
from src.utils.cleaning import save_reviews

BASE_URL = "https://fr.trustpilot.com/review/boursobank.com"

if __name__ == "__main__":
    reviews = scrape_trustpilot_page(BASE_URL)
    print(f"Nombre d'avis récupérés : {len(reviews)}")
    save_reviews(reviews, filename="reviews_trustpilot.json")

