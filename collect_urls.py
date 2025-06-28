


class UrlCollector:
    def __init__(self, urls):
        self.urls = urls

    def collect_urls(self):
        collected_urls = []
        for url in self.urls:
            if url.startswith("https://"):
                collected_urls.append(url)
        return collected_urls   