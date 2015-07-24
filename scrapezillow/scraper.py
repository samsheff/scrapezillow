import re
try:
    from httplib import OK
    from urlparse import urljoin
except ImportError:  # Python3
    from http.client import OK
    from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from scrapezillow import constants


def _check_for_null_result(result):
    if not result:
        raise Exception(
            "We were unable to parse crucial facts for this home. This "
            "is probably because the HTML changed and we must update the "
            "scraper. File a bug at https://github.com/hahnicity/scrapezillow/issues"
        )


def _get_sale_info(soup):
    sale_info = {"price": None, "status": None, "zestimate": None}
    value_wrapper = soup.find("div", id=constants.HOME_VALUE)
    summary_rows = value_wrapper.find_all(class_=re.compile("home-summary-row"))
    for row in summary_rows:
        pricing_re = "(Foreclosure Estimate|Below Zestimate|Rent Zestimate|Zestimate|Sold on|Sold|Price cut)(?:\xae)?:?[\n ]+-?\$?([\d,\/\w]+)"
        pricing = re.findall(pricing_re, row.text)
        status = re.findall("(For Sale|Auction|Make Me Move|For Rent|Pre-Foreclosure|Off Market)", row.text)
        if pricing:
            property_ = pricing[0][0].strip().replace(" ", "_").lower()
            sale_info[str(property_)] = pricing[0][1]
        elif status:
            sale_info["status"] = status[0]
        elif re.search("\$?[\d,]+", row.text):
            sale_info["price"] = re.findall(r"\$?([\d,]+)", row.text)[0]
    return sale_info


def _get_property_summary(soup):
    def parse_property(regex, property_):
        try:
            results[property_] = re.findall(regex, prop_summary)[0]
        except IndexError:
            results[property_] = None

    prop_summary = soup.find("header", class_=constants.PROP_SUMMARY_CLASS)
    _check_for_null_result(prop_summary)
    prop_summary = prop_summary.text
    results = {}
    parse_property(r"([\d\.]+) beds?", "bedrooms")
    parse_property(r"([\d\.]+) baths?", "bathrooms")
    parse_property(r"([\d,\.]+) sqft", "sqft")
    parse_property(r"((?:[A-Z]\w+ ?){1,}), [A-Z]{2}", "city")
    parse_property(r"(?:[A-Z]\w+ ?){1,}, ([A-Z]{2})", "state")
    parse_property(r"[A-Z]{2} (\d{5}-?(?:\d{4})?)", "zipcode")
    return results


def _get_description(soup):
    description = soup.find("div", class_=constants.DESCRIPTION)
    _check_for_null_result(description)
    return description.text


def _get_fact_list(soup):
    groups = soup.find_all("ul", constants.FACT_GROUPING)
    facts = []
    for group in groups:
        facts.extend(group.find_all(class_=constants.INDIVIDUAL_FACT))
    return facts


def _parse_facts(facts):
    parsed_facts = {}
    for fact in facts:
        if fact.text in constants.HOME_TYPES:
            parsed_facts["home_type"] = fact.text
        elif "Built in" in fact.text:
            parsed_facts["year"] = re.findall(r"Built in (\d+)", fact.text)[0]
        elif "days on Zillow" in fact.text:
            parsed_facts["days_on_zillow"] = re.findall(r"(\d+) days", fact.text)[0]
        elif len(fact.text.split(":")) == 1:
            if not "extras" in parsed_facts:
                parsed_facts["extras"] = []
            parsed_facts["extras"].append(fact.text)
        else:
            string = re.sub("( #|# )", "", fact.text)
            split = string.split(":")
            # Translate facts types to vars_with_underscores and convert unicode to string
            parsed_facts[str(split[0].strip().replace(" ", "_").lower())] = split[1].strip()
    return parsed_facts


def get_raw_html(url, timeout):
    response = requests.get(url, timeout=timeout)
    if response.status_code != OK:
        raise Exception("You received a {} error. Your content {}".format(
            response.status_code, response.content
        ))
    elif response.url == constants.ZILLOW_HOMES_URL:
        raise Exception(
            "You were redirected to {} perhaps this is because your original url {} was "
            "unable to be found".format(constants.ZILLOW_HOMES_URL, url)
        )
    else:
        return response.content


def validate_scraper_input(url, zpid):
    if url and zpid:
        raise ValueError("You cannot specify both a url and a zpid. Choode one or the other")
    elif not url and not zpid:
        raise ValueError("You must specify either a zpid or a url of the home to scrape")
    if url and "homedetails" not in url:
        raise ValueError(
            "This program only supports gathering data for homes. Please Specify your url as "
            "http://zillow.com/homedetails/<zpid>_zpid"
        )
    return url or urljoin(constants.ZILLOW_URL, "homedetails/{}_zpid".format(zpid))


def _get_ajax_url(soup, label):
    pattern = r"(\/AjaxRender.htm\?encparams=[\w\-_~=]+&rwebid=\d+&rhost=\d)\",jsModule:\"{}".format(label)
    url = re.search(pattern, soup.text)
    _check_for_null_result(url)
    ajax_url = "http://www.zillow.com" + url.group(1)
    return ajax_url


def _get_table_body(ajax_url, request_timeout):
    html = get_raw_html(ajax_url, request_timeout)
    pattern = r' { "html": "(.*)" }'
    html = re.search(pattern, str(html)).group(1)
    html = re.sub(r'\\"', r'"', html)  # Correct escaped quotes
    html = re.sub(r'\\/', r'/', html)  # Correct escaped forward slashes
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:  # It doesn't have a price/tax history
        raise ValueError("There is no table history for url {}".format(ajax_url))
    table_body = table.find('tbody')
    return table_body


def _get_price_history(ajax_url, request_timeout):
    table_body = _get_table_body(ajax_url, request_timeout)
    data = []

    rows = table_body.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        cols = [ele for ele in cols]
        date = cols[0].get_text()
        event = cols[1].get_text()
        price = cols[2].find('span').get_text()

        data.append([date, event, price])
    return data


def _get_tax_history(ajax_url, request_timeout):
    data = []
    try:
        table_body = _get_table_body(ajax_url, request_timeout)
    except ValueError:
        return data

    rows = table_body.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        cols = [ele for ele in cols]
        date = cols[0].get_text()
        tax = cols[1].contents[0]
        assessment = cols[3].get_text()

        data.append([date, tax, assessment])
    return data


def populate_price_and_tax_histories(soup, results, request_timeout):
    history_url = _get_ajax_url(soup, "z-hdp-price-history")
    results["price_history"] = _get_price_history(history_url, request_timeout)
    tax_url = _get_ajax_url(soup, "z-expando-table")
    results["tax_history"] = _get_tax_history(tax_url, request_timeout)


def scrape_url(url, zpid, request_timeout):
    """
    Scrape a specific zillow home. Takes either a url or a zpid. If both/neither are
    specified this function will throw an error.
    """
    url = validate_scraper_input(url, zpid)
    soup = BeautifulSoup(get_raw_html(url, request_timeout), 'html.parser')
    results = _get_property_summary(soup)
    facts = _parse_facts(_get_fact_list(soup))
    results.update(**facts)
    results.update(**_get_sale_info(soup))
    results["description"] = _get_description(soup)
    populate_price_and_tax_histories(soup, results, request_timeout)
    return results
