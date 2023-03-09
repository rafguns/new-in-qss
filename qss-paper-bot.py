import os
from dataclasses import dataclass
from pathlib import Path

import requests
from mastodon import Mastodon


@dataclass
class Article:
    title: str
    url: str
    doi: str
    authors: list[str]

    @classmethod
    def from_dict(cls, data):
        title = data["title"][0]
        authors = [au["given"] + " " + au["family"] for au in data["author"]]

        return cls(title, data["URL"], data["DOI"], authors)

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


def latest_articles(issn="2641-3337", num_items=20):
    url = f"http://api.crossref.org/journals/{issn}/works"
    params = {"sort": "published-online", "order": "desc", "rows": num_items}
    if email := os.environ.get("EMAIL"):
        params["mailto"] = email

    r = requests.get(url, params=params)
    r.raise_for_status()

    data = r.json()
    if data["status"] != "ok":
        raise Exception(f"Unexpected status {data['status']}")

    return data["message"]["items"]


def update():
    # Get articles from CrossRef
    article_dicts = latest_articles(num_items=10)
    articles = [
        Article.from_dict(article_dict) for article_dict in reversed(article_dicts)
    ]
    latest_dois = {article.doi for article in articles}

    # Determine new DOIs/articles
    tooted_dois_file = Path("./tooted-dois.txt")
    with open(tooted_dois_file, encoding="utf-8") as fh:
        tooted_dois = {line.rstrip("\n") for line in fh}
    new_dois = latest_dois - tooted_dois
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
        print(f"Tooted article '{article.title}' {article.doi}")

    # Register that we've posted these articles
    with open(tooted_dois_file, mode="a", encoding="utf-8") as fh:
        for article in new_articles:
            fh.write(article.doi + "\n")


if __name__ == "__main__":
    update()
