# test_scraper_boursobank.py

from src.scraper.trustpilot_scraper import scrape_trustpilot_to_df


def main():
    domain = "boursobank.com"   # <-- ici Boursobank
    lang = "fr"
    max_pages = 1               # mets None pour toutes les pages

    df = scrape_trustpilot_to_df(domain, lang=lang, max_pages=max_pages)

    print("Scraping terminé")
    print(df.head())

    output_file = f"trustpilot_{domain.replace('.', '_')}_{lang}.csv"
    df.to_csv(output_file, index=False)
    print(f"CSV sauvegardé : {output_file}")


if __name__ == "__main__":
    main()
