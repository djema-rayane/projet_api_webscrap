import requests
from bs4 import BeautifulSoup

lang = "fr"
url = f"https://fr.trustpilot.com/review/carhartt-wip.com?languages={lang}&sort=recency"

r = requests.get(url)
print("Status code:", r.status_code)
print("Longueur HTML:", len(r.text))

soup = BeautifulSoup(r.text, "html.parser")
reviews = soup.find_all("article", class_="styles_reviewCard__hcAvl")
print("Nombre de <article styles_reviewCard__hcAvl> trouvés :", len(reviews))
