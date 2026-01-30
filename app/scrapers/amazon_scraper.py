from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

import time
import os
import re
import random
import pickle
from pathlib import Path
from datetime import datetime


class AmazonReviewScraper:
    """
    Scraper Amazon (FR) - Version FULL
    - Anti-détection + comportement "human-like"
    - Cookies persistants (save/load/clear)
    - Insertion directe en BDD pendant le scraping
    - Modes:
        * SEARCH: scrape_multiple_products(query,...)
        * URL: scrape_single_product_by_url(product_url,...)
        * URL_AUTH: scrape_product_reviews_auth(product_url, username, password, ...)
    """

    def __init__(
        self,
        profile_dir=None,
        headless=False,
        wait_seconds=15,
        cookies_file: str | None = None,
        db_session=None,  
    ):
        self.options = webdriver.ChromeOptions()

        self.options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option("useAutomationExtension", False)

        # Options de base
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-session-crashed-bubble")
        self.options.add_argument("--disable-restore-session-state")
        self.options.add_argument("--disable-infobars")

        # Profil optionnel
        if profile_dir:
            self.profile_path = os.path.expanduser(profile_dir)
            self.options.add_argument(f"--user-data-dir={self.profile_path}")
            self.options.add_argument("--profile-directory=Default")

        if headless:
            self.options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=self.options)

        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.navigator.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR','fr','en-US','en'] });
                """
            },
        )

        self.wait = WebDriverWait(self.driver, wait_seconds)
        self.progress_callback = None

        # Cookies file (persistant)
        self.cookies_file = Path(cookies_file) if cookies_file else Path("amazon_session_cookies.pkl")
        self._session_bootstrapped = False
        
        self.db_session = db_session
        self.session_scraping = None
        self.produit_actuel = None
        self.avis_count = 0

    def _random_sleep(self, min_seconds=1.0, max_seconds=3.0):
        time.sleep(random.uniform(min_seconds, max_seconds))

    def _human_like_type(self, element, text, min_delay=0.1, max_delay=0.3):
        element.clear()
        self._random_sleep(0.3, 0.7)

        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))
            if random.random() < 0.1:
                time.sleep(random.uniform(0.5, 1.5))

    def _move_to_element_human_like(self, element):
        actions = ActionChains(self.driver)

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
            element,
        )
        self._random_sleep(0.5, 1.0)

        actions.move_to_element(element).perform()
        self._random_sleep(0.3, 0.7)

    def _human_click(self, element):
        self._move_to_element_human_like(element)
        self._random_sleep(0.2, 0.5)
        element.click()
        self._random_sleep(0.5, 1.0)

    def set_progress_callback(self, callback):
        self.progress_callback = callback

    def _update_progress(self, message: str):
        if self.progress_callback:
            self.progress_callback(message)

    def _log(self, message: str):
        if self.progress_callback:
            self.progress_callback(message)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def set_db_session(self, db_session, session_scraping):
        """Configure la session BDD pour insertion directe"""
        self.db_session = db_session
        self.session_scraping = session_scraping

    def _insert_avis_direct(self, review_data: dict, source: str = "amazon"):
        """Insère un avis directement en BDD pendant le scraping"""
        if not self.db_session or not self.session_scraping or not self.produit_actuel:
            return
        
        from app.crud import inserer_avis
        
        try:
            inserer_avis(
                db=self.db_session,
                session_id=self.session_scraping.id,
                produit_id=self.produit_actuel.id,
                source=source,
                numero=self.avis_count + 1,
                profil=review_data.get("profil"),
                titre_review=review_data.get("titre_review"),
                contenu=review_data.get("contenu"),
                etoiles=review_data.get("etoiles"),
                etoiles_valeur=review_data.get("etoiles_valeur"),
                date_avis=review_data.get("date"),
            )
            self.avis_count += 1
            
            # Progress tous les 10 avis
            if self.avis_count % 10 == 0:
                self._log(f"⚡ {self.avis_count} avis insérés en temps réel")
        
        except Exception as e:
            self._log(f"Erreur insertion avis: {e}")

    def debug_current_page(self):
        try:
            url = self.driver.current_url
        except Exception:
            url = "N/A"
        try:
            title = self.driver.title
        except Exception:
            title = "N/A"
        self._log(f"DEBUG Page: {url}")
        self._log(f"DEBUG Titre: {title[:80]}")

    def accept_cookies_if_present(self):
        try:
            button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "sp-cc-accept"))
            )
            button.click()
            time.sleep(1)
            self._update_progress("Cookies acceptés")
        except TimeoutException:
            pass

    def save_cookies(self):
        """Sauvegarder TOUS les cookies Amazon après connexion réussie."""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, "wb") as f:
                pickle.dump(cookies, f)
            self._log(f"{len(cookies)} cookies sauvegardés dans {self.cookies_file}")

            important_cookies = {"session-id", "ubid-acbfr", "x-acbfr", "at-acbfr"}
            for cookie in cookies:
                if cookie.get("name") in important_cookies:
                    self._log(f"   → Cookie clé: {cookie.get('name')}")

        except Exception as e:
            self._log(f"Erreur sauvegarde cookies: {e}")

    def load_cookies(self) -> bool:
        """
        Charger les cookies Amazon depuis le fichier.
        IMPORTANT: être sur amazon.fr AVANT add_cookie.
        """
        try:
            if not self.cookies_file.exists():
                self._log("ℹAucun fichier de cookies trouvé")
                return False

            with open(self.cookies_file, "rb") as f:
                cookies = pickle.load(f)

            if not cookies:
                self._log("Fichier de cookies vide")
                return False

            self._log(f"{len(cookies)} cookies trouvés dans le fichier")

            loaded_count = 0
            for cookie in cookies:
                try:
                    cookie_clean = {
                        "name": cookie["name"],
                        "value": cookie["value"],
                        "domain": cookie.get("domain", ".amazon.fr"),
                        "path": cookie.get("path", "/"),
                    }
                    if "sameSite" in cookie:
                        cookie_clean["sameSite"] = cookie["sameSite"]
                    if "secure" in cookie:
                        cookie_clean["secure"] = cookie["secure"]

                    self.driver.add_cookie(cookie_clean)
                    loaded_count += 1
                except Exception as e:
                    self._log(f"Cookie '{cookie.get('name','?')}' non chargé: {e}")

            self._log(f"{loaded_count}/{len(cookies)} cookies chargés")
            return loaded_count > 0

        except Exception as e:
            self._log(f"Erreur chargement cookies: {e}")
            return False

    def clear_cookies(self):
        """Supprimer le fichier de cookies (pour forcer une nouvelle connexion)."""
        try:
            if self.cookies_file.exists():
                self.cookies_file.unlink()
                self._log(f"Cookies supprimés: {self.cookies_file}")
            else:
                self._log("ℹAucun fichier de cookies à supprimer")
        except Exception as e:
            self._log(f"Erreur suppression cookies: {e}")

    def is_logged_in(self) -> bool:
        """Vérifier si connecté Amazon (texte UI + fallback cookies session)."""
        try:
            account_element = self.driver.find_element(By.ID, "nav-link-accountList-nav-line-1")
            text = (account_element.text or "").strip().lower()

            if "identifiez-vous" in text or "hello, sign in" in text:
                self._log("Non connecté (bouton 'Identifiez-vous' détecté)")
                return False

            self._log(f"Connecté! Message: '{text}'")
            return True

        except NoSuchElementException:
            # fallback cookies session
            try:
                cookies = self.driver.get_cookies()
                session_names = {"session-id", "ubid-acbfr", "x-acbfr"}
                session_cookies = [c for c in cookies if c.get("name") in session_names]
                if session_cookies:
                    self._log(f"Cookies de session détectés ({len(session_cookies)})")
                    return True
                self._log("Aucun cookie de session trouvé")
                return False
            except Exception:
                self._log("Impossible de vérifier le statut de connexion")
                return False

    def _check_error_box_text(self, selectors, keywords):
        for selector in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                txt = (el.text or "").strip()
                if txt and any(k in txt.lower() for k in keywords):
                    return True, txt
            except NoSuchElementException:
                continue
            except Exception:
                continue
        return False, None

    def login_manual(self, username: str, password: str) -> bool:
        """
        Connexion Amazon avec anti-détection "human-like".
        """
        try:
            self._log("Début de la connexion...")

            # Aller sur Amazon.fr
            self.driver.get("https://www.amazon.fr")
            self._random_sleep(2.0, 4.0)
            self.accept_cookies_if_present()
            self._random_sleep(1.0, 2.0)

            # Clic sur compte
            self._log("1️Clic sur 'Bonjour, Identifiez-vous'")
            account_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "nav-link-accountList"))
            )
            self._human_click(account_button)
            self._random_sleep(2.0, 3.5)

            # Email
            self._log("2️Saisie email")
            email_field = self.wait.until(EC.presence_of_element_located((By.ID, "ap_email")))
            self._human_click(email_field)
            self._random_sleep(0.5, 1.0)
            self._human_like_type(email_field, username, min_delay=0.08, max_delay=0.25)
            self._random_sleep(0.8, 1.5)

            current_value = email_field.get_attribute("value")
            if current_value != username:
                self._log(f"Texte saisi différent : '{current_value}' vs '{username}' (retry)")
                email_field.clear()
                self._random_sleep(0.5, 1.0)
                self._human_like_type(email_field, username, min_delay=0.1, max_delay=0.3)
                self._random_sleep(0.5, 1.0)

            continue_button = self.wait.until(EC.element_to_be_clickable((By.ID, "continue")))
            current_url = self.driver.current_url
            self._human_click(continue_button)

            # Attendre page password / erreur email
            start = time.time()
            while time.time() - start < 15:
                try:
                    self.driver.find_element(By.ID, "ap_password")
                    break
                except NoSuchElementException:
                    pass

                has_error, msg = self._check_error_box_text(
                    selectors=[
                        "div.a-alert-error",
                        "#auth-error-message-box",
                        "div.a-box-inner.a-alert-container",
                    ],
                    keywords=[
                        "incorrect", "introuvable", "invalide",
                        "erreur", "problème", "n'existe pas",
                    ],
                )
                if has_error:
                    self._log(f"Erreur email: {msg}")
                    return False

                if self.driver.current_url != current_url:
                    pass

                time.sleep(0.5)

            # Password
            self._log("3️Saisie mot de passe (mode humain)")
            password_field = self.wait.until(EC.presence_of_element_located((By.ID, "ap_password")))
            self._human_click(password_field)
            self._random_sleep(0.5, 1.0)
            self._human_like_type(password_field, password, min_delay=0.08, max_delay=0.25)
            self._random_sleep(1.0, 2.0)

            current_url_pw = self.driver.current_url
            password_field.send_keys(Keys.RETURN)
            self._random_sleep(2.0, 4.0)

            # Vérification login / erreur password
            start = time.time()
            while time.time() - start < 15:
                if self.driver.current_url != current_url_pw and "/ap/signin" not in self.driver.current_url:
                    break
                if self.is_logged_in():
                    break

                has_error, msg = self._check_error_box_text(
                    selectors=[
                        "div.a-alert-error",
                        "#auth-error-message-box",
                        "div.a-box-inner.a-alert-container",
                    ],
                    keywords=[
                        "incorrect", "invalide", "erreur",
                        "problème", "mot de passe", "password", "réessayer",
                    ],
                )
                if has_error:
                    self._log(f"Erreur password: {msg}")
                    return False

                time.sleep(0.5)

            time.sleep(2)
            ok = self.is_logged_in()
            if ok:
                self._log("CONNEXION RÉUSSIE")
                self.save_cookies()
            else:
                self._log("ÉCHEC CONNEXION (vérif finale)")
            return ok

        except Exception as e:
            self._log(f"ERREUR login_manual: {e}")
            import traceback
            self._log(traceback.format_exc())
            return False

    # Alias compat: certains de tes anciens appels utilisent login()
    def login(self, username: str, password: str) -> bool:
        return self.login_manual(username, password)

    def ensure_logged_in(
        self,
        username: str | None = None,
        password: str | None = None,
        cookies_only: bool = False,
    ) -> bool:
        """
        - Tente cookies si fichier présent.
        - Si cookies_only=True : ne tente jamais de login manuel.
        - Sinon : fallback login manuel si creds fournis.
        """
        try:
            self._log("=" * 60)
            self._log("VÉRIFICATION AUTHENTIFICATION AMAZON")
            self._log("=" * 60)

            # Bootstrap domaine obligatoire avant add_cookie
            if not getattr(self, "_session_bootstrapped", False):
                self._log("0️Bootstrap amazon.fr")
                self.driver.get("https://www.amazon.fr")
                time.sleep(2)
                self.accept_cookies_if_present()
                self._session_bootstrapped = True

            # 1) Essai cookies
            if self.cookies_file.exists():
                self._log("1️Cookies détectés → tentative session via cookies")
                cookies_loaded = self.load_cookies()

                if cookies_loaded:
                    self._log("   → Refresh")
                    self.driver.refresh()
                    time.sleep(3)

                    # Petit wait header (évite faux négatif)
                    try:
                        WebDriverWait(self.driver, 8).until(
                            EC.presence_of_element_located((By.ID, "nav-link-accountList-nav-line-1"))
                        )
                    except Exception:
                        pass

                    if self.is_logged_in():
                        self._log("CONNECTÉ VIA COOKIES")
                        return True

                self._log("Cookies présents mais session non validée")

                if cookies_only:
                    self._log("cookies_only=True → pas de login manuel")
                    return False

            else:
                self._log("ℹAucun fichier cookies → login requis")

            # 2) Fallback login manuel
            if cookies_only:
                self._log("cookies_only=True → pas de login manuel")
                return False

            if not username or not password:
                self._log("Identifiants manquants")
                return False

            self._log("2️Fallback login manuel…")
            ok = self.login_manual(username, password)
            if ok:
                self._log("Login OK → sauvegarde cookies")
                self.save_cookies()
                return True

            self._log("Login manuel échoué")
            return False

        except Exception as e:
            self._log(f"Erreur ensure_logged_in: {e}")
            return False

    def set_cookies(self, cookies: dict):
        """
        Injecter des cookies (dict) dans la session.
        Note: il faut être sur le domaine amazon.fr avant add_cookie.
        """
        self.driver.get("https://www.amazon.fr")
        time.sleep(2)
        self.accept_cookies_if_present()
        for name, value in cookies.items():
            try:
                self.driver.add_cookie({"name": name, "value": value, "domain": ".amazon.fr"})
            except Exception:
                continue
        self.driver.refresh()
        time.sleep(2)

    # =========================================================
    # AMAZON NAV (Search mode)
    # =========================================================
    def open_amazon(self):
        self._update_progress("Ouverture d'Amazon.fr")
        self.driver.get("https://www.amazon.fr")
        self.accept_cookies_if_present()

    def search(self, query: str):
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
        products = self.driver.find_elements(
            By.CSS_SELECTOR,
            "div.a-section.puis-padding-left-small.puis-padding-right-small",
        )
        if len(products) == 0:
            products = self.driver.find_elements(
                By.CSS_SELECTOR,
                "div[data-component-type='s-search-result']",
            )
        return len(products)

    def click_next_page(self):
        self._update_progress("Passage à la page suivante...")
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)

        try:
            next_button = self.driver.find_element(By.CSS_SELECTOR, "a.s-pagination-next")

            classes = next_button.get_attribute("class") or ""
            if "s-pagination-disabled" in classes:
                self._update_progress("Dernière page atteinte")
                return False

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                next_button,
            )
            time.sleep(1)
            next_button.click()

            self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
                )
            )

            self._update_progress("Page suivante chargée")
            return True

        except NoSuchElementException:
            self._update_progress("Bouton page suivante introuvable")
            return False

    # =========================================================
    # Product data extraction
    # =========================================================
    def extract_brand(self):
        """Extraire la marque du produit"""
        brand = "Marque non disponible"

        try:
            product_overview = self.driver.find_element(By.ID, "productOverview_feature_div")
            rows = product_overview.find_elements(By.CSS_SELECTOR, "tr.a-spacing-small")

            for row in rows:
                try:
                    label_td = row.find_element(By.CSS_SELECTOR, "td.a-span3")
                    label_text = label_td.text.strip().lower()

                    if "marque" in label_text or "brand" in label_text:
                        value_td = row.find_element(By.CSS_SELECTOR, "td.a-span9")
                        brand = value_td.text.strip()

                        if brand:
                            return brand
                except Exception:
                    continue
        except Exception:
            pass

        return brand

    def extract_product_title(self):
        """Extraire le titre du produit (compatible mode recherche et URL)"""
        product_title = "Titre non disponible"

        try:
            title_element = self.driver.find_element(By.ID, "productTitle")
            product_title = title_element.text.strip()
            if product_title:
                return product_title
        except NoSuchElementException:
            pass

        try:
            title_element = self.driver.find_element(By.CSS_SELECTOR, "h1 span")
            product_title = title_element.text.strip()
            if product_title:
                return product_title
        except Exception:
            pass

        return product_title

    def click_product_reviews(self, product_index=1):
        self._update_progress(f"Accès aux avis du produit #{product_index}")
        time.sleep(3)

        max_attempts = 3
        products = []

        for _ in range(max_attempts):
            try:
                self.driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(0.5)
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)

                products = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "div.a-section.puis-padding-left-small.puis-padding-right-small",
                )

                if len(products) == 0:
                    products = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "div[data-component-type='s-search-result']",
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
            except Exception:
                pass

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            product,
        )
        time.sleep(1)

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
                            if re.search(r"\d+", text):
                                self.driver.execute_script("arguments[0].click();", link)
                                time.sleep(3)
                                self._update_progress(f"Page des avis ouverte: {product_title[:50]}")
                                return product_title
                    except Exception:
                        continue

            # Fallback
            review_links = product.find_elements(By.CSS_SELECTOR, "a")
            for link in review_links:
                try:
                    href = link.get_attribute("href")
                    text = link.text

                    if href and ("customerReviews" in href or "product-reviews" in href):
                        if re.search(r"\d+", text):
                            self.driver.execute_script("arguments[0].click();", link)
                            time.sleep(3)
                            self._update_progress(f"Page des avis ouverte: {product_title[:50]}")
                            return product_title
                except Exception:
                    continue

            raise NoSuchElementException("Aucun lien d'avis valide")
        except NoSuchElementException:
            raise Exception(f"Aucun lien d'avis trouvé pour le produit #{product_index}")

    def go_back(self):
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

    # =========================================================
    # Reviews extraction (base)
    # =========================================================
    def extract_reviews(self, france_only=True, limit=None, insert_db=True):
        """
        Extrait les avis ET les insère directement si BDD configurée
        
        CHANGEMENT : insert_db=True par défaut si db_session existe
        """
        self._update_progress("Extraction des avis en cours...")
        time.sleep(3)

        review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "div[data-hook='review']")
        if not review_blocks:
            review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "[data-hook='review']")

        if not review_blocks:
            self._update_progress("Aucun bloc d'avis trouvé sur la page")
            return []

        self._update_progress(f"{len(review_blocks)} avis détectés sur la page")

        reviews = []
        skipped = 0

        for review_block in review_blocks:
            if limit and len(reviews) >= limit:
                break
                
            try:
                profile_name = "Anonyme"
                try:
                    profile_element = review_block.find_element(By.CSS_SELECTOR, "span.a-profile-name")
                    profile_name = profile_element.text.strip()
                except NoSuchElementException:
                    try:
                        profile_element = review_block.find_element(By.CSS_SELECTOR, "div.a-profile-content span")
                        profile_name = profile_element.text.strip()
                    except Exception:
                        pass

                date_element = review_block.find_element(By.CSS_SELECTOR, "span[data-hook='review-date']")
                date_full = date_element.text

                if france_only and "France" not in date_full:
                    skipped += 1
                    continue

                date_clean = re.search(r"le\s+(.+)$", date_full)
                date_clean = date_clean.group(1) if date_clean else date_full

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
                        except Exception:
                            pass

                if star_element:
                    try:
                        star_span = star_element.find_element(By.TAG_NAME, "span")
                        star_text = star_span.text or star_span.get_attribute("textContent")

                        if star_text:
                            star_match = re.search(r"(\d+[,.]?\d*)", star_text)
                            if star_match:
                                star_value = float(star_match.group(1).replace(",", "."))
                    except Exception:
                        pass

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
                    except Exception:
                        pass

                content_element = review_block.find_element(By.CSS_SELECTOR, "span[data-hook='review-body']")
                content = content_element.text.strip()

                review_data = {
                    "numero": len(reviews) + 1,
                    "profil": profile_name,
                    "titre_review": review_title,
                    "etoiles": star_text,
                    "etoiles_valeur": star_value,
                    "date": date_clean,
                    "contenu": content,
                }
                
                # INSERTION DIRECTE EN BDD
                if insert_db and self.db_session:
                    self._insert_avis_direct(review_data)
                
                reviews.append(review_data)

            except Exception:
                continue

        self._update_progress(f"{len(reviews)} avis extraits")
        return reviews

    # =========================================================
    # MODE URL (base)
    # =========================================================
    def scrape_single_product_by_url(self, product_url, france_only=True, limit=None):
        """
        MODE URL: Scrape un seul produit à partir de son URL Amazon
        Extrait les avis DIRECTEMENT depuis la page produit (section "Commentaires")
        """
        try:
            self._update_progress(f"Accès au produit: {product_url}")
            self.driver.get(product_url)

            self.accept_cookies_if_present()
            time.sleep(3)

            product_title = self.extract_product_title()
            self._update_progress(f"Produit: {product_title[:50]}...")

            brand = self.extract_brand()
            self._update_progress("Chargement de la section des avis...")

            for i in range(3):
                scroll_position = (i + 1) * (self.driver.execute_script("return document.body.scrollHeight") // 3)
                self.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                time.sleep(1)

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            reviews = self.extract_reviews(france_only=france_only, limit=limit)

            if reviews and len(reviews) < 5:
                self._update_progress(f"Seulement {len(reviews)} avis visibles sur la page produit")
            elif not reviews:
                self._update_progress("Aucun avis trouvé sur cette page")

            result = {
                "type": "single_product",
                "titre": product_title,
                "marque": brand,
                "url": product_url,
                "date_extraction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "filtre_france": france_only,
                "nb_avis_extraits": len(reviews) if reviews else 0,
                "avis": reviews if reviews else [],
            }

            self._update_progress(f"Terminé: {len(reviews) if reviews else 0} avis extraits de la page produit")
            return result

        finally:
            self.driver.quit()

    # =========================================================
    # MODE SEARCH (base)
    # =========================================================
    def scrape_multiple_products(self, query, nb_products, france_only=True, limit_per_product=None):
        """
        MODE RECHERCHE: Scrape plusieurs produits via une recherche
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
                            "avis": reviews,
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
                            except Exception:
                                pass
                        i += 1
                        continue
                except Exception:
                    i += 1
                    continue

            total_reviews = sum(p["nb_avis_extraits"] for p in all_products_data)

            result = {
                "type": "multiple_products",
                "query": query,
                "date_extraction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "filtre_france": france_only,
                "nb_produits_demandes": nb_products,
                "nb_produits_scrapes": len(all_products_data),
                "total_avis_extraits": total_reviews,
                "produits": all_products_data,
            }

            self._update_progress(f"Terminé: {len(all_products_data)} produits, {total_reviews} avis")
            return result

        finally:
            self.driver.quit()

    # =========================================================
    # ===============  AJOUTS URL_AUTH (auth)  =================
    # =========================================================
    def click_voir_plus_commentaires(self) -> bool:
        """Cliquer sur 'Voir plus de commentaires' / lien vers page complète des avis"""
        try:
            self._log("Recherche du lien 'Voir plus de commentaires'")
            selectors = [
                "a[data-hook='see-all-reviews-link-foot']",
                "a.a-link-emphasis[href*='customerReviews']",
                "a[href*='product-reviews']",
            ]

            for selector in selectors:
                try:
                    link = self.driver.find_element(By.CSS_SELECTOR, selector)
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                    time.sleep(1)
                    # clic human-like (plus safe)
                    try:
                        self._human_click(link)
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", link)
                    time.sleep(3)
                    self._log("Page complète des avis ouverte")
                    return True
                except NoSuchElementException:
                    continue

            self._log("Lien vers la page complète des avis introuvable")
            return False

        except Exception as e:
            self._log(f"Erreur clic 'voir plus': {e}")
            return False

    def click_traduire_commentaires(self) -> bool:
        """Cliquer sur 'Traduire tous les commentaires en français' (si disponible)"""
        try:
            time.sleep(2)
            selectors = [
                "span[data-action='cr-translate-reviews']",
                "a[data-hook='cr-translate-reviews-link']",
                "span.a-declarative[data-action='cr-translate-reviews']",
            ]

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if "traduire" in (el.text or "").lower():
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", el)
                            time.sleep(3)
                            self._log("Traduction activée")
                            return True
                except Exception:
                    continue

            # Fallback brut
            try:
                spans = self.driver.find_elements(By.TAG_NAME, "span")
                for s in spans:
                    if "traduire tous les commentaires" in (s.text or "").lower():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", s)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", s)
                        time.sleep(3)
                        self._log("Traduction activée (fallback)")
                        return True
            except Exception:
                pass

            self._log("ℹBouton traduction introuvable (peut-être déjà en FR)")
            return True

        except Exception as e:
            self._log(f"Erreur traduction: {e}")
            return True

    def extract_reviews_from_page_auth(self, france_only=False, insert_db=True):
        """
        Extrait les avis depuis la page complète (mode auth)
        AVEC insertion directe
        """
        try:
            time.sleep(3)

            review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "div[data-hook='review']")
            if not review_blocks:
                review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "[data-hook='review']")
            if not review_blocks:
                review_blocks = self.driver.find_elements(By.CSS_SELECTOR, "div.review")
            if not review_blocks:
                review_blocks = self.driver.find_elements(By.CSS_SELECTOR, ".review-views .review")

            if not review_blocks:
                self._log("Aucun bloc d'avis trouvé")
                return []

            self._log(f"{len(review_blocks)} avis détectés")

            reviews = []
            skipped = 0

            for review_block in review_blocks:
                try:
                    # Profil
                    profile_name = "Anonyme"
                    for sel in ["span.a-profile-name", "div.a-profile-content span", ".a-profile-name"]:
                        try:
                            profile_name = review_block.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if profile_name:
                                break
                        except Exception:
                            pass

                    # Date
                    date_full = ""
                    for sel in ["span[data-hook='review-date']", ".review-date"]:
                        try:
                            date_full = review_block.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if date_full:
                                break
                        except Exception:
                            pass

                    if france_only and date_full and "France" not in date_full:
                        skipped += 1
                        continue

                    date_clean = date_full
                    if date_full:
                        m = re.search(r"le\s+(.+)$", date_full)
                        if m:
                            date_clean = m.group(1)

                    # Étoiles
                    star_text = ""
                    star_value = None
                    star_element = None
                    for sel in [
                        "i.a-icon-star",
                        "i[data-hook='review-star-rating']",
                        "i[data-hook='cmps-review-star-rating']",
                        ".a-icon-star",
                    ]:
                        try:
                            star_element = review_block.find_element(By.CSS_SELECTOR, sel)
                            break
                        except Exception:
                            pass
                    if star_element:
                        try:
                            star_span = star_element.find_element(By.TAG_NAME, "span")
                            star_text = star_span.text or star_span.get_attribute("textContent") or ""
                            m = re.search(r"(\d+[,.]?\d*)", star_text)
                            if m:
                                star_value = float(m.group(1).replace(",", "."))
                        except Exception:
                            pass

                    # Titre
                    review_title = ""
                    for sel in ["a[data-hook='review-title']", "span[data-hook='review-title']", ".review-title"]:
                        try:
                            review_title = review_block.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if review_title:
                                review_title = re.sub(
                                    r"^\d+[,.]?\d*\s+étoiles?\s+sur\s+5\s*",
                                    "",
                                    review_title,
                                )
                                break
                        except Exception:
                            pass

                    # Contenu
                    content = ""
                    for sel in ["span[data-hook='review-body']", ".review-text", ".review-text-content span"]:
                        try:
                            content = review_block.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if content:
                                break
                        except Exception:
                            pass

                    if content or review_title:
                        review_data = {
                            "profil": profile_name,
                            "titre_review": review_title,
                            "etoiles": star_text,
                            "etoiles_valeur": star_value,
                            "date": date_clean,
                            "contenu": content,
                        }
                        
                        if insert_db and self.db_session:
                            self._insert_avis_direct(review_data)
                        
                        reviews.append(review_data)

                except Exception:
                    continue

            if france_only:
                self._log(f"{len(reviews)} avis extraits (ignorés: {skipped})")
            else:
                self._log(f"{len(reviews)} avis extraits (tous pays)")
            return reviews

        except Exception as e:
            self._log(f"Erreur extraction: {e}")
            return []

    def click_next_page_reviews_auth(self) -> bool:
        """Pagination sur la page complète des avis"""
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_button = None
            try:
                next_li = self.driver.find_element(By.CSS_SELECTOR, "li.a-last")
                classes = next_li.get_attribute("class") or ""
                if "a-disabled" in classes:
                    self._log("ℹDernière page d'avis atteinte")
                    return False
                next_button = next_li.find_element(By.TAG_NAME, "a")
            except NoSuchElementException:
                pass

            if not next_button:
                try:
                    all_links = self.driver.find_elements(By.CSS_SELECTOR, ".a-pagination a")
                    for link in all_links:
                        if "suivant" in (link.text or "").lower():
                            next_button = link
                            break
                except Exception:
                    pass

            if not next_button:
                self._log("Bouton 'Suivant' introuvable")
                return False

            current_url = self.driver.current_url
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
            time.sleep(1)
            try:
                self._human_click(next_button)
            except Exception:
                next_button.click()

            start = time.time()
            while time.time() - start < 10:
                if self.driver.current_url != current_url:
                    break
                time.sleep(0.5)

            try:
                WebDriverWait(self.driver, 15).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, ".cr-list-loading"))
                )
            except TimeoutException:
                pass

            time.sleep(3)
            return True

        except Exception as e:
            self._log(f"Erreur pagination avis: {e}")
            return False

    # =========================================================
    # MODE URL_AUTH (public)
    # =========================================================
    def scrape_product_reviews_auth(
        self,
        product_url: str,
        username: str | None = None,
        password: str | None = None,
        limit: int = 30,
        france_only: bool = False,
        cookies_only: bool = False,   
    ):
        """
        MODE URL_AUTH:
        Scraper les avis d'un produit via la page complète des avis.

        - charge cookies si dispo
        - vérifie connexion
        - si pas connecté:
            - si cookies_only=True => stop
            - sinon login manuel (username/password requis)
        - scrape avis avec pagination
        """
        try:
            self._log("=" * 60)
            self._log("SCRAPING AUTHENTIFIE DU PRODUIT (FULL)")
            self._log("=" * 60)

            if not self.ensure_logged_in(
                username=username,
                password=password,
                cookies_only=cookies_only
            ):
                if cookies_only:
                    self._log("Cookies invalides et cookies_only=True → stop")
                else:
                    self._log("Impossible de se connecter (cookies invalides + login KO ou creds manquants)")
                return None

            # Accès produit
            self._log("Accès à la page produit")
            self.driver.get(product_url)
            time.sleep(3)
            self.accept_cookies_if_present()

            self.debug_current_page()

            product_title = self.extract_product_title()
            self._log(f"Produit: {product_title[:60]}")

            brand = self.extract_brand()
            self._log(f"Marque détectée: {brand}")

            # Page avis complète
            if not self.click_voir_plus_commentaires():
                self._log("Impossible d'accéder à la page des avis")
                return None

            self.debug_current_page()

            # Traduction (optionnelle)
            self.click_traduire_commentaires()

            # Scraping paginé
            all_reviews = []
            page = 1
            max_pages = 50

            while len(all_reviews) < limit and page <= max_pages:
                self._log(f"Page {page}")

                page_reviews = self.extract_reviews_from_page_auth(france_only=france_only)
                if not page_reviews:
                    self._log("Aucun avis détecté sur cette page")
                    break

                remaining = limit - len(all_reviews)
                all_reviews.extend(page_reviews[:remaining])

                self._log(f"Total extrait: {len(all_reviews)}/{limit}")

                if len(all_reviews) >= limit:
                    break

                if not self.click_next_page_reviews_auth():
                    self._log("ℹFin de la pagination")
                    break

                page += 1

            # Numérotation
            for i, review in enumerate(all_reviews, 1):
                review["numero"] = i

            result = {
                "type": "authenticated_scraping",
                "titre": product_title,
                "marque": brand,
                "url": product_url,
                "date_extraction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "filtre_france": france_only,
                "limite_demandee": limit,
                "nb_avis_extraits": len(all_reviews),
                "nb_pages_scrapees": page,
                "avis": all_reviews,
            }

            self._log(f"SCRAPING TERMINE: {len(all_reviews)} avis extraits")
            return result

        except Exception as e:
            self._log(f"ERREUR SCRAPING AUTH: {e}")
            return None