"""
🚗 SM360 Dealer Scraper - CORE MODULE
=====================================
Core scraping logic for extracting vehicle data from dealer websites.

Fields: URL, VIN, Stock#, Year, Make, Model, Trim, Condition, Price, Mileage,
Transmission, Drivetrain, Body Style, Color, Engine, Fuel, Doors, Passengers
"""

import re
import time
import json
from dataclasses import dataclass
from typing import List, Dict, Callable, Optional
from urllib.parse import urljoin, urlparse

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from bs4 import BeautifulSoup

# -------------------------------------------------
# DATA MODEL - ALL FIELDS
# -------------------------------------------------
@dataclass
class VehicleData:
    url: str = ""
    source_dealer: str = ""
    vin: str = ""
    stock_number: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    trim: str = ""
    condition: str = ""
    full_title: str = ""
    price: str = ""
    was_price: str = ""
    mileage_km: str = ""
    transmission: str = ""
    drivetrain: str = ""
    body_style: str = ""
    ext_color: str = ""
    int_color: str = ""
    engine: str = ""
    cylinders: str = ""
    fuel_type: str = ""
    doors: str = ""
    passengers: str = ""
    certified: str = ""
    image_url: str = ""
    features: str = ""


def is_selenium_available() -> bool:
    """Check if Selenium is available"""
    return SELENIUM_AVAILABLE


# -------------------------------------------------
# CHROME DRIVER
# -------------------------------------------------
def create_driver():
    """Create headless Chrome driver"""
    if not SELENIUM_AVAILABLE:
        return None
        
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        print(f"Chrome driver error: {e}")
        return None


# -------------------------------------------------
# HELPER: Extract dealer name from URL
# -------------------------------------------------
def get_dealer_name(url: str) -> str:
    """Extract dealer name from URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        name = domain.replace('www.', '').split('.')[0]
        return name.title()
    except:
        return url[:30]


# -------------------------------------------------
# PARSE MULTIPLE URLS
# -------------------------------------------------
def parse_urls(url_text: str) -> List[str]:
    """Parse multiple URLs from text (one per line or comma-separated)"""
    urls = []
    lines = url_text.replace(',', '\n').split('\n')
    
    for line in lines:
        url = line.strip()
        if url and url.startswith('http'):
            urls.append(url)
    
    return urls


# -------------------------------------------------
# DETAIL PAGE SCRAPER - Gets ALL fields
# -------------------------------------------------
def scrape_detail_page(driver, url: str, source_dealer: str = "") -> Dict:
    """Scrape complete vehicle data from detail page"""
    
    data = {
        'url': url,
        'source_dealer': source_dealer,
        'vin': '',
        'stock_number': '',
        'year': '',
        'make': '',
        'model': '',
        'trim': '',
        'condition': '',
        'full_title': '',
        'price': '',
        'was_price': '',
        'mileage_km': '',
        'transmission': '',
        'drivetrain': '',
        'body_style': '',
        'ext_color': '',
        'int_color': '',
        'engine': '',
        'cylinders': '',
        'fuel_type': '',
        'doors': '',
        'passengers': '',
        'certified': '',
        'carfax_url': '',
        'image_url': '',
        'features': '',
    }
    
    try:
        driver.get(url)
        time.sleep(2)
        
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator='\n', strip=True)
        
        # ===== CONDITION (New/Used/Certified) =====
        url_lower = url.lower()
        if '/new-inventory/' in url_lower or '/new/' in url_lower:
            data['condition'] = 'New'
        elif '/certified-inventory/' in url_lower or '/certified/' in url_lower:
            data['condition'] = 'Certified Pre-Owned'
        elif '/used-inventory/' in url_lower or '/used/' in url_lower:
            data['condition'] = 'Used'
        
        if not data['condition']:
            condition_patterns = [
                r'Condition\s*[:\s]*\n?\s*(New|Used|Certified|Pre-Owned|CPO)',
                r'Vehicle\s*Condition\s*[:\s]*\n?\s*(New|Used|Certified|Pre-Owned|CPO)',
                r'Status\s*[:\s]*\n?\s*(New|Used|Certified|Pre-Owned|CPO)',
            ]
            for pattern in condition_patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    val = match.group(1).strip()
                    if val.lower() in ['cpo', 'certified', 'pre-owned']:
                        data['condition'] = 'Certified Pre-Owned'
                    else:
                        data['condition'] = val.capitalize()
                    break
        
        if not data['condition']:
            if re.search(r'\bBrand\s*New\b|\bNew\s*Vehicle\b', text, re.I):
                data['condition'] = 'New'
            elif re.search(r'\bCertified\s*Pre-Owned\b|\bCPO\b', text, re.I):
                data['condition'] = 'Certified Pre-Owned'
            elif re.search(r'\bPre-Owned\b|\bUsed\s*Vehicle\b', text, re.I):
                data['condition'] = 'Used'
        
        # ===== VIN =====
        vin_patterns = [
            r'VIN\s*#?\s*[:\s]*\n?\s*([A-HJ-NPR-Z0-9]{17})',
            r'Vehicle\s*Identification\s*[:\s]*([A-HJ-NPR-Z0-9]{17})',
            r'\b([A-HJ-NPR-Z0-9]{17})\b',
        ]
        for pattern in vin_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                data['vin'] = match.group(1)
                break
        
        # ===== STOCK/INVENTORY NUMBER =====
        stock_patterns = [
            r'Inventory\s*#?\s*[:\s]*\n?\s*([A-Z0-9\-]+)',
            r'Stock\s*#?\s*[:\s]*\n?\s*([A-Z0-9\-]+)',
            r'Stock\s*Number\s*[:\s]*([A-Z0-9\-]+)',
        ]
        for pattern in stock_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()
                num_match = re.search(r'(\d+[A-Z0-9\-]*|\d+)', val, re.I)
                if num_match:
                    val = num_match.group(1)
                val = re.sub(r'^(stock|inventory|#|:|\s)+', '', val, flags=re.I).strip()
                if len(val) >= 1 and len(val) <= 20:
                    data['stock_number'] = val
                    break
        
        # ===== PRICE =====
        price_match = re.search(r'\$\s*([\d,]+)', text)
        if price_match:
            data['price'] = price_match.group(1).replace(',', '')
        
        was_match = re.search(r'Was\s*\$?\s*([\d,]+)', text, re.I)
        if was_match:
            data['was_price'] = was_match.group(1).replace(',', '')
        
        # ===== MILEAGE =====
        km_patterns = [
            r'Mileage\s*[:\s]*\n?\s*([\d,]+)\s*(?:KM|km)?',
            r'Odometer\s*[:\s]*\n?\s*([\d,]+)',
            r'Kilometers?\s*[:\s]*\n?\s*([\d,]+)',
            r'([\d,]+)\s*KM\b',
            r'([\d,]+)\s*km\b',
        ]
        for pattern in km_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).replace(',', '')
                if val.isdigit() and int(val) > 100:
                    data['mileage_km'] = val
                    break
        
        # ===== TRANSMISSION =====
        trans_patterns = [
            r'Transmission\s*[:\s]*\n?\s*([^\n]+)',
            r'Trans\.?\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in trans_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:50]
                data['transmission'] = val
                break
        
        if not data['transmission']:
            if re.search(r'\bAutomatic\b', text, re.I):
                data['transmission'] = 'Automatic'
            elif re.search(r'\bManual\b', text, re.I):
                data['transmission'] = 'Manual'
            elif re.search(r'\bCVT\b', text, re.I):
                data['transmission'] = 'CVT'
        
        # ===== DRIVETRAIN =====
        drive_patterns = [
            r'Drivetrain\s*[:\s]*\n?\s*([^\n]+)',
            r'Drive\s*Type\s*[:\s]*\n?\s*([^\n]+)',
            r'Drive\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in drive_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:30]
                if val and not val.startswith('$'):
                    data['drivetrain'] = val
                    break
        
        if not data['drivetrain']:
            drive_map = [
                (r'\b4x4\b', '4x4'),
                (r'\b4WD\b', '4WD'),
                (r'\bAll[\s\-]?Wheel[\s\-]?Drive\b', 'AWD'),
                (r'\bAWD\b', 'AWD'),
                (r'\bFront[\s\-]?Wheel[\s\-]?Drive\b', 'FWD'),
                (r'\bFWD\b', 'FWD'),
                (r'\bRear[\s\-]?Wheel[\s\-]?Drive\b', 'RWD'),
                (r'\bRWD\b', 'RWD'),
            ]
            for pattern, value in drive_map:
                if re.search(pattern, text, re.I):
                    data['drivetrain'] = value
                    break
        
        # ===== BODY STYLE =====
        body_patterns = [
            r'Body\s*Style\s*[:\s]*\n?\s*([^\n]+)',
            r'Bodystyle\s*[:\s]*\n?\s*([^\n]+)',
            r'Body\s*Type\s*[:\s]*\n?\s*([^\n]+)',
            r'Style\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in body_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:50]
                if val and not val.startswith('$') and not val.isdigit():
                    data['body_style'] = val
                    break
        
        # ===== EXTERIOR COLOR =====
        color_patterns = [
            r'Ext(?:erior)?\.?\s*Colou?r\s*[:\s]*\n?\s*([^\n]+)',
            r'Exterior\s*[:\s]*\n?\s*([^\n]+)',
            r'Colou?r\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in color_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:30]
                if val and not val.startswith('$') and not val.isdigit():
                    data['ext_color'] = val
                    break
        
        # ===== INTERIOR COLOR =====
        int_patterns = [
            r'Int(?:erior)?\.?\s*Colou?r\s*[:\s]*\n?\s*([^\n]+)',
            r'Interior\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in int_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:30]
                if val and not val.startswith('$'):
                    data['int_color'] = val
                    break
        
        # ===== ENGINE =====
        engine_patterns = [
            r'Engine\s*[:\s]*\n?\s*([^\n]+)',
            r'Motor\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in engine_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:80]
                if val and not val.startswith('$'):
                    data['engine'] = val
                    break
        
        # ===== CYLINDERS =====
        cyl_patterns = [
            r'Cylinders?\s*[:\s]*\n?\s*([^\n]+)',
            r'(\d+)\s*[Cc]ylinder',
            r'([VILvil]\d+)',
        ]
        for pattern in cyl_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:50]
                data['cylinders'] = val
                break
        
        # ===== FUEL TYPE =====
        fuel_patterns = [
            r'Fuel\s*(?:Type)?\s*[:\s]*\n?\s*([^\n]+)',
            r'Fuel\s*[:\s]*\n?\s*([^\n]+)',
        ]
        for pattern in fuel_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1).strip()[:30]
                if val and not val.startswith('$'):
                    data['fuel_type'] = val
                    break
        
        if not data['fuel_type']:
            if re.search(r'\bDiesel\b', text, re.I):
                data['fuel_type'] = 'Diesel'
            elif re.search(r'\bElectric\b', text, re.I):
                data['fuel_type'] = 'Electric'
            elif re.search(r'\bHybrid\b', text, re.I):
                data['fuel_type'] = 'Hybrid'
            elif re.search(r'\bGasoline\b|\bGas\b|\bPetrol\b', text, re.I):
                data['fuel_type'] = 'Gasoline'
        
        # ===== DOORS =====
        doors_patterns = [
            r'Doors?\s*[:\s]*\n?\s*(\d+)',
            r'(\d+)\s*[Dd]oors?',
        ]
        for pattern in doors_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1)
                if val.isdigit() and 2 <= int(val) <= 6:
                    data['doors'] = val
                    break
        
        # ===== PASSENGERS =====
        pass_patterns = [
            r'Passengers?\s*[:\s]*\n?\s*(\d+)',
            r'Seating\s*(?:Capacity)?\s*[:\s]*\n?\s*(\d+)',
            r'(\d+)\s*[Pp]assengers?',
        ]
        for pattern in pass_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = match.group(1)
                if val.isdigit() and 2 <= int(val) <= 15:
                    data['passengers'] = val
                    break
        
        # ===== TITLE (Year Make Model Trim) =====
        h1 = soup.find('h1')
        if h1:
            data['full_title'] = h1.get_text(strip=True)[:100]
        
        title_pattern = r'(\d{4})\s+(GMC|Chevrolet|Buick|Ford|Toyota|Honda|Nissan|BMW|Mazda|Volkswagen|Kia|Ram|Dodge|Lincoln|Jeep|Cadillac|Hyundai|Subaru|Audi|Mercedes|Lexus|Acura|Chrysler|Tesla|Mitsubishi|Infiniti|Volvo|Porsche|Mini|Fiat|Genesis|Rivian|Harley-Davidson|Airstream|Thor)\s+([^\n\$]{3,60})'
        
        title_match = re.search(title_pattern, text, re.I)
        if title_match:
            data['year'] = title_match.group(1)
            data['make'] = title_match.group(2)
            
            model_trim = title_match.group(3).strip()
            model_trim = re.sub(r'[.\s]+$', '', model_trim)
            
            if ',' in model_trim:
                parts = model_trim.split(',', 1)
                data['model'] = parts[0].strip()
                data['trim'] = parts[1].strip()
            else:
                words = model_trim.split()
                if len(words) >= 2 and re.match(r'\d', words[1]):
                    data['model'] = f"{words[0]} {words[1]}"
                    data['trim'] = ' '.join(words[2:]) if len(words) > 2 else ''
                else:
                    data['model'] = words[0] if words else model_trim
                    data['trim'] = ' '.join(words[1:]) if len(words) > 1 else ''
            
            if not data['full_title']:
                data['full_title'] = f"{data['year']} {data['make']} {model_trim}"
        
        # ===== CERTIFIED =====
        if re.search(r'\bcertified\b', text, re.I):
            data['certified'] = 'Yes'
        
        # ===== IMAGE URL =====
        img = soup.find('img', src=re.compile(r'sm360\.ca.*inventory.*\.(jpg|jpeg|png|webp)', re.I))
        if img:
            data['image_url'] = img.get('src', '')
        
        # ===== CARFAX URL =====
        carfax_link = soup.find('a', href=re.compile(r'carfax', re.I))
        if carfax_link:
            data['carfax_url'] = carfax_link.get('href', '')
        
        if not data['carfax_url']:
            carfax_iframe = soup.find('iframe', src=re.compile(r'carfax', re.I))
            if carfax_iframe:
                data['carfax_url'] = carfax_iframe.get('src', '')
        
        if not data['carfax_url']:
            carfax_img = soup.find('img', src=re.compile(r'carfax', re.I))
            if carfax_img:
                parent_link = carfax_img.find_parent('a')
                if parent_link and parent_link.get('href'):
                    data['carfax_url'] = parent_link.get('href', '')
        
        # ===== JSON-LD DATA (backup) =====
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                jdata = json.loads(script.string)
                if isinstance(jdata, list):
                    jdata = jdata[0] if jdata else {}
                
                if jdata.get('@type') in ['Vehicle', 'Car', 'Product']:
                    if not data['ext_color']:
                        data['ext_color'] = jdata.get('color', '')
                    if not data['fuel_type']:
                        data['fuel_type'] = jdata.get('fuelType', '')
                    if not data['body_style']:
                        data['body_style'] = jdata.get('bodyType', '')
                    if not data['doors']:
                        data['doors'] = str(jdata.get('numberOfDoors', ''))
                    if not data['passengers']:
                        data['passengers'] = str(jdata.get('vehicleSeatingCapacity', ''))
                    if not data['transmission']:
                        data['transmission'] = jdata.get('vehicleTransmission', '')
                    if not data['drivetrain']:
                        data['drivetrain'] = jdata.get('driveWheelConfiguration', '')
                    if not data['condition']:
                        item_condition = jdata.get('itemCondition', '')
                        if 'New' in item_condition:
                            data['condition'] = 'New'
                        elif 'Used' in item_condition:
                            data['condition'] = 'Used'
            except:
                pass
        
    except Exception as e:
        print(f"Error scraping {url[:50]}: {str(e)[:50]}")
    
    return data


# -------------------------------------------------
# INVENTORY PAGE - Get all vehicle URLs
# -------------------------------------------------
def get_vehicle_urls(driver, base_url: str) -> List[str]:
    """Get all vehicle detail page URLs from inventory page"""
    
    urls = []
    
    try:
        if '?' in base_url:
            fetch_url = f"{base_url}&limit=99"
        else:
            fetch_url = f"{base_url}?limit=99"
        
        driver.get(fetch_url)
        time.sleep(3)
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        link_pattern = re.compile(r'/(used|certified|new)-inventory/[^/]+/[^/]+/.*-id\d+', re.I)
        links = soup.find_all('a', href=link_pattern)
        
        seen = set()
        for link in links:
            href = link.get('href', '')
            full_url = urljoin(base_url, href)
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)
        
    except Exception as e:
        print(f"Error getting URLs from {base_url}: {e}")
    
    return urls


# -------------------------------------------------
# MAIN SCRAPER - MULTI-URL VERSION
# -------------------------------------------------
def scrape_all_vehicles_multi(
    base_urls: List[str], 
    max_vehicles_per_url: int = 100, 
    progress_callback: Optional[Callable[[str, float], None]] = None,
    warning_callback: Optional[Callable[[str], None]] = None,
    error_callback: Optional[Callable[[str], None]] = None
) -> List[Dict]:
    """
    Scrape all vehicles from multiple dealer inventories
    
    Args:
        base_urls: List of dealer inventory URLs
        max_vehicles_per_url: Maximum vehicles to scrape per URL
        progress_callback: Function(message, progress_percent) for progress updates
        warning_callback: Function(message) for warnings
        error_callback: Function(message) for errors
    
    Returns:
        List of vehicle data dictionaries
    """
    
    all_vehicles = []
    
    if progress_callback:
        progress_callback("Starting Chrome browser...", 0.02)
    
    driver = create_driver()
    if not driver:
        if error_callback:
            error_callback("Failed to create Chrome driver")
        return []
    
    try:
        total_urls = len(base_urls)
        
        for url_idx, base_url in enumerate(base_urls):
            dealer_name = get_dealer_name(base_url)
            
            url_start_pct = 0.05 + (0.95 * url_idx / total_urls)
            url_end_pct = 0.05 + (0.95 * (url_idx + 1) / total_urls)
            
            if progress_callback:
                progress_callback(f"[{url_idx+1}/{total_urls}] Getting vehicle URLs from {dealer_name}...", url_start_pct)
            
            vehicle_urls = get_vehicle_urls(driver, base_url)
            
            if not vehicle_urls:
                if warning_callback:
                    warning_callback(f"No vehicle URLs found for {dealer_name}!")
                continue
            
            vehicle_urls = vehicle_urls[:max_vehicles_per_url]
            
            if progress_callback:
                progress_callback(f"[{url_idx+1}/{total_urls}] Found {len(vehicle_urls)} vehicles at {dealer_name}. Scraping...", url_start_pct + 0.02)
            
            total = len(vehicle_urls)
            for i, url in enumerate(vehicle_urls):
                if progress_callback:
                    inner_pct = url_start_pct + ((url_end_pct - url_start_pct) * (i + 1) / total)
                    progress_callback(f"[{url_idx+1}/{total_urls}] {dealer_name}: Scraping {i+1}/{total}...", inner_pct)
                
                data = scrape_detail_page(driver, url, source_dealer=dealer_name)
                
                if data.get('vin') or data.get('price') or data.get('year'):
                    all_vehicles.append(data)
                
                time.sleep(0.5)
        
    except Exception as e:
        if error_callback:
            error_callback(f"Scraping error: {e}")
    finally:
        driver.quit()
    
    return all_vehicles


# -------------------------------------------------
# SINGLE URL SCRAPER (for backward compatibility)
# -------------------------------------------------
def scrape_all_vehicles(
    base_url: str, 
    max_vehicles: int = 100, 
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> List[Dict]:
    """Scrape all vehicles from a single dealer inventory URL"""
    return scrape_all_vehicles_multi(
        [base_url], 
        max_vehicles, 
        progress_callback
    )