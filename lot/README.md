# unnamed — car culture magazine + store (Django)

One Django codebase: storefront, cart, Stripe Checkout, accounts, blog ("Journal"), and admin.
Django templates + Tailwind CSS, no JavaScript framework. "unnamed" is a placeholder brand name — set `BRAND_NAME` in `.env` to rename it.

## Quick start

```bash
cd lot
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
python manage.py migrate
python manage.py seed           # 8 products, 6 blog posts, reviews, shipping
python manage.py createsuperuser   # your secret admin username + password
python manage.py runserver
```

Open http://127.0.0.1:8000 for the store. The admin lives at the **secret path** in `ADMIN_URL` (e.g. http://127.0.0.1:8000/studio-xyz/); `/admin/` returns 404. Nothing on the public site links to it.

`seed --admin` additionally creates a local `admin` / `admin12345` superuser (only with `DEBUG=1`). **Never** use that account in production.

`seed` is safe to re-run. `seed --reset` wipes the catalog and blog and starts over.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required when `DEBUG=0`. |
| `DEBUG` | `1` locally, `0` in production. |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Comma-separated. |
| `ADMIN_URL` | Secret admin path, e.g. `studio-8f3kq29xz`. Required when `DEBUG=0`. Defaults to `admin` locally if unset. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Only read by `manage.py ensure_admin`. Remove the password afterwards. |
| `TRUST_X_FORWARDED_FOR` | `1` behind a proxy you control, so login/comment rate limits see real visitor IPs. |
| `DATABASE_URL` | Unset = SQLite (`db.sqlite3`). Set e.g. `postgres://user:pass@host:5432/lot` for Postgres (the `psycopg` driver is in requirements). |
| `BLOG_MAX_UPLOAD_MB` | Max photo upload size (default 15). |
| `S3_BUCKET` (+ `S3_ENDPOINT_URL`, `S3_REGION`, `S3_CUSTOM_DOMAIN`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) | Optional: store uploads in S3/R2/B2 instead of `media/`. Needs `pip install "django-storages[s3]"`. |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Outgoing email (comment notifications). Default prints to the console. |
| `STRIPE_SECRET_KEY` | Server-side only. Used in the checkout view. |
| `STRIPE_PUBLISHABLE_KEY` | Public key, exposed to templates as `stripe_publishable_key` (not needed for redirect checkout). |
| `STRIPE_WEBHOOK_SECRET` | Verifies webhook signatures. |
| `BRAND_NAME`, `STORE_CURRENCY`, `CURRENCY_SYMBOL` | Storefront settings. |

Stripe secrets are read in `config/settings.py` and used only in `shop/views.py`. No template ever receives them.

## Stripe setup (test mode)

1. Copy your test keys from https://dashboard.stripe.com/test/apikeys into `.env` (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`).
2. Install the Stripe CLI (https://stripe.com/docs/stripe-cli) and run:
   ```bash
   stripe login
   stripe listen --forward-to localhost:8000/stripe/webhook/
   ```
   The CLI prints `whsec_...`. Put it in `.env` as `STRIPE_WEBHOOK_SECRET`, then restart `runserver`.
3. Add something to the cart, check out, and pay with card `4242 4242 4242 4242` (any future date, any CVC).
4. Stripe redirects you to `/checkout/success/`. The webhook (`checkout.session.completed`) marks the order **Paid** and decrements stock. Refresh the thank-you page to see "Payment confirmed".

**Production:** in the Stripe Dashboard → Developers → Webhooks, add an endpoint `https://yourdomain.com/stripe/webhook/` with these events:
`checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`.
Use that endpoint's signing secret as `STRIPE_WEBHOOK_SECRET`.

### How checkout works

1. `/checkout/` collects email, address, and a shipping method (guest checkout; logged-in users get the order linked to their account).
2. The view creates a **pending** `Order` with its line items, then creates a Stripe Checkout Session (line items + shipping rate + `metadata.order_id`) and redirects to Stripe.
3. Success URL: `/checkout/success/?session_id={CHECKOUT_SESSION_ID}`. Cancel URL: `/checkout/cancel/`, which goes back to the cart.
4. `/stripe/webhook/` verifies the signature, then in one transaction marks the order paid and decrements each variant's stock. This is idempotent, so Stripe retries never double-count. Stock never drops below 0.
5. An expired or failed session marks a pending order **Cancelled**.

Stock is checked when items are added to the cart and again at checkout. It isn't reserved during payment, so two buyers could race for the last unit. Fine for a small shop; check the low-stock panel on the admin dashboard.

## Admin

- **Dashboard:** paid orders to ship, orders awaiting payment, unread messages, low-stock list.
- **Products:** variants (size/color, SKU, optional price override, stock) and images inline. Edit price and visibility from the list.
- **Inventory:** every variant, sorted by stock, with stock editable directly in the list. Filter by sold out / low / in stock. This is where you adjust stock by hand.
- **Orders:** payment status, editable fulfillment status and tracking number, bulk "mark packing/shipped/delivered". Orders are only created by checkout.
- **Blog:** posts (writing editor, see below), tags, media library, comments, blog settings.
- **Storefront:** homepage featured products (ordered), homepage reviews, contact messages.
- Shipping methods and categories.

When every variant of a product hits 0, the product page hides add-to-cart and shows "Sold out". A variant at 0 is disabled in the picker.

### Turning the store off (blog-only site)

Admin → **Core → Site settings** (or the "Store On/Off" card on the dashboard) → untick **Store enabled** → Save. It takes effect immediately:

- Shop, product, cart, checkout, account, login/register, and FAQ pages return 404 to visitors. Shop links, the cart and account icons, and the "Shop the story" block on posts disappear.
- The home page keeps the hero but points to the journal and lists the latest six posts.
- Nothing is deleted: products, orders, and customer accounts stay in the admin. While logged in as staff you can still open shop pages directly to check them.
- The Stripe webhook keeps working, so payments for orders placed before the switch are still recorded.

Tick the box again to bring the store back.

## Pages

| URL | Page |
| --- | --- |
| `/` | Home: full-screen hero, featured products, reviews, section tiles |
| `/shop/`, `/shop/<category>/` | Collection with sorting |
| `/products/<slug>/` | Product: gallery, variants, stock, add to cart |
| `/cart/`, `/checkout/` | Cart and checkout |
| `/account/`, `/account/login/`, `/account/register/` | Account and order history |
| `/blog/`, `/blog/?q=…` | Blog home: featured post, then posts grouped under month headings, a month bar, search, pagination |
| `/blog/<year>/<month>/` (e.g. `/blog/2026/10/`) | All posts from that month, with links to the newer/older month |
| `/blog/tag/<slug>/` | Posts with a tag |
| `/blog/<slug>/` | Post with comments and related posts |
| `/blog/feed/` | RSS feed |
| `/journal/…` | Old blog URLs; permanently redirect to `/blog/…` |
| `/faq/`, `/contact/` | Info pages |
| `/404/` | Preview of the 404 page (DEBUG only; the real 404 shows when `DEBUG=0`) |

Blog posts output JSON-LD (`BlogPosting`/`Article`/`NewsArticle`), Open Graph tags, and a canonical URL. Product pages output `Product` JSON-LD.

## Blog

The nav link is **Journal** (rename it in `templates/partials/header.html`; the blog's own heading comes from Blog settings).

### Admin access (the secret portal)

- The admin is at `/<ADMIN_URL>/`. `/admin/` is a 404, and no public page links to the admin.
- Log in with a **staff** account. Create it with `python manage.py createsuperuser`, or on a host without a shell set `ADMIN_USERNAME` / `ADMIN_PASSWORD` and run `python manage.py ensure_admin` (then remove the password variable). Change a password with `python manage.py changepassword <username>`.
- Customer accounts (`/account/register/`) are never staff, so they only ever see the storefront. Django's admin rejects them even if they find the URL.
- Admin and customer logins allow 10 attempts per 15 minutes per IP, then return HTTP 429. With several server processes, configure a shared cache (Redis or database) so the limit is global.
- Staff see a small "Edit post" link on published posts. Visitors never do.

### Writing posts

Admin → **Blog → Posts → Add post** (or "Write a post" on the dashboard) opens the editor:

- Title, slug (auto-generated if blank), excerpt, and a Markdown body with a toolbar for headings, bold, italics, links, quotes, lists, dividers, and photos. Shortcuts: Ctrl+B / Ctrl+I / Ctrl+K, **Ctrl+S saves**.
- **Write / Split / Preview** modes. The preview uses the real site stylesheet. **Preview** in the top bar opens a full-page preview of what's in the editor, without saving.
- **Photos:** the Photo button, drag & drop, or paste. Images are auto-rotated, stripped of camera/GPS metadata, resized (2000 px for article photos, 2400 px for covers, plus smaller thumbnails), and given random file names. **Library** reuses earlier uploads.
  - An image on its own line becomes a full-width photo. The text in `![…]` is its caption (`![](url)` = no caption; `![alt](url "Caption")` when alt text and caption should differ).
  - Several images on consecutive lines (no blank line between) become a gallery. The Gallery button does this for you.
- **Save draft / Publish / Update / Unpublish.** Drafts are only visible to staff. A future publish date schedules the post, and it stays hidden until then. "Updated on" is optional and shown on the post.
- **Unsaved changes:** the top bar shows the save state, and the browser warns before you leave with unsaved edits. Your text is backed up to the database a few seconds after you stop typing. If you return to a post with a newer backup than the saved version, you're offered **Restore** or **Discard**.
- **Delete post…** (sidebar) goes to a confirmation page.
- Sidebar: publish date, updated date, featured (the newest featured post leads the blog home), allow comments, author, cover photo with description and caption, tags, SEO description, and "Shop the story" products.

Existing posts written as HTML or plain text still render. All post HTML is sanitized (no scripts, iframes, or event handlers).

### Comments

- Guests comment with an optional display name, a required email (never shown publicly), and the comment. No account needed.
- Spam protection: a hidden honeypot field, a signed form token (rejects posts made under 3 seconds after loading or more than 2 days later), per-IP limits (3 per 10 minutes, 20 per day; IPs are stored only as a keyed hash), duplicate detection, more than 2 links means held for review, and a blocked-words list that sends matches to spam.
- Comments are plain text, escaped when shown; HTML can't be injected.
- Moderation: Admin → **Blog → Comments** opens on "Awaiting approval", with bulk Approve / Reject / Mark as spam, plus delete. The dashboard shows the pending count. Blog settings control: comments on/off, require approval, auto-approve returning commenters, a notification email, and blocked words.
- Retention: the privacy notice under the form explains email use. Run `python manage.py prune_comments --days 30` (e.g. as a daily cron) to delete old rejected and spam comments along with their emails.

### Blog settings

Admin → **Blog → Blog settings**: heading, intro line, posts per page, and the comment options above.

## Tailwind CSS

The compiled stylesheet `static/css/app.css` is committed, so `runserver` works without Node. If you change classes in templates, rebuild with the standalone Tailwind CLI (v3.4):

```bash
# download once from https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17 into bin/
bin/tailwindcss -i assets/input.css -o static/css/app.css --minify          # build
bin/tailwindcss -i assets/input.css -o static/css/app.css --watch           # while editing
```

Theme colors (`forest` #2c570e, `ink` black, `bone` off-white) and fonts live in `tailwind.config.js`. The admin theme is `static/css/admin.css`.

Store sections are the product categories (Apparel, Car Accessories, Accessories, Stickers). Add, rename, or reorder them in the admin under Shop → Categories; the nav, footer, and home tiles update automatically.

## Images

The seed command draws original placeholder product art with Pillow (`core/placeholder_art.py`) into `media/`. Replace it with real photos in the admin (product → images). The homepage hero is `static/img/hero.jpg`; swap in your own file with the same name.

## Tests

```bash
python manage.py test
```

Covers cart stock limits, sold-out hiding, the checkout → Stripe redirect (mocked), webhook signature checks, paid status, stock decrement, idempotency, page rendering, store sections, registration, and admin screens.

Blog tests (`blog/tests.py`) cover: Markdown rendering and sanitizing (scripts, event handlers, `javascript:` links); figures and galleries; draft and scheduled posts hidden from list, search, month archive, feed, and detail pages, even for logged-in customers; month archive navigation; staff-only previews; save draft, publish, schedule, and unpublish; delete confirmation; autosave and restore; the upload pipeline (EXIF/GPS stripped, rotation fixed, resized, non-images rejected); the editor endpoints refusing non-staff; comment moderation, escaping, honeypot, token timing, rate limits, duplicates, blocked words, and email privacy; admin and login throttling; the secret admin path; and that public pages never reveal the admin URL.

## Database: SQLite now, Postgres when you're ready

Local development uses SQLite (`db.sqlite3`) as long as `DATABASE_URL` is unset. The project is ready for Postgres:

1. Get a Postgres database. Locally: `docker compose up -d` (Postgres 17 on 127.0.0.1:5432, user/password `lot`/`lot`), or install Postgres from postgresql.org. Hosted options (Neon, Supabase, Render, Railway) give you a ready-made URL. If you create the database yourself:
   ```sql
   CREATE USER lot WITH PASSWORD 'a-strong-password' CREATEDB;
   CREATE DATABASE lot OWNER lot;
   ```
   (`CREATEDB` lets `python manage.py test` create its `test_lot` database.)
2. In `.env`: `DATABASE_URL=postgres://lot:a-strong-password@127.0.0.1:5432/lot`
3. `python manage.py migrate`, then `python manage.py createsuperuser` (and `seed` for demo content).

Moving existing SQLite content into Postgres:

```bash
# with DATABASE_URL unset (SQLite):
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions --indent 2 -o backup.json
# then set DATABASE_URL to Postgres:
python manage.py migrate
python manage.py loaddata backup.json
```

Uploaded photos aren't in the database. Copy the `media/` folder too (or keep using the same storage).

The `psycopg[binary]` driver installs from ready-made wheels on Windows, macOS and Linux, so no system packages are needed.

## Deploying (outline)

1. Set `DEBUG=0`, `SECRET_KEY`, `ADMIN_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (Postgres), and the Stripe keys. Behind a platform proxy, also set `TRUST_X_FORWARDED_FOR=1`.
2. `python manage.py migrate && python manage.py collectstatic --noinput`
3. Create the admin: `python manage.py createsuperuser`, or `ensure_admin` with `ADMIN_USERNAME`/`ADMIN_PASSWORD`.
4. Run `gunicorn config.wsgi` behind HTTPS. WhiteNoise serves static files.
5. **Uploaded photos must live somewhere persistent.** Either a persistent disk mounted at `media/` with `SERVE_MEDIA=1`, or object storage via `S3_BUCKET` (recommended on hosts with ephemeral filesystems like Heroku or Render without a disk). Posts and comments live in the database, so back up Postgres (e.g. a nightly `pg_dump` or your host's automated backups).
6. Optional: a daily `python manage.py prune_comments`.
7. Configure the Stripe webhook endpoint as described above.

## Project layout

```
config/   settings, urls
core/     home, FAQ, contact, accounts, featured products, reviews, seed command, admin dashboard
shop/     catalog, variants/inventory, session cart, orders, checkout + Stripe webhook
blog/     posts, month archive, tags, media library, comments + moderation, Markdown rendering/sanitizing,
          image processing, admin writing editor (templates/admin/blog/post/editor.html, static/js/editor.js)
templates/  base layout, partials, account pages, 404/500, admin overrides
static/   compiled CSS, admin theme, small vanilla JS (gallery, variant picker, cart steppers)
```
