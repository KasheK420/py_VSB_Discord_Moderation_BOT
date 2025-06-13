import json
import random

import requests

from .logger import get_logger

# Initialize logger for this module
logger = get_logger("tenor_api_gif")


def get_tenor_gif(search_term: str, api_key: str, client_key: str = "my_test_app", limit: int = 10) -> str:
    """
    Fetches a random GIF URL from the Tenor API based on the search term.

    :param search_term: The keyword to search for GIFs.
    :param api_key: The Tenor API key.
    :param client_key: The client key for tracking (default: "my_test_app").
    :param limit: The maximum number of GIFs to fetch (default: 10).
    :return: A single random GIF URL or None if the API request fails.
    """
    try:
        url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={api_key}&client_key={client_key}&limit={limit}"
        response = requests.get(url)

        if response.status_code == 200:
            data = json.loads(response.content)
            if "results" in data and len(data["results"]) > 0:
                # Randomly select a GIF from the results
                random_gif = random.choice(data["results"])
                return random_gif["media_formats"]["gif"]["url"]
            else:
                logger.warning(f"No GIFs found for search term: {search_term}")
        else:
            logger.error(f"Tenor API request failed with status code {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching GIF from Tenor API: {e}")

    return None
