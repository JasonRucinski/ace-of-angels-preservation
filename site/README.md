# The project's web page

The source of the GitHub Pages site,
<https://jasonrucinski.github.io/ace-of-angels-preservation/>: one page that
search engines can find and rank better than the repository itself.
`.github/workflows/pages.yml` publishes it on every push to `main` that
touches this folder or `docs/images/`, copying `docs/images/*.jpg` into
`images/` so the screenshots are not stored twice.

- `index.html`: the page, with its title, description, link-preview tags and
  a schema.org `VideoGame` description of the game.
- The look follows the official site, aceofangels.com (2001–2006), as its
  own art shows it: black pages, gold metallic small-caps titles in Cinzel
  (a Trajan-style face, from Google Fonts; "A Living Game" and the
  "AceofAngels.com" banner used this style), blue bracketed section headers
  after the site's `[ News ]` header image, and framed panels like its
  "Spotlight" art. The old pages' HTML could not be fetched when this was
  made, so colours were sampled from the site's images in `docs/images/`,
  not from its stylesheet.
- `og-image.jpg`: the 1280×640 link-preview image, also suitable for the
  repository's social preview (Settings → Social preview). Made from
  `docs/images/screenshot-flight.jpg` and `docs/images/logo.jpg`.
- `robots.txt`, `sitemap.xml`: for search engines. Update `lastmod` in the
  sitemap when the page changes.

`tests/test_site.py` checks that every local image the page uses exists,
that the page's own URLs agree, and that the structured data parses.

Before the first publish, the repository owner sets Settings → Pages →
Source to **GitHub Actions**. Facts on the page must match the README and
`docs/STATUS.md`; change them together.
