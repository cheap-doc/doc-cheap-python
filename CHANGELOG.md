# Changelog

## 0.2.0

- The README said nothing is stored under the sandbox key. In fact the public
  sandbox key `sk_sandbox_public` keeps a record of every scan for one year,
  with a reduced thumbnail and the address it came from, and cannot read it
  back; an account's own sandbox key stores nothing. The text now says so, and
  asks for test images only, never a real document.

- `issuing_state_detail` and `nationality_detail` on the scan's document and
  holder, typed as the new `CountryCodeDetail`: the country code as the
  document writes it, its ISO 3166-1 alpha-3 and alpha-2, and its category.

## 0.1.0

- First release: `Client` with `recognize`, `get_scan`, `list_scans`,
  `delete_scan` and `usage`; typed answers; an exception per API error code;
  the key from an argument or the `DOC_CHEAP_API_KEY` environment variable.
