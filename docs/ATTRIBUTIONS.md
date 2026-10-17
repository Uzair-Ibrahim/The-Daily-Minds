# Dependencies and references

Editorial images are selected exclusively from publisher-supplied RSS metadata/HTML.
Original image URLs, metadata origins and supplied credits are retained in new saved
editions. Where photographer credit is unavailable, the UI says "Image via [source]"
rather than inventing a photographer or license. Image copyrights remain with their
owners; metadata availability is not a redistribution-license audit. No stock-image
API, generated news photography, page scraping or newly granted content license is used.
Pillow, already in the dependency lock, is now required at runtime to validate, resize
and re-encode JPEG/PNG/WebP delivery; its bundled license information still applies.

## Application license status

No application-wide open-source license has been selected by the owner. Publication
does not add a license grant. Third-party packages and publisher content retain their
respective licenses and rights; the references below document those dependencies.

No reference server or complete solution was cloned. Application code is newly written.
Direct dependency projects and their declared licenses:

| Project | License | Reference |
|---|---|---|
| FastMCP | Apache-2.0 | https://github.com/PrefectHQ/fastmcp |
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| HTTPX | BSD-3-Clause | https://github.com/encode/httpx |
| Exa Python SDK (exa-py) | MIT | https://github.com/exa-labs/exa-py |
| Pydantic / pydantic-settings | MIT | https://github.com/pydantic/pydantic-settings |
| pytest | MIT | https://github.com/pytest-dev/pytest |
| pytest-asyncio | Apache-2.0 | https://github.com/pytest-dev/pytest-asyncio |

Retain applicable copyright notices, license text and NOTICE files when redistributing
dependencies; inspect the locked transitive packages before packaging a distribution.
This table is not a completed competition rules or redistribution audit.
License names above were also checked against installed package metadata.

Daily Mind additions: feedparser (RSS/Atom parser), Playwright/Chromium (local rendering
and browser tests), tzdata (timezone database), pypdf (PDF sanity checks), pypdfium2 and
Pillow (local page rasterization), React, Vite, Tailwind CSS, Lucide icons, clsx and
tailwind-merge. Keep their bundled licenses/transitive notices with redistributions.
System Georgia/Arial fonts are referenced, not bundled or downloaded.

RSS sources: https://feeds.bbci.co.uk/ , https://www.dawn.com/feeds/home ,
https://www.theguardian.com/world/rss and https://news.google.com/rss . Descriptions
are attributed, length-bounded publisher excerpts; copyrights remain with publishers.
Google News RSS links may redirect to originals. Check event/provider terms before
public distribution; this is a local reader, not a license to republish full articles.

Exa and Tavily are external services, not redistributed source. API access, returned snippets
and source content remain subject to provider/source terms. No competition rules have
been supplied; compliance and permitted prebuilt work must be confirmed before submission.

Implementation references checked:

- https://exa.ai/docs/reference/search
- https://github.com/exa-labs/exa-py (official Python SDK; pinned installed API verified)
- Installed `build-with-exa` coding skill used for integration (development tooling,
  not part of the published application).

- https://gofastmcp.com/clients/transports
- https://gofastmcp.com/clients/tools
- https://docs.tavily.com/documentation/api-reference/endpoint/search
- https://help.tavily.com/articles/4840311948-tavily-search-api
- https://github.com/modelcontextprotocol/inspector

Optional authentication uses the official [`@supabase/supabase-js`](https://github.com/supabase/supabase-js) SDK (MIT) and [PyJWT](https://github.com/jpadilla/pyjwt) (MIT), with cryptography for asymmetric JWT verification.
