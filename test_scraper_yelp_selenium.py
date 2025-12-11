# test_scraper_yelp_selenium.py

from src.scraper.yelp_selenium_scraper import scrape_yelp_reviews_selenium


def main():
    # Mets ici une vraie URL Yelp d'un établissement
    # Par exemple (à tester, ou remplace par un resto que tu connais) :
    business_url = "https://www.yelp.fr/biz/le-petit-cler-paris"

    max_pages = 10  # commence par 1 page

    df = scrape_yelp_reviews_selenium(
        business_url=business_url,
        max_pages=max_pages,
        sleep_between=3.0,
        headless=True,
    )

    print("Scraping terminé")
    print("Nombre d'avis récupérés :", len(df))
    print(df.head())

    output_file = "yelp_reviews_selenium_page1.csv"
    df.to_csv(output_file, index=False)
    print(f"CSV sauvegardé : {output_file}")


if __name__ == "__main__":
    main()
