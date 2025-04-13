import sys
import concurrent.futures
import logging
import random
import time
import urllib3
import requests
from datetime import datetime
from colorama import Fore, Style, init
from requests_html import HTMLSession
from bs4 import BeautifulSoup

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize colorama
init(autoreset=True)

# Set up logging
logging.basicConfig(filename='src/username_search.log', level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Set up separate error logging
error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler('src/username_search_errors.log')
error_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
error_logger.addHandler(error_handler)

# File for saving results will be set up in main() function
results_file = None

# Keep track of visited URLs to prevent duplicates
visited_urls = set()
visited_html_content = set()

# Daftar domain yang sering gagal
PROBLEMATIC_DOMAINS = [
    # Hanya simpan domain yang benar-benar bermasalah
    "ask.fm",
    "blip.fm"
    # Hapus domain lain untuk mendapatkan hasil yang lebih lengkap
]

# Default settings
DEFAULT_TIMEOUT = 30  # seconds - ditingkatkan untuk hasil yang lebih lengkap
DEFAULT_DELAY = 1  # seconds between requests - dikurangi untuk mempercepat pencarian
MAX_RETRIES = 3  # maximum number of retries for failed requests - ditingkatkan untuk hasil yang lebih lengkap


# Function to search for username on a single URL
def search_username_on_url(username: str, url: str, include_titles=True, include_descriptions=True, include_html_content=True, verify_ssl=False, timeout=DEFAULT_TIMEOUT):
    global visited_urls, visited_html_content

    # Validate username
    if not username or len(username.strip()) == 0:
        print(f"{Fore.YELLOW}⚠️ {Fore.RED}Empty username provided. Skipping URL: {Fore.WHITE}{url}")
        return None

    # Periksa apakah URL mengandung domain yang bermasalah
    if any(domain in url for domain in PROBLEMATIC_DOMAINS):
        print(f"{Fore.YELLOW}⚠️ {Fore.RED}Skipping problematic domain: {Fore.WHITE}{url}")
        return None

    try:
        # Construct URL with username
        # Remove any special characters that might cause issues in URLs
        clean_username = ''.join(c for c in username if c.isalnum() or c in '-_.')

        if clean_username.lower() not in url.lower():
            url += f'/{clean_username}' if url.endswith('/') else f'/{clean_username}'

        if url in visited_urls:
            print(f"{Fore.YELLOW}⚠️ {Fore.RED}Skipping duplicate URL: {Fore.WHITE}{url}")
            return None

        visited_urls.add(url)

        session = HTMLSession()
        session.verify = verify_ssl  # Mengabaikan verifikasi SSL jika verify_ssl=False

        # Tambahkan timeout
        time.sleep(random.uniform(1, 3))  # Introduce a random delay to mimic human behavior

        # Tambahkan sistem retry dengan backoff eksponensial
        retry_attempt = 0
        response = None

        for retry_attempt in range(MAX_RETRIES):
            try:
                if retry_attempt > 0:
                    # Jika ini percobaan ulang, tunggu dengan backoff eksponensial
                    wait_time = 2 ** retry_attempt
                    print(f"{Fore.YELLOW}⏱️ {Fore.CYAN}Retry attempt {retry_attempt} for URL {Fore.WHITE}{url}{Fore.CYAN}. Waiting {wait_time}s...")
                    time.sleep(wait_time)

                # Coba lakukan request
                response = session.get(url, timeout=timeout)
                # Jika berhasil, keluar dari loop retry
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.SSLError) as e:
                # Jika ini percobaan terakhir, lempar exception untuk ditangani di luar
                if retry_attempt == MAX_RETRIES - 1:
                    if isinstance(e, requests.exceptions.Timeout):
                        print(f"{Fore.YELLOW}⏱️ {Fore.RED}Timeout for URL {Fore.WHITE}{url}")
                        error_logger.error(f"Timeout occurred while searching for {username} on {url}")
                    elif isinstance(e, requests.exceptions.SSLError):
                        print(f"{Fore.YELLOW}🔒 {Fore.RED}SSL Certificate error for URL {Fore.WHITE}{url}")
                        error_logger.error(f"SSL Certificate error occurred while searching for {username} on {url}")
                    elif isinstance(e, requests.exceptions.ConnectionError):
                        if "certificate verify failed" in str(e):
                            print(f"{Fore.YELLOW}🔒 {Fore.RED}SSL Certificate error for URL {Fore.WHITE}{url}")
                        elif "getaddrinfo failed" in str(e):
                            print(f"{Fore.YELLOW}🌐 {Fore.RED}DNS resolution failed for URL {Fore.WHITE}{url}")
                        else:
                            print(f"{Fore.YELLOW}🔌 {Fore.RED}Connection error for URL {Fore.WHITE}{url}")
                        error_logger.error(f"Connection error occurred while searching for {username} on {url}: {e}")
                    return None
                # Jika bukan percobaan terakhir, lanjutkan ke percobaan berikutnya
                continue
            except Exception as e:
                print(f"{Fore.YELLOW}❌ {Fore.RED}Request error for URL {Fore.WHITE}{url}: {str(e)}")
                error_logger.error(f"Request error occurred while searching for {username} on {url}: {e}")
                return None

        # Jika response tidak ada (semua percobaan gagal), return None
        if response is None:
            return None

        # Proses response
        if response.status_code == 200:
            if response.html.raw_html in visited_html_content:
                print(f"{Fore.YELLOW}⚠️ {Fore.RED}Skipping duplicate HTML content for URL: {Fore.WHITE}{url}")
                return None

            visited_html_content.add(response.html.raw_html)

            print(f"{Fore.CYAN}🔍 {Fore.BLUE}{username} {Fore.RED}| {Fore.YELLOW}[{Fore.GREEN}✅{Fore.YELLOW}]{Fore.WHITE} URL{Fore.YELLOW}: {Fore.LIGHTGREEN_EX}{url}{Fore.WHITE} {response.status_code} {Fore.CYAN}(Attempt: {retry_attempt+1}/{MAX_RETRIES})")

            # Always check for query in URL, title, description, and HTML content
            print_query_detection(username, url, response.html.raw_html)

            # Write results to file
            write_to_file(username, url, response.status_code, include_titles, include_descriptions, include_html_content)

            # Print HTML content with organized formatting if requested
            if include_titles or include_descriptions or include_html_content:
                print_html(response.html.raw_html, url, username, include_titles, include_descriptions, include_html_content)

            # Return True untuk menandakan bahwa pencarian berhasil
            return True
        else:
            # Skip processing for non-200 status codes
            print(f"{Fore.YELLOW}⚠️ {Fore.RED}Status code for URL {Fore.WHITE}{url}{Fore.RED}: {response.status_code}")
            return None

    except UnicodeEncodeError:
        print(f"{Fore.YELLOW}� {Fore.RED}Unicode encoding error for URL {Fore.WHITE}{url}")
        error_logger.error(f"UnicodeEncodeError occurred while printing to console for {username} on {url}")
        return None
    except Exception as e:
        print(f"{Fore.YELLOW}❓ {Fore.RED}Unexpected error for URL {Fore.WHITE}{url}: {str(e)}")
        error_logger.error(f"Error occurred while searching for {username} on {url}: {e}")
        return None

def print_query_detection(username, url, html_content):
    query_detected = False
    try:
        # Check if username is detected in URL
        if username.lower() in url.lower():
            #print(f"{Fore.YELLOW}🔸 Query detected in URL: {Fore.WHITE}{url}")
            query_detected = True

        # Check if username is detected in HTML content
        if html_content and username.lower() in html_content.decode('utf-8').lower():
            print(f"{Fore.YELLOW}🔸 {Fore.LIGHTBLACK_EX}Query detected in 'HTML content'{Fore.RED}... {Fore.WHITE}")
            query_detected = True

        # Check if username is detected in meta description
        soup = BeautifulSoup(html_content, 'html.parser')
        meta_description = soup.find("meta", attrs={"name": "description"})
        description = meta_description['content'] if meta_description else ""
        if username.lower() in description.lower():
            print(f"{Fore.YELLOW}🔸 {Fore.LIGHTBLACK_EX}Query detected in 'description'{Fore.RED}... {Fore.WHITE}")
            query_detected = True

        if not query_detected:
            print(f"{Fore.YELLOW}🔸 Query not detected in URL, description, or HTML content for URL: {Fore.WHITE}{url}")

  # Check if username is detected in title
        title = soup.title.get_text(strip=True) if soup.title else ""
        if username.lower() in title.lower():
            print(f"{Fore.YELLOW}🔸 {Fore.LIGHTBLACK_EX}Query detected in 'title'{Fore.RED}... {Fore.WHITE}")
            query_detected = True

        if not query_detected:
            print(f"{Fore.YELLOW}🔸 Query not detected in URL, title, description, or HTML content for URL: {Fore.WHITE}{url}")

    except Exception as e:
        print(f"{Fore.RED}Error occurred while checking for query in URL, title, description, or HTML content for URL: {Fore.WHITE}{url}: {str(e)}")


def write_to_file(username, url, status_code, include_titles=True, include_descriptions=True, include_html_content=True):
    try:
        # Tulis informasi dasar
        results_file.write(f"Username: {username}\n")
        results_file.write(f"URL: {url}\n")
        results_file.write(f"Status Code: {status_code}\n")

        # Tambahkan timestamp
        results_file.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Tulis detail jika diminta
        if include_titles or include_descriptions or include_html_content:
            results_file.write("Details:\n")
            if include_titles:
                results_file.write("Title: ...\n")  # Placeholder, will be replaced if available
            if include_descriptions:
                results_file.write("Description: ...\n")  # Placeholder, will be replaced if available
            if include_html_content:
                results_file.write("HTML Content: ...\n")  # Placeholder, will be replaced if available

        # Tambahkan informasi tambahan
        results_file.write("Retry Information: Menggunakan sistem retry dengan backoff eksponensial\n")
        results_file.write(f"Timeout: {DEFAULT_TIMEOUT} seconds\n")
        results_file.write(f"Max Retries: {MAX_RETRIES}\n")

        # Tambahkan pemisah
        results_file.write("\n" + "-"*50 + "\n\n")
    except Exception as e:
        logging.error(f"Error occurred while writing to file for {username} on {url}: {e}")
        error_logger.error(f"Error occurred while writing to file for {username} on {url}: {e}")


def print_html(html_content, url, query, include_titles=True, include_descriptions=True, include_html_content=True):
    try:
        if not html_content:
            print(f"{Fore.YELLOW}HTML Content for URL {Fore.WHITE}{url}:{Fore.YELLOW} Empty")
            return

        soup = BeautifulSoup(html_content, 'html.parser')
        if soup:
            if include_titles:
                title = soup.title.get_text(strip=True) if soup.title else "No title found"
                if query.lower() in title.lower():
                    print(f"{Fore.YELLOW}🔸 TITLE: {Fore.WHITE}{title}")
            if include_descriptions:
                meta_description = soup.find("meta", attrs={"name": "description"})
                description = meta_description['content'] if meta_description else "No meta description found"
                if query.lower() in description.lower():
                    print(f"{Fore.YELLOW}🔸 DESCRIPTION: {Fore.WHITE}{description}")

            if include_html_content:
                print(f"{Fore.YELLOW}🔸 HTML Content for URL {Fore.WHITE}{url}:{Fore.YELLOW}")
                # Decode bytes to string
                html_content_str = html_content.decode('utf-8')
                # Check if query is in HTML content
                if query.lower() in html_content_str.lower():
                    # Print a snippet of the HTML content with line breaks for better readability
                    snippet_length = 300  # Adjust as needed
                    html_snippet = html_content_str[:snippet_length] + ("..." if len(html_content_str) > snippet_length else "")
                    print("\n".join([f"{Fore.CYAN}{line}" for line in html_snippet.split("\n")]))

        else:
            print(f"{Fore.YELLOW}HTML Content for URL {Fore.WHITE}{url}:{Fore.RED} Empty")
    except Exception as e:
        print(f"{Fore.RED}Error occurred while parsing HTML content for URL {Fore.WHITE}{url}:{Fore.RED} {str(e)}")




def main(username, max_urls=None, verify_ssl=False, timeout=DEFAULT_TIMEOUT):
    global results_file

    # Validate username
    if not username or len(username.strip()) == 0:
        print("❌ Error: Username cannot be empty.")
        return

    # Clean username for better search results
    username = username.strip()
    print(f"{Fore.CYAN}🔍 Using username: {Fore.WHITE}{username}")

    # Set up file for saving results with username in the filename
    results_filename = f"Results/{username}_username-search_results.txt"
    results_file = open(results_filename, "w", encoding='utf-8')

    # Load URLs from file
    try:
        with open("src/urls.txt", "r") as f:
            url_list = [x.strip() for x in f.readlines() if x.strip() and not x.strip().startswith('#')]
    except Exception as e:
        print(f"❌ Error loading URLs: {e}")
        return

    if not url_list:
        print("❌ Error: No URLs found in src/urls.txt.")
        return

    # Limit the number of URLs if specified
    if max_urls and max_urls < len(url_list):
        url_list = url_list[:max_urls]
        print(f"{Fore.CYAN}ℹ️ Limiting search to {Fore.WHITE}{max_urls}{Fore.CYAN} URLs")

    print(f"{Fore.RED}_" * 80 + "\n")
    include_titles = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include titles? (y/n): {Style.RESET_ALL}").lower() == 'y'
    include_descriptions = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include descriptions? (y/n):{Style.RESET_ALL} ").lower() == 'y'
    include_html_content = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include HTML content? (y/n):{Style.RESET_ALL} ").lower() == 'y'
    print(f"{Fore.RED}_" * 80 + "\n")

    # Opsi untuk mengabaikan verifikasi SSL (default: n untuk hasil yang lebih lengkap)
    verify_ssl_input = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Verify SSL certificates? (y/n) [default: n]:{Style.RESET_ALL} ").lower()
    verify_ssl = verify_ssl_input == 'y'  # Hanya True jika pengguna secara eksplisit mengetik 'y'

    print(f"{Fore.CYAN}🔍 Searching for username: {Fore.WHITE}{username}")
    print(f"{Fore.CYAN}📊 Total URLs to check: {Fore.WHITE}{len(url_list)}")
    print(f"{Fore.CYAN}⏱️ Timeout: {Fore.WHITE}{timeout} seconds")
    print(f"{Fore.CYAN}🔒 SSL Verification: {Fore.WHITE}{verify_ssl}")
    print(f"{Fore.RED}_" * 80 + "\n")

    # Tambahkan variabel untuk melacak hasil
    successful_urls = []
    failed_urls = []

    # Jalankan pencarian dengan ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:  # Ditingkatkan dari 5 menjadi 15 untuk hasil yang lebih lengkap
        # Buat dictionary untuk melacak URL untuk setiap future
        future_to_url = {}

        # Submit semua tugas dan simpan future dan URL-nya
        for url in url_list:
            future = executor.submit(search_username_on_url, username, url, include_titles, include_descriptions, include_html_content, verify_ssl, timeout)
            future_to_url[future] = url

        # Dapatkan semua future
        futures = list(future_to_url.keys())

        # Tunggu semua future selesai
        for future in concurrent.futures.as_completed(futures):
            url = future_to_url[future]
            try:
                # Jika future mengembalikan hasil (tidak None), tambahkan ke successful_urls
                result = future.result()
                if result is not None:
                    successful_urls.append(url)
            except Exception as e:
                # Jika future menghasilkan exception, tambahkan ke failed_urls
                failed_urls.append(url)
                error_logger.error(f"Error occurred while searching for {username} on {url}: {e}")

    # Tampilkan ringkasan hasil
    print(f"\n{Fore.RED}_" * 80)
    print(f"{Fore.CYAN}📊 {Fore.WHITE}Search Summary for {Fore.YELLOW}{username}:")
    print(f"{Fore.GREEN}✅ {Fore.WHITE}Successfully checked: {Fore.GREEN}{len(successful_urls)}/{len(url_list)} URLs")
    print(f"{Fore.RED}❌ {Fore.WHITE}Failed: {Fore.RED}{len(failed_urls)}/{len(url_list)} URLs")

    # Tulis ringkasan ke file
    results_file.write(f"\nSearch Summary for {username}:\n")
    results_file.write(f"Successfully checked: {len(successful_urls)}/{len(url_list)} URLs\n")
    results_file.write(f"Failed: {len(failed_urls)}/{len(url_list)} URLs\n")
    results_file.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    print(f"{Fore.CYAN}💾 {Fore.WHITE}Results saved to: {Fore.YELLOW}{results_filename}")
    print(f"{Fore.RED}_" * 80)

    # Close the results file
    results_file.close()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            print("❌ Error: Invalid number of arguments.")
            sys.exit(1)

        if sys.argv[1] == '--skip':
            print(f" {Fore.RED}- {Fore.LIGHTBLACK_EX}src/usr.py[ Skipping the username search{Fore.RED}...{Style.RESET_ALL}")
            sys.exit(0)

        input_text = sys.argv[1]

        confirmation = input(f"\n {Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.WHITE}Do you want to run a username search{Fore.RED}? {Fore.LIGHTBLACK_EX}({Fore.WHITE}y{Fore.LIGHTBLACK_EX}/{Fore.WHITE}n{Fore.LIGHTBLACK_EX}){Fore.YELLOW}: {Style.RESET_ALL}")
        if confirmation.lower() != 'y':
            #print("Script execution aborted.")
            sys.exit(0)

        # Uncomment the line below if you want to display input_text before running main
        # print(f" \n〘 Username Search: {input_text} 〙\n")

        main(input_text)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        print("❌ Error: An unexpected error occurred.")

# File is closed in main() function
