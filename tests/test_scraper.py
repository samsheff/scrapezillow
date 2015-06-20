from nose.tools import assert_greater, eq_, ok_

from scrapezillow.scraper import scrape_url

zpid_1_expected = {
    'city': u'Berkeley',
    'bathrooms': u'2',
    'sqft': u'1,470',
    'bedrooms': u'3',
    'zipcode': u'94703',
    'state': u'CA',
}


def test_scrape_url():
    zpid = "2101920883"
    response = scrape_url(None, zpid, 5)
    for k, v in zpid_1_expected.items():
        eq_(response[k], v)
    assert_greater(int(response['price'].replace(',', '')), 0)
    ok_(response['description'])
    ok_(response['price_history'])
