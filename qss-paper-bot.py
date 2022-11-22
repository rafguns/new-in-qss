import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import requests_html
from mastodon import Mastodon


@dataclass
class Article:
    title: str
    url: str
    # DOI is part of the URL but probably more persistent.
    # Used to ensure we don't toot the same article twice
    doi: str
    authors: List[str]

    @classmethod
    def from_html(cls, html):
        title_el = html.find(".al-title a")[0]
        title = title_el.text
        url = title_el.absolute_links.pop()  # `absolute_links`is a one-element set

        doi_match = re.search("/doi/(10\.\d+/.+?)/", url)
        if not doi_match:
            raise ValueError("Could not extract DOI frorm url {url}")
        doi = doi_match.group(1)

        authors = [el.text for el in html.find("div.al-authors-list .wi-fullname")]

        return cls(title, url, doi, authors)

    def to_message(self, char_limit=500):
        author_list = ", ".join(self.authors)

        # To avoid exceeding the character limit, we trim the author list if needed
        # 5 is the number of extra characters in the message (2 newlines and "by ")
        total_length = len(self.title) + len(author_list) + len(self.url) + 5
        if total_length > char_limit:
            # 1 to make extra space for ellipsis
            author_list_length = total_length - char_limit - 1
            author_list = author_list[:author_list_length] + "…"

        return f"{self.title}\nby {author_list}\n{self.url}"


def get_article_divs(session):
    r = session.get("https://direct.mit.edu/")
    r.raise_for_status()
    print(r.html.raw_html)
    return r.html.find("div.al-article-items")


def update():
    # Get articles from QSS site
    session = requests_html.HTMLSession()
    article_divs = get_article_divs(session)
    articles = [Article.from_html(article_div) for article_div in article_divs]
    dois_on_page = {article.doi for article in articles}

    # Determine new DOIs/articles
    tooted_dois_file = Path("./tooted-dois.txt")
    with open(tooted_dois_file, encoding="utf-8") as fh:
        tooted_dois = {line.rstrip("\n") for line in fh}
    new_dois = dois_on_page - tooted_dois
    new_articles = [article for article in articles if article.doi in new_dois]

    # Connect to Mastodon instance
    access_token = os.environ["BOTSIN_SPACE_ACCESS_TOKEN"]
    mastodon = Mastodon(
        access_token=access_token,
        api_base_url="https://botsin.space/",
        ratelimit_method="pace",
    )

    # Post all new articles
    for article in new_articles:
        mastodon.status_post(article.to_message())
        print(f"Tooted article '{article.title}'")

    # Register that we've posted these articles
    with open(tooted_dois_file, mode="a", encoding="utf-8") as fh:
        for doi in new_dois:
            fh.write(doi)


if __name__ == "__main__":
    update()
