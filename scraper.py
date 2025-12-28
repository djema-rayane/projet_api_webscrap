# ========================================
# FILE 1: scraper.py
# ========================================

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os
import re
from datetime import datetime


class AmazonReviewScraper:
    """
    Scraper Amazon (FR) - Gestion complète du scraping
    """

    def __init__(self, profile_dir="~/.selenium_profiles/amazon", headless=False, wait_seconds=15):
        """
        Initialise le scraper avec les bonnes pratiques Selenium
        
        Args:
            profile_dir: dossier pour stocker le profil Chrome
            headless: True = mode invisible, False = voir le navigateur
            wait_seconds: temps max d'attente pour les éléments
        """
        self.options = webdriver.ChromeOptions()
        
        # Arguments de stabilité
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        
        # Profil persistant
        self.profile_path = os.path.expanduser(profile_dir)
        self.options.add_argument(f"--user-data-dir={self.profile_path}")
        self.options.add_argument("--profile-directory=Default")
        
        # Mode headless si demandé
        if headless:
            self.options.add_argument("--headless=new")
        
        # Lancer Chrome
        self.driver = webdriver.Chrome(options=self.options)
        self.wait = WebDriverWait(self.driver, wait_seconds)
        
        # Callback pour mettre à jour la progression (sera défini par l'API)
        self.progress_callback = None

    def set_progress_callback(self, callback):
        """Définir une fonction de callback pour la progression"""
        self.progress_callback = callback

    def _update_progress(self, message):
        """Mise à jour de la progression"""
        if self.progress_callback:
            self.progress_callback(message)

    def accept_cookies_if_present(self):
        """Accepte les cookies si la popup apparaît"""
        try:
            button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "sp-cc-accept"))
            )
            button.click()
            time.sleep(1)
            self._update_progress("Cookies acceptés")
        except TimeoutException:
            pass

    def open_amazon(self):
        """Ouvrir Amazon France"""
        self._update_progress("Ouverture d'Amazon.fr")
        self.driver.get("https://www.amazon.fr")
        self.accept_cookies_if_present()

    def search(self, query: str):
        """Rechercher un produit"""
        self._update_progress(f"Recherche de '{query}'")
        
        search_bar = self.wait.until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
        )
        
        search_bar.clear()
        search_bar.send_keys(query)
        search_bar.send_keys(Keys.RETURN)
        time.sleep(2)
        
        self._update_progress("Résultats affichés")

    def count_products_on_page(self):
        """Compter le nombre de produits sur la page actuelle"""
        products = self.driver.find_elements(
            By.CSS_SELECTOR, 
            "div.a-section.puis-padding-left-small.puis-padding-right-small"
        )
        if len(products) == 0:
            products = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "div[data-component-type='s-search-result']"
            )
        return len(products)

    def click_next_page(self):
        """Cliquer sur le bouton 'Suivant'"""
        self._update_progress("Passage à la page suivante...")
        
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        next_button_selectors = [
            "a.s-pagination-next",
            "a[aria-label='Aller à la page suivante']",
            ".s-pagination-next",
        ]
        
        for selector in next_button_selectors:
            try:
                next_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                
                classes = next_button.get_attribute("class") or ""
                if "disabled" in classes or "s-pagination-disabled" in classes:
                    self._update_progress("Dernière page atteinte")
                    return False
                
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(1)
                next_button.click()
                time.sleep(3)
                
                try:
                    self.wait.until(
                        EC.presence_of_all_elements_located(
                            (By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
                        )
                    )
                    self._update_progress("Page suivante chargée")
                    return True
                except TimeoutException:
                    return False
                
            except (NoSuchElementException, Exception):
                continue
        
        return False

    def extract_brand(self):
        """Extraire la marque du produit"""
        brand = "Marque non disponible"
        
        try:
            # Méthode 1: Structure a-span3 / a-span9
            label_elements = self.driver.find_elements(By.CSS_SELECTOR, "span.a-span3")
            for label_elem in label_elements:
                label_text = label_elem.text.strip().lower()
                if "marque" in label_text or "brand" in label_text:
                    try:
                        parent_row = label_elem.find_element(By.XPATH, "../..")
                        value_elem = parent_row.find_element(By.CSS_SELECTOR, "span.a-span9")
                        brand = value_elem.text.strip()
                        if brand:
                            return brand
                    except:
                        continue
            
            # Méthode 2: Extraction depuis l'URL
            current_url = self.driver.current_url
            url_brand_match = re.search(r'/([^/]+)/dp/', current_url)
            if url_brand_match:
                potential_brand = url_brand_match.group(1)
                potential_brand = potential_brand.replace('-', ' ').title()
                if len(potential_brand) > 2:
                    brand = potential_brand
                    return brand
            
        except Exception:
            pass
        
        return brand

    def click_product_reviews(self, product_index=1):
        """Cliquer sur le lien des avis d'un produit"""
        self._update_progress(f"Accès aux avis du produit #{product_index}")
        
        time.sleep(3)
        
        max_attempts = 3
        products = []
        
        for attempt in range(max_attempts):
            try:
                self.driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(0.5)
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
                
                products = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    "div.a-section.puis-padding-left-small.puis-padding-right-small"
                )
                
                if len(products) == 0:
                    products = self.driver.find_elements(
                        By.CSS_SELECTOR, 
                        "div[data-component-type='s-search-result']"
                    )
                
                if len(products) > 0:
                    break
                    
            except Exception:
                time.sleep(2)
        
        if len(products) == 0:
            raise Exception("Aucun produit trouvé")
        
        if product_index > len(products):
            raise Exception(f"Produit #{product_index} n'existe pas")
        
        product = products[product_index - 1]
        
        # Extraire le titre
        product_title = "Titre non disponible"
        try:
            title_block = product.find_element(By.CSS_SELECTOR, "div[data-cy='title-recipe']")
            title_element = title_block.find_element(By.CSS_SELECTOR, "h2")
            product_title = title_element.text.strip()
            if not product_title:
                title_span = title_element.find_element(By.TAG_NAME, "span")
                product_title = title_span.text.strip()
        except NoSuchElementException:
            try:
                title_element = product.find_element(By.CSS_SELECTOR, "h2")
                product_title = title_element.text.strip()
            except:
                pass
        
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", product)
        time.sleep(1)
        
        # Trouver et cliquer sur le lien des avis
        try:
            review_block = None
            try:
                review_block = product.find_element(By.CSS_SELECTOR, "div[data-cy='reviews-block']")
            except NoSuchElementException:
                pass
            
            if review_block:
                review_links = review_block.find_elements(By.CSS_SELECTOR, "a")
                for link in review_links:
                    try:
                        href = link.get_attribute("href")
                        text = link.text
                        
                        if href and ("customerReviews" in href or "product-reviews" in href):
                            if re.search(r'\d+', text):
                                self.driver.execute_script("arguments[0].click();", link)
                                time.sleep(3)
                                self._update_progress(f"Page des avis ouverte: {product_title[:50]}")
                                return product_title
                    except:
                        continue
            
            # Fallback
            review_links = product.find_elements(By.CSS_SELECTOR, "a")
            for link in review_links:
                try:
                    href = link.get_attribute("href")
                    text = link.text
                    
                    if href and ("customerReviews" in href or "product-reviews" in href):
                        if re.search(r'\d+', text):
                            self.driver.execute_script("arguments[0].click();", link)
                            time.sleep(3)
                            self._update_progress(f"Page des avis ouverte: {product_title[:50]}")
                            return product_title
                except:
                    continue
            
            raise NoSuchElementException("Aucun lien d'avis valide")
            
        except NoSuchElementException:
            raise Exception(f"Aucun lien d'avis trouvé pour le produit #{product_index}")

    def go_back(self):
        """Revenir à la page de résultats"""
        self._update_progress("Retour à la page de résultats")
        self.driver.back()
        time.sleep(3)
        
        try:
            self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
                )
            )
        except TimeoutException:
            time.sleep(2)

    def extract_reviews(self, france_only=True, limit=None):
        """Extraire les avis de la page"""
        self._update_progress("Extraction des avis en cours...")
        
        time.sleep(3)
        
        review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "div[data-hook='review']")
        if not review_blocks:
            review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "[data-hook='review']")
        
        if not review_blocks:
            return []
        
        reviews = []
        skipped = 0
        
        for review_block in review_blocks:
            try:
                # Profil
                profile_name = "Anonyme"
                try:
                    profile_element = review_block.find_element(By.CSS_SELECTOR, "span.a-profile-name")
                    profile_name = profile_element.text.strip()
                except NoSuchElementException:
                    try:
                        profile_element = review_block.find_element(By.CSS_SELECTOR, "div.a-profile-content span")
                        profile_name = profile_element.text.strip()
                    except:
                        pass
                
                # Date
                date_element = review_block.find_element(By.CSS_SELECTOR, "span[data-hook='review-date']")
                date_full = date_element.text
                
                if france_only and "France" not in date_full:
                    skipped += 1
                    continue
                
                date_clean = re.search(r"le\s+(.+)$", date_full)
                date_clean = date_clean.group(1) if date_clean else date_full
                
                # Étoiles
                star_element = None
                star_text = ""
                star_value = None
                
                try:
                    star_element = review_block.find_element(By.CSS_SELECTOR, "i.a-icon-star")
                except NoSuchElementException:
                    try:
                        star_element = review_block.find_element(By.CSS_SELECTOR, "i[data-hook='review-star-rating']")
                    except NoSuchElementException:
                        try:
                            star_element = review_block.find_element(By.CSS_SELECTOR, "i[data-hook='cmps-review-star-rating']")
                        except:
                            pass
                
                if star_element:
                    try:
                        star_span = star_element.find_element(By.TAG_NAME, "span")
                        star_text = star_span.text or star_span.get_attribute("textContent")
                        
                        if star_text:
                            star_match = re.search(r"(\d+[,.]?\d*)", star_text)
                            if star_match:
                                star_value = float(star_match.group(1).replace(",", "."))
                    except:
                        pass
                
                # Titre de l'avis
                review_title = ""
                try:
                    title_element = review_block.find_element(By.CSS_SELECTOR, "a[data-hook='review-title']")
                    review_title = title_element.text.strip()
                    review_title = re.sub(r"^\d+[,.]?\d*\s+étoiles?\s+sur\s+5\s*", "", review_title)
                except NoSuchElementException:
                    try:
                        title_element = review_block.find_element(By.CSS_SELECTOR, "span[data-hook='review-title']")
                        review_title = title_element.text.strip()
                        review_title = re.sub(r"^\d+[,.]?\d*\s+étoiles?\s+sur\s+5\s*", "", review_title)
                    except:
                        pass
                
                # Contenu
                content_element = review_block.find_element(By.CSS_SELECTOR, "span[data-hook='review-body']")
                content = content_element.text.strip()
                
                reviews.append({
                    "numero": len(reviews) + 1,
                    "profil": profile_name,
                    "titre_review": review_title,
                    "etoiles": star_text,
                    "etoiles_valeur": star_value,
                    "date": date_clean,
                    "contenu": content
                })
                
                if limit and len(reviews) >= limit:
                    break
                    
            except Exception:
                continue
        
        self._update_progress(f"{len(reviews)} avis extraits")
        return reviews

    def scrape_multiple_products(self, query, nb_products, france_only=True, limit_per_product=None):
        """
        Fonction principale - Scrape plusieurs produits
        
        Args:
            query: ce qu'on cherche
            nb_products: nombre de produits à scraper
            france_only: ne garder que les avis français
            limit_per_product: nombre max d'avis par produit
        """
        try:
            self.open_amazon()
            self.search(query)
            
            nb_products_on_page = self.count_products_on_page()
            self._update_progress(f"{nb_products_on_page} produits sur la page")
            
            all_products_data = []
            total_scraped = 0
            i = 1
            
            while total_scraped < nb_products:
                try:
                    if i > nb_products_on_page:
                        if self.click_next_page():
                            nb_products_on_page = self.count_products_on_page()
                            i = 1
                        else:
                            self._update_progress(f"Limite atteinte - {total_scraped} produits")
                            break
                    
                    self._update_progress(f"Produit {total_scraped + 1}/{nb_products} (#{i} sur la page)")
                    
                    accessed_reviews_page = False
                    
                    try:
                        product_title = self.click_product_reviews(product_index=i)
                        accessed_reviews_page = True
                        
                        brand = self.extract_brand()
                        reviews = self.extract_reviews(france_only=france_only, limit=limit_per_product)
                        
                        product_data = {
                            "produit_numero": total_scraped + 1,
                            "titre": product_title,
                            "marque": brand,
                            "url": self.driver.current_url,
                            "nb_avis_extraits": len(reviews),
                            "avis": reviews
                        }
                        all_products_data.append(product_data)
                        
                        total_scraped += 1
                        i += 1
                        
                        if total_scraped < nb_products:
                            self.go_back()
                            
                    except Exception as e:
                        self._update_progress(f"Erreur produit #{i}: {str(e)[:50]}")
                        if accessed_reviews_page:
                            try:
                                self.go_back()
                            except:
                                pass
                        i += 1
                        continue
                    
                except Exception:
                    i += 1
                    continue
            
            total_reviews = sum(p["nb_avis_extraits"] for p in all_products_data)
            
            result = {
                "type": query,
                "date_extraction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "filtre_france": france_only,
                "nb_produits_demandes": nb_products,
                "nb_produits_scrapes": len(all_products_data),
                "total_avis_extraits": total_reviews,
                "produits": all_products_data
            }
            
            self._update_progress(f"Terminé: {len(all_products_data)} produits, {total_reviews} avis")
            return result
            
        finally:
            self.driver.quit()