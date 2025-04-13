"""
SerpAPI search module for Ominis-OSINT
Provides functions to search using SerpAPI
"""

import logging
import json
from serpapi import GoogleSearch
from colorama import Fore, Style, init
import random

from src.config import SERP_API_KEY
from src.utils import find_social_profiles, extract_mentions

# Initialize colorama
init(autoreset=True)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Emojis for console output
counter_emojis = ['🍻', '📑', '📌', '🌐', '🔰', '💀', '🔍', '📮', 'ℹ️', '📂', '📜', '📋', '📨', '🌟', '💫', '✨', '🔥', '🆔', '🎲']

def search_with_serpapi(query, language=None, country=None, date_range=None, num_results=100):
    """
    Search using SerpAPI
    
    Args:
        query (str): Search query
        language (str, optional): Language code (e.g., 'lang_en'). Defaults to None.
        country (str, optional): Country code (e.g., 'us'). Defaults to None.
        date_range (tuple, optional): Date range as (start_date, end_date). Defaults to None.
        num_results (int, optional): Number of results to return. Defaults to 100.
        
    Returns:
        tuple: (total_results, mention_links, social_profiles)
    """
    all_mention_links = []
    all_unique_social_profiles = set()
    processed_urls = set()
    total_results = 0
    
    # Prepare search parameters
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "num": min(100, num_results)  # SerpAPI max is 100 per request
    }
    
    # Add optional parameters
    if language:
        params["hl"] = language.replace('lang_', '')  # Convert 'lang_en' to 'en'
    if country:
        params["gl"] = country.lower()  # Convert 'US' to 'us'
    if date_range:
        start_date, end_date = date_range
        params["tbs"] = f"cdr:1,cd_min:{start_date},cd_max:{end_date}"
    
    # Create output file
    output_file = f"Results/{query}_serpapi-search_results.txt"
    with open(output_file, 'w') as file:
        file.write(f"Search Query: {query}\n")
        if language:
            file.write(f"Language: {language}\n")
        if country:
            file.write(f"Country: {country}\n")
        if date_range:
            file.write(f"Date Range: {date_range[0]} - {date_range[1]}\n")
        file.write("=" * 80 + "\n\n")
        
        print(f"Search Query: {query}")
        if language:
            print(f"Chosen Language: {language}")
        if country:
            print(f"Chosen Country: {country}")
        if date_range:
            print(f"Chosen Date Range: {date_range[0]} - {date_range[1]}")
        
        # Perform search
        try:
            search = GoogleSearch(params)
            results = search.get_dict()
            
            # Check for error
            if "error" in results:
                logger.error(f"SerpAPI error: {results['error']}")
                return total_results, all_mention_links, all_unique_social_profiles
            
            # Process organic results
            if "organic_results" in results:
                for result in results["organic_results"]:
                    title = result.get("title", "No title")
                    url = result.get("link", "No URL")
                    snippet = result.get("snippet", "No snippet")
                    
                    if url in processed_urls:
                        continue
                    
                    processed_urls.add(url)
                    total_results += 1
                    
                    # Write to file
                    file.write(f"Title: {title}\n")
                    file.write(f"URL: {url}\n")
                    file.write(f"Snippet: {snippet}\n")
                    file.write("-" * 80 + "\n\n")
                    
                    # Print to console
                    print('_' * 80)
                    print(random.choice(counter_emojis), f"Title{Fore.YELLOW}: {Fore.BLUE}{title}" + Style.RESET_ALL)
                    print(random.choice(counter_emojis), f"URL{Fore.YELLOW}: {Fore.LIGHTBLACK_EX}{url}" + Style.RESET_ALL)
                    
                    # Check for mentions
                    text_to_check = title + ' ' + url + ' ' + snippet
                    mention_count = extract_mentions(text_to_check, query)
                    
                    for q, count in mention_count.items():
                        if count > 0:
                            print(random.choice(counter_emojis), f"{Fore.BLUE}'{q}'{Fore.YELLOW}: {Fore.WHITE}Detected in result{Fore.RED}..." + Style.RESET_ALL)
                            all_mention_links.append({"url": url, "count": count})
                    
                    # Find social profiles
                    social_profiles = find_social_profiles(url)
                    if social_profiles:
                        for profile in social_profiles:
                            all_unique_social_profiles.add((profile["platform"], profile["profile_url"]))
                            print(random.choice(counter_emojis), f"{Fore.YELLOW}Social Profile Detected: {Fore.GREEN}{profile['platform']}{Fore.YELLOW} - {Fore.BLUE}{profile['profile_url']}" + Style.RESET_ALL)
            
            # Process related searches if available
            if "related_searches" in results:
                file.write("\nRELATED SEARCHES:\n")
                file.write("-" * 80 + "\n")
                print("\nRELATED SEARCHES:")
                
                for related in results["related_searches"]:
                    query_text = related.get("query", "")
                    file.write(f"- {query_text}\n")
                    print(f"- {query_text}")
                
                file.write("\n")
            
            # Process pagination for more results if needed
            if "pagination" in results and total_results < num_results:
                if "next" in results["pagination"]:
                    next_page = results["pagination"]["next"]
                    params["start"] = next_page
                    # Recursive call to get next page
                    # This is simplified - in a real implementation you'd want to handle this more carefully
                    # to avoid excessive API calls
                    more_results, more_mentions, more_profiles = search_with_serpapi(
                        query, language, country, date_range, num_results - total_results
                    )
                    total_results += more_results
                    all_mention_links.extend(more_mentions)
                    all_unique_social_profiles.update(more_profiles)
            
        except Exception as e:
            logger.error(f"Error during SerpAPI search: {e}")
            file.write(f"\nError during search: {e}\n")
            print(f"{Fore.RED}Error during search: {e}{Style.RESET_ALL}")
    
    print(f"\n{Fore.GREEN}Search completed. Found {total_results} results.{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Results saved to {output_file}{Style.RESET_ALL}")
    
    return total_results, all_mention_links, list(all_unique_social_profiles)

if __name__ == "__main__":
    # Example usage
    query = input("Enter search query: ")
    language = input("Enter language code (e.g., lang_en) or leave empty: ")
    country = input("Enter country code (e.g., US) or leave empty: ")
    start_date = input("Enter start date (YYYY-MM-DD) or leave empty: ")
    end_date = input("Enter end date (YYYY-MM-DD) or leave empty: ")
    
    date_range = None
    if start_date and end_date:
        date_range = (start_date, end_date)
    
    search_with_serpapi(query, language or None, country or None, date_range)
