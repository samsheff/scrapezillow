from argparse import ArgumentParser
from pprint import pprint
import json

from scrapezillow.scraper import scrape_url


def main():
    parser = ArgumentParser()
    mutex = parser.add_mutually_exclusive_group(required=True)
    mutex.add_argument("--zpid")
    mutex.add_argument("--url")
    parser.add_argument("-t", "--request-timeout", type=int)
    args = parser.parse_args()
    pprint(json.dumps(scrape_url(**args.__dict__)))
