import re
import datetime
from bs4 import BeautifulSoup
from logging import getLogger, basicConfig, DEBUG
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from feedgen.feed import FeedGenerator

# Constants
fakeauthor = {'name': 'FGO Gamepress', 'email': 'contact@gamepress.gg', 'uri': 'https://gamepress.gg'}
baseurl = 'https://gamepress.gg'
targeturl = baseurl + '/c/fategrand-order'
logourl = 'https://gamepress.gg/grandorder/sites/grandorder/files/fgo-icon.jpg'
falseagent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246'
request = Request('https://gamepress.gg/c/fategrand-order')
request.add_header('User-Agent', falseagent)
log = getLogger('FGO-Feed-Generator')
# log.setLevel(DEBUG) # uncomment to get DEBUG logs
basicConfig()

class NoFeedTitleError(RuntimeError): pass
class NoFeedIDError(RuntimeError): pass
class NoFeedDateError(RuntimeError): pass

class FeedItem:
  def __init__(self, item):
    candidate_titles = item.find_all('div', 'feed-item-title')
    
    if len(candidate_titles) <= 0:
      raise NoFeedTitleError('Unable to find title for a feed item.')

    self.title = candidate_titles[0].a.get_text()
    log.debug('Currently working on: \"%s\"', self.title)

    path = candidate_titles[0].a['href']
    self.href = urljoin(baseurl, path)
    log.debug('\"%s\" URL: %s', self.title, self.href)

    candidate_id = re.search(r'(\d+)', candidate_titles[0].a['href'])
    if candidate_id == None:
      raise NoFeedIDError('Unable to find ID for a feed item.')

    self.id = candidate_id[0]
    log.debug('\"%s\" ID: %s', self.title, self.id)

    candidate_lang = re.search(r'(\d+)', candidate_titles[0].a['hreflang'])
    if candidate_lang == None:
      self.lang = 'en'
    else:
      self.lang = candidate_lang[0]
    log.debug('\"%s\" Language: %s', self.title, self.lang)

    candidate_images = item.find_all('div', 'feed-item-right')
    self.img = ''
    if len(candidate_images) >= 0:
      self.img = urljoin(baseurl, candidate_images[0].img['src'])
    log.debug('\"%s\" Image: %s', self.title, self.img)

    article_request = Request(self.href)
    article_request.add_header('User-Agent', falseagent)
    with urlopen(article_request) as response:
      soup = BeautifulSoup(response.read().decode(), features='lxml')
      date_candidates = soup.find_all('div', 'last-updated-date')

      if len(date_candidates) <= 0:
        # special case: even more learning with manga. images are usually labelled with their dates
        log.debug('\"%s\" No date found. Trying special case parsing', self.title)
        content_body = soup.find(id='block-gamepressbase-content')
        if content_body == None:
          raise NoFeedDateError('Unable to find feed date, variant 1')

        probable_candidate = content_body.find('img').find_next_sibling('img')
        if probable_candidate == None:
          raise NoFeedDateError('Unable to find feed date, variant 2')

        likely_match = re.search('\/grandorder\/sites\/grandorder\/files\/(\d+-\d+)', probable_candidate['src'] )
        if likely_match == None:
          raise NoFeedDateError('Unable to find feed date, variant 3')

        self.date = datetime.datetime.strptime(likely_match[1], '%Y-%m')
        log.debug('\"%s\" Guessed Inaccurate Date: %s', self.title, self.date)
      else:
        self.date = datetime.datetime.strptime(date_candidates[0].time['datetime'], '%Y-%m-%dT%H:%M:%S')
        log.debug('\"%s\" Date: %s', self.title, self.date)

      author_candidates = soup.find_all('div', 'article-credit-top')
      self.authors = []
      if len(author_candidates) > 0:
        for author in author_candidates[0].find_all('a'):
          self.authors.append({'name': author.get_text(), 'uri': author['href'], 'email': fakeauthor['email']})
      else:
        self.authors = [fakeauthor]
      log.debug('\"%s\" Authors: %s', self.title, self.authors)

  def generate_feedentry(self, fg):
    fe = fg.add_entry()

    fe.id(self.href)
    fe.title(self.title)
    fe.content(content='<img href=\"{:s}\"></img>'.format(self.img), src=self.href, type='CDATA')
    fe.link(href=self.href, hreflang=self.lang)
    fe.updated(self.date.astimezone(tz=None))
    fe.author(self.authors)

    return fe

log.debug('Opening connection to %s', targeturl)
with urlopen(request) as response:
  log.debug('Feeding page into BeautifulSoup')
  soup = BeautifulSoup(response.read().decode(), features='lxml')

  log.debug('Getting all items in feed-item-container')
  items = soup.find_all('div', class_='feed-item-container')
  fg = FeedGenerator()
  fg.id(targeturl)
  fg.link(href=targeturl, rel='alternate')
  fg.title('Fate/GO Gamepress')
  fg.subtitle('Fate/Grand Order gamepress feed')
  fg.logo(logourl)
  fg.language('en')

  for item in items:
    fi = FeedItem(item)
    log.debug('\"%s\": Generating feed entry', fi.title)
    fi.generate_feedentry(fg)

  log.debug('Finishing up, generating atom.xml')
  fg.atom_file('atom.xml')
