import sys
import urllib.request
headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }
def get_html(url):
        res = None

        req = urllib.request.Request(url, headers=headers)
        try:
            site = urllib.request.urlopen(req)
        except urllib.request.HTTPError as err:
            print("HTTP Error %s: %s: \"%s\"") % (err.code, err.reason, url)
        else:
            # leave the decoding up to bs4
            res = site.read()
            site.close()

            # try to read encoding from headers otherwise use utf-8 as fallback
            encoding = site.headers.get_content_charset()
            res = res.decode(encoding.lower() if encoding else "utf-8")
            print("Getting html done!")

        return res
        
with open(sys.argv[2], "w", encoding="UTF-8") as f:
    f.write(get_html(sys.argv[1]))