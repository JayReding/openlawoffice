# Font Awesome and app icon

## Vendored assets

Font Awesome Free is self-hosted rather than loaded from a CDN so the app keeps
its strict same-origin Content Security Policy and works without internet
access.

- Version: **6.7.2**
- Package: `@fortawesome/fontawesome-free`
- Source: <https://fontawesome.com>
- Location: `openlawoffice/static/vendor/fontawesome/`
- Bundled files:
  - `css/all.min.css`
  - `webfonts/` (Solid, Regular, Brands, and compatibility web fonts)
  - `LICENSE.txt`
  - `README.txt`

The base template loads the stylesheet with:

```jinja
{{ url_for('static', filename='vendor/fontawesome/css/all.min.css') }}
```

No application JavaScript is required. Font files are served from `'self'`, so
no CSP changes are necessary.

## App icon

The fallback app branding uses the Font Awesome Solid **scale-balanced** icon:

```html
<i class="fa-solid fa-scale-balanced" aria-hidden="true"></i>
```

It appears when no firm logo has been uploaded:

- Authenticated header
- Login page
- First-run setup page
- Firm logo placeholder in settings

A firm-uploaded logo still takes precedence in the header and login page.

The browser favicon is a local SVG at
`openlawoffice/static/img/scale-balanced.svg`.

## Licensing and attribution

Font Awesome Free licensing:

- Icons: CC BY 4.0
- Fonts: SIL OFL 1.1
- Code: MIT

The complete license is included at
`openlawoffice/static/vendor/fontawesome/LICENSE.txt`. The site footer also
credits “Icons: Font Awesome Free” with a link to fontawesome.com.

## Updating Font Awesome

1. Download the desired `@fortawesome/fontawesome-free` npm tarball.
2. Replace `css/all.min.css` and the contents of `webfonts/`.
3. Replace `LICENSE.txt` and update `README.txt` with the new version.
4. Verify the new package still contains `fa-scale-balanced`.
5. Run the test suite and visually check the header, login, and setup pages.

Do not load Font Awesome from a third-party CDN without updating the CSP and
considering offline operation.
