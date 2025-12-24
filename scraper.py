import re
import time
import random
import logging
import requests
from dataclasses import dataclass, asdict
from typing import List, Optional, Set, Dict
from urllib.parse import urlparse, urljoin

import pandas as pd
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


# ----------------------------
# Logging
# ----------------------------
logger = logging.getLogger("prod_scraper")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
if not logger.handlers:
    logger.addHandler(_handler)

# ----------------------------
# Data model
# ----------------------------
VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")  # excludes I,O,Q
WS_RE = re.compile(r"\s+")

@dataclass
class VehicleRecord:
    source_url: str
    vin: Optional[str] = None
    stock: Optional[str] = None
    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    price: Optional[str] = None
    mileage: Optional[str] = None
    exterior_color: Optional[str] = None
    interior_color: Optional[str] = None
    transmission: Optional[str] = None
    drivetrain: Optional[str] = None
    engine: Optional[str] = None
    # VIN decoded fields
    vin_make: Optional[str] = None
    vin_model: Optional[str] = None
    vin_year: Optional[str] = None
    vin_trim: Optional[str] = None
    vin_body_style: Optional[str] = None


def clean_text(s: str) -> str:
    return WS_RE.sub(" ", s).strip()

def jitter_sleep(base: float = 1.0, jitter: float = 0.7):
    time.sleep(max(0.1, base + random.uniform(-jitter, jitter)))

def normalize_url(url: str) -> str:
    if not url:
        return url
    return url.split("#")[0].split("?")[0].strip()

def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()

def same_domain(base_url: str, url: str) -> bool:
    return get_domain(base_url) == get_domain(url)

def likely_detail_url(url: str) -> bool:
    """
    STRICT detection - only actual vehicle detail pages
    """
    u = (url or "").lower()
    
    # BLACKLIST - exclude these immediately
    blacklist_patterns = [
        'search', 'inventory/search', 'filter', 'sort',
        'blog', 'news', 'article', 'post',
        'about', 'contact', 'service', 'parts',
        'financing', 'trade', 'appointment',
        'dealer', 'location', 'hours',
        '/new/', '/models/', '/certified-preowned-program',
        'promotion', 'offer', 'special',
        'type/', 'brand/', 'category/',
    ]
    
    for pattern in blacklist_patterns:
        if pattern in u:
            return False
    
    # MUST have ID pattern - this is the key validation
    has_id = bool(re.search(r'-id\d{7,}', u))  # Must have -idXXXXXXX (7+ digits)
    
    # WHITELIST - only these patterns with ID
    if has_id:
        # /used/YEAR-Make-Model-idXXXXXX.html
        if re.search(r'/used/\d{4}-[A-Za-z]+-[A-Za-z]+-id\d+\.html?', u):
            return True
        # /demos/YEAR-Make-Model-idXXXXXX.html
        if re.search(r'/demos?/\d{4}-[A-Za-z]+-[A-Za-z]+-id\d+\.html?', u):
            return True
        # /new/YEAR-Make-Model-idXXXXXX.html
        if re.search(r'/new/\d{4}-[A-Za-z]+-[A-Za-z]+-id\d+\.html?', u):
            return True
    
    # Dealer.com .htm files (very specific)
    if u.endswith('.htm'):
        # Must have year in URL
        if re.search(r'\d{4}', u) and 'search' not in u:
            return True
    
    return False


# ----------------------------
# VIN Decoder (NHTSA API)
# ----------------------------
def decode_vin(vin: str) -> Dict[str, Optional[str]]:
    """
    Decode VIN using NHTSA API
    Returns dict with: make, model, year, trim, body_style
    """
    result = {
        "vin_make": None,
        "vin_model": None,
        "vin_year": None,
        "vin_trim": None,
        "vin_body_style": None
    }
    
    if not vin or len(vin) != 17:
        return result
    
    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "Results" in data:
                results = data["Results"]
                
                # Create lookup dict
                lookup = {item["Variable"]: item["Value"] for item in results if item.get("Value")}
                
                result["vin_make"] = lookup.get("Make")
                result["vin_model"] = lookup.get("Model")
                result["vin_year"] = lookup.get("Model Year")
                result["vin_trim"] = lookup.get("Trim")
                result["vin_body_style"] = lookup.get("Body Class")
                
                logger.info(f"VIN decoded: {vin} -> {result['vin_make']} {result['vin_model']} {result['vin_year']}")
    except Exception as e:
        logger.warning(f"VIN decode failed for {vin}: {e}")
    
    return result


# ----------------------------
# Selenium factory
# ----------------------------
def build_driver(headless: bool = False, block_images: bool = True, page_load_timeout: int = 45) -> webdriver.Chrome:
    opts = Options()

    if headless:
        opts.add_argument("--headless=new")

    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-US,en")

    # UA
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    prefs = {}
    if block_images:
        prefs["profile.managed_default_content_settings.images"] = 2
    opts.add_experimental_option("prefs", prefs)

    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(page_load_timeout)

    # reduce webdriver hint
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass

    return driver


# ----------------------------
# Main Scraper
# ----------------------------
class ProductionVehicleScraper:
    def __init__(
        self,
        inventory_url: str,
        headless: bool = False,
        block_images: bool = True,
        max_scrolls: int = 15,
        scroll_pause: float = 2.5,
        max_pages: int = 10,
        max_links: int = 2000,
        page_load_timeout: int = 45,
    ):
        self.inventory_url = inventory_url
        self.headless = headless
        self.block_images = block_images
        self.max_scrolls = max_scrolls
        self.scroll_pause = scroll_pause
        self.max_pages = max_pages
        self.max_links = max_links

        self.driver = build_driver(headless=headless, block_images=block_images, page_load_timeout=page_load_timeout)

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=12),
        retry=retry_if_exception_type((TimeoutException, WebDriverException, Exception)),
    )
    def load(self, url: str):
        logger.info(f"Loading: {url}")
        self.driver.get(url)

    def detect_platform(self) -> str:
        """
        Detect what platform/CMS the site is using
        """
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        
        # Check for .htm/.html links
        htm_links = [a.get("href", "") for a in soup.select("a[href*='.htm']")]
        if len(htm_links) >= 5:
            return "dealer.com"
        
        # Check for ID-based URLs
        id_links = [a.get("href", "") for a in soup.select("a[href*='-id']")]
        if len(id_links) >= 3:
            return "d2cmedia"
        
        # Fallback
        return "generic"

    def _wait_for_content(self, timeout: int = 10):
        """
        Wait for dynamic content to load
        """
        try:
            # Wait for vehicle cards/listings to appear
            WebDriverWait(self.driver, timeout).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "a[href*='used'], a[href*='demos'], a[href*='vehicle'], a[href*='.htm']")) > 0
            )
            logger.info("✓ Content loaded")
        except TimeoutException:
            logger.warning("⚠ Timeout waiting for content")

    def _scroll_aggressive(self):
        """
        More aggressive scrolling with multiple passes and waits
        """
        logger.info("Starting aggressive scroll...")
        
        # Initial wait for content
        self._wait_for_content()
        
        # Multiple scroll passes
        for pass_num in range(2):
            logger.info(f"Scroll pass {pass_num + 1}/2")
            last_h = 0
            
            for i in range(self.max_scrolls):
                h = self.driver.execute_script("return document.body.scrollHeight")
                if h == last_h and i > 3:
                    break
                last_h = h
                
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                jitter_sleep(self.scroll_pause, 0.8)
                
                # Also scroll to middle to trigger lazy loading
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
                jitter_sleep(0.5, 0.2)
                
            # Scroll back to top between passes
            if pass_num < 1:
                self.driver.execute_script("window.scrollTo(0, 0);")
                jitter_sleep(1.0, 0.3)
        
        logger.info("✓ Scrolling complete")

    def _collect_links_from_dom(self) -> List[str]:
        """
        Collect all potential vehicle detail links from current page
        """
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        links: Set[str] = set()
        rejected_links = []

        # Find all anchors
        all_anchors = soup.find_all("a", href=True)
        logger.info(f"Found {len(all_anchors)} total anchors on page")
        
        for a in all_anchors:
            href = a.get("href", "")
            if not href:
                continue
            
            # Make absolute URL
            if href.startswith('/'):
                href = urljoin(self.inventory_url, href)
            elif not href.startswith('http'):
                continue
            
            href = normalize_url(href)

            # Keep same domain only
            if not same_domain(self.inventory_url, href):
                continue

            # Check if it's a detail page (STRICT validation)
            if likely_detail_url(href):
                links.add(href)
            else:
                # Track rejected for debugging
                if '-id' in href or '/used/' in href or '/demos/' in href:
                    rejected_links.append(href)
        
        # Remove duplicates and sort
        out = list(dict.fromkeys(sorted(links)))
        logger.info(f"✓ Found {len(out)} valid detail page links")
        logger.info(f"✓ Rejected {len(rejected_links)} invalid links")
        
        # Debug: show sample links
        if out:
            logger.info(f"  Sample VALID links:")
            for link in out[:3]:
                logger.info(f"    ✓ {link}")
        
        if rejected_links and len(rejected_links) <= 5:
            logger.info(f"  Sample REJECTED links:")
            for link in rejected_links[:3]:
                logger.info(f"    ✗ {link}")
        
        return out

    def _dealercom_click_next(self) -> bool:
        """
        Try to click Next/Load More buttons
        """
        xpath_candidates = [
            "//a[contains(translate(., 'NEXT', 'next'), 'next')]",
            "//button[contains(translate(., 'NEXT', 'next'), 'next')]",
            "//a[contains(., '›') or contains(., '»')]",
            "//button[contains(., '›') or contains(., '»')]",
            "//a[contains(translate(., 'LOAD MORE', 'load more'), 'load more')]",
            "//button[contains(translate(., 'LOAD MORE', 'load more'), 'load more')]",
        ]

        for xp in xpath_candidates:
            try:
                el = self.driver.find_element(By.XPATH, xp)
                if el and el.is_displayed() and el.is_enabled():
                    self.driver.execute_script("arguments[0].click();", el)
                    jitter_sleep(3.0, 1.0)
                    return True
            except:
                continue
        return False

    def collect_detail_links(self) -> List[str]:
        """
        Collect all vehicle detail page links from inventory
        """
        self.load(self.inventory_url)
        jitter_sleep(4.0, 1.5)

        platform = self.detect_platform()
        logger.info(f"✓ Detected platform: {platform}")

        collected: Set[str] = set()

        if platform in ["dealer.com", "d2cmedia"]:
            # These platforms may have pagination
            for p in range(1, self.max_pages + 1):
                logger.info(f"📄 Page {p}/{self.max_pages}")
                
                # Aggressive scrolling
                self._scroll_aggressive()

                # Collect links
                links = self._collect_links_from_dom()
                for u in links:
                    collected.add(u)

                logger.info(f"✓ Total collected: {len(collected)} links")
                
                if len(collected) >= self.max_links:
                    logger.info(f"⚠ Reached max_links cap ({self.max_links})")
                    break

                # Try to click next
                if not self._dealercom_click_next():
                    logger.info("✓ No more pages")
                    break

        else:
            # Generic: scroll + collect
            self._scroll_aggressive()
            links = self._collect_links_from_dom()
            for u in links:
                collected.add(u)

        out = list(dict.fromkeys(sorted(collected)))
        logger.info(f"✅ TOTAL DETAIL LINKS FOUND: {len(out)}")
        return out

    def _soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.driver.page_source, "lxml")

    def _find_vin(self, soup: BeautifulSoup) -> Optional[str]:
        txt = " ".join(soup.stripped_strings).upper()
        m = VIN_RE.search(txt)
        return m.group(1) if m else None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[str]:
        """
        SIMPLE & DIRECT price extraction - handles formats with and without $ sign
        """
        full_text = " ".join(soup.stripped_strings)
        
        # Pattern 1: "Price: 156,859" (Screenshot format - NO $ sign!)
        match = re.search(r'Price\s*:\s*(\d{1,3}(?:,\d{3})+)(?:\s|$|[^\d])', full_text, flags=re.I)
        if match:
            amount = int(match.group(1).replace(',', ''))
            if 5000 <= amount <= 200000:
                return f"${match.group(1)}"
        
        # Pattern 2: "ONE PRICE: $19,888" (CAMCO format with $)
        match = re.search(r'ONE\s*PRICE\s*:\s*\$\s*(\d{1,3}(?:,\d{3})*)', full_text, flags=re.I)
        if match:
            amount = int(match.group(1).replace(',', ''))
            if 5000 <= amount <= 200000:
                return f"${match.group(1)}"
        
        # Pattern 3: "Price: $19,888" (with $ sign)
        match = re.search(r'Price\s*:\s*\$\s*(\d{1,3}(?:,\d{3})*)', full_text, flags=re.I)
        if match:
            amount = int(match.group(1).replace(',', ''))
            if 5000 <= amount <= 200000:
                return f"${match.group(1)}"
        
        # Pattern 4: Look in HTML elements with "price" in class/id
        for elem in soup.find_all(class_=re.compile('price', re.I)):
            text = elem.get_text(strip=True)
            # Try WITH $ sign first
            match = re.search(r'\$\s*(\d{1,3}(?:,\d{3})*)', text)
            if match:
                amount = int(match.group(1).replace(',', ''))
                if 5000 <= amount <= 200000:
                    return f"${match.group(1)}"
            # Try WITHOUT $ sign
            match = re.search(r'(\d{1,3}(?:,\d{3})+)', text)
            if match:
                amount = int(match.group(1).replace(',', ''))
                if 5000 <= amount <= 200000:
                    return f"${match.group(1)}"
        
        # Pattern 5: Any complete price with $ sign (last resort)
        all_matches = re.findall(r'\$\s*(\d{1,3}(?:,\d{3})+)', full_text)
        valid = []
        for m in all_matches:
            num = int(m.replace(',', ''))
            if 5000 <= num <= 200000:
                valid.append((num, f"${m}"))
        
        if valid:
            valid.sort(reverse=True)  # Take highest = main price
            return valid[0][1]
        
        return None

    def _extract_mileage(self, soup: BeautifulSoup, full_text: str) -> Optional[str]:
        """
        SIMPLE & DIRECT mileage extraction - handles DEMO and USED cars
        """
        # Pattern 1: "Kilometers: 3,139 km" (Screenshot format - with or without commas)
        match = re.search(r'Kilometers?\s*:\s*(\d{1,3}(?:,\d{3})*)\s*km', full_text, flags=re.I)
        if match:
            mileage_str = match.group(1)
            mileage_num = int(mileage_str.replace(',', ''))
            # DEMO + USED: 1 km - 500,000 km (demo cars have low mileage)
            if 1 <= mileage_num <= 500000:
                return f"{mileage_str} km"
        
        # Pattern 2: "Mileage: 92,968 km" or "Mileage:  92,968 km"
        match = re.search(r'Mileage\s*:\s*(\d{1,3}(?:,\d{3})*)\s*km', full_text, flags=re.I)
        if match:
            mileage_str = match.group(1)
            mileage_num = int(mileage_str.replace(',', ''))
            if 1 <= mileage_num <= 500000:
                return f"{mileage_str} km"
        
        # Pattern 3: "Odometer: 92,968 km"
        match = re.search(r'Odometer\s*:\s*(\d{1,3}(?:,\d{3})*)\s*km', full_text, flags=re.I)
        if match:
            mileage_str = match.group(1)
            mileage_num = int(mileage_str.replace(',', ''))
            if 1 <= mileage_num <= 500000:
                return f"{mileage_str} km"
        
        # Pattern 4: Look in HTML elements with "mileage" or "kilometer" in class/id
        for elem in soup.find_all(class_=re.compile(r'(mileage|kilometer)', re.I)):
            text = elem.get_text(strip=True)
            match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*km', text, flags=re.I)
            if match:
                mileage_str = match.group(1)
                mileage_num = int(mileage_str.replace(',', ''))
                if 1 <= mileage_num <= 500000:
                    return f"{mileage_str} km"
        
        # Pattern 5: Any complete km value "X,XXX km" (last resort)
        all_matches = re.findall(r'(\d{1,3}(?:,\d{3})+)\s*km', full_text, flags=re.I)
        valid = []
        for m in all_matches:
            num = int(m.replace(',', ''))
            if 1 <= num <= 500000:
                valid.append((num, f"{m} km"))
        
        if valid:
            valid.sort()  # Take smallest = actual odometer
            return valid[0][1]
        
        return None

    def parse_detail(self, url: str) -> VehicleRecord:
        rec = VehicleRecord(source_url=url)

        self.load(url)
        jitter_sleep(2.5, 1.0)

        soup = self._soup()
        full_text = " ".join(soup.stripped_strings)

        # VIN
        rec.vin = self._find_vin(soup)

        # Decode VIN if found
        if rec.vin and len(rec.vin) == 17:
            vin_data = decode_vin(rec.vin)
            rec.vin_make = vin_data["vin_make"]
            rec.vin_model = vin_data["vin_model"]
            rec.vin_year = vin_data["vin_year"]
            rec.vin_trim = vin_data["vin_trim"]
            rec.vin_body_style = vin_data["vin_body_style"]

        # Title parsing
        title = ""
        if soup.title and soup.title.string:
            title = clean_text(soup.title.string)
        if not title:
            h1 = soup.find(["h1", "h2"])
            if h1:
                title = clean_text(h1.get_text(" ", strip=True))

        if title:
            ym = re.search(r"\b(19|20)\d{2}\b", title)
            if ym:
                rec.year = ym.group(0)

            if rec.year and rec.year in title:
                tail = title.split(rec.year, 1)[1].strip(" -|")
                parts = tail.split()
                if len(parts) >= 1:
                    rec.make = parts[0]
                if len(parts) >= 2:
                    rec.model = parts[1]
                if len(parts) >= 3:
                    rec.trim = " ".join(parts[2:])[:80]

        # Price
        rec.price = self._extract_price(soup)
        if rec.price:
            logger.info(f"  ✓ Price found: {rec.price}")
        else:
            logger.warning(f"  ⚠ Price NOT found")

        # Mileage - STRICT extraction
        rec.mileage = self._extract_mileage(soup, full_text)
        if rec.mileage:
            logger.info(f"  ✓ Mileage found: {rec.mileage}")
        else:
            logger.warning(f"  ⚠ Mileage NOT found")

        # Stock
        sm = re.search(r"\bStock\s*#?\s*[:\-]?\s*([A-Z0-9\-]+)\b", full_text, flags=re.I)
        if sm:
            rec.stock = sm.group(1).strip()

        # Transmission
        tr = re.search(r"\b(Automatic|Manual|CVT)\b", full_text, flags=re.I)
        if tr:
            rec.transmission = tr.group(1).title()

        # Drivetrain
        dr = re.search(r"\b(AWD|FWD|RWD|4WD)\b", full_text, flags=re.I)
        if dr:
            rec.drivetrain = dr.group(1).upper()

        # Engine
        eng = re.search(r"\b(\d\.\d)\s*L\b", full_text, flags=re.I)
        if eng:
            rec.engine = f"{eng.group(1)}L"

        # Colors
        ext = re.search(r"\bExterior\s*Color\s*[:\-]?\s*([A-Za-z0-9 \-]+)\b", full_text, flags=re.I)
        if ext:
            rec.exterior_color = clean_text(ext.group(1))[:40]
        intr = re.search(r"\bInterior\s*Color\s*[:\-]?\s*([A-Za-z0-9 \-]+)\b", full_text, flags=re.I)
        if intr:
            rec.interior_color = clean_text(intr.group(1))[:40]

        # Validate VIN
        if rec.vin and len(rec.vin) != 17:
            rec.vin = None

        return rec

    def run(self, limit: Optional[int] = None) -> pd.DataFrame:
        links = self.collect_detail_links()
        if limit:
            links = links[:limit]

        logger.info(f"🚀 Starting detail scrape for {len(links)} vehicles...")
        
        rows: List[VehicleRecord] = []
        for i, u in enumerate(links, start=1):
            logger.info(f"({i}/{len(links)}) Parsing: {u}")
            try:
                r = self.parse_detail(u)
                rows.append(r)
                jitter_sleep(1.0, 0.5)
            except Exception as e:
                logger.warning(f"❌ Failed: {u} | {e}")
                rows.append(VehicleRecord(source_url=u))
                jitter_sleep(2.0, 1.0)

        df = pd.DataFrame([asdict(x) for x in rows])
        
        # STRICT FILTERING - Remove invalid/unwanted data
        original_count = len(df)
        
        # Filter 1: Must have VIN OR (year AND make)
        df = df[
            (df['vin'].notna() & (df['vin'].str.len() == 17)) |
            ((df['year'].notna()) & (df['make'].notna()))
        ].copy()
        logger.info(f"✓ Filter 1 (VIN/Year+Make): {original_count} → {len(df)} rows")
        
        # Filter 2: Remove duplicates by VIN (keep first)
        if 'vin' in df.columns:
            df['vin'] = df['vin'].fillna("").astype(str).str.upper()
            before = len(df)
            # Remove duplicates where VIN is not empty
            df = df[~((df['vin'] != "") & df.duplicated(subset=['vin'], keep='first'))].copy()
            logger.info(f"✓ Filter 2 (Duplicate VINs): {before} → {len(df)} rows")
        
        # Filter 3: Remove duplicates by URL
        before = len(df)
        df = df.drop_duplicates(subset=['source_url'], keep='first').copy()
        logger.info(f"✓ Filter 3 (Duplicate URLs): {before} → {len(df)} rows")
        
        # Filter 4: Remove rows with no useful data (no VIN, price, or mileage)
        before = len(df)
        df = df[
            (df['vin'].notna() & (df['vin'] != "")) |
            (df['price'].notna()) |
            (df['mileage'].notna())
        ].copy()
        logger.info(f"✓ Filter 4 (Has useful data): {before} → {len(df)} rows")
        
        # Reset index
        df = df.reset_index(drop=True)
        
        logger.info(f"✅ SCRAPING COMPLETE: {len(df)} valid vehicles (filtered from {original_count} total)")
        return df
