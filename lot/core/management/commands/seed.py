from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from blog.models import MediaAsset, Post, Tag
from core import placeholder_art as art
from core.models import FeaturedProduct, Review
from shop.models import Category, Product, ProductImage, ShippingMethod, Variant

INK, BONE, FOREST = art.INK, art.BONE, art.FOREST
# Bump when the placeholder art changes so browsers don't show cached old images.
ART_VERSION = "forest"

CATEGORIES = [
    ("apparel", "Apparel", "Heavyweight tees and hoodies. Boxy fits, small runs."),
    ("car-accessories", "Car Accessories", "Plate frames, fresheners, and garage-tested parts for the daily and the weekend car."),
    ("accessories", "Accessories", "Caps, keychains, and the small stuff you carry every day."),
    ("stickers", "Stickers", "Outdoor-rated vinyl. Made to outlast the clear coat."),
]

SHIPPING = [
    ("Standard", "5–7 business days, tracked", "6.00"),
    ("Express", "2–3 business days, tracked", "18.00"),
    ("Local pickup", "Pick up from the shop, by appointment", "0.00"),
]

# (bg, body, print, accent) per image; views map 1:1 to the colorways list.
PRODUCTS = [
    {
        "slug": "night-shift-tee", "name": "Night Shift Tee", "category": "apparel", "price": "38.00",
        "kind": "tee", "featured": 1,
        "tagline": "7 oz heavyweight cotton. Boxy, slightly cropped.",
        "description": "Our everyday tee, built heavy so it holds its shape after a hundred washes. "
                       "Small chest hit up front, full back print behind.",
        "details": "100% ring-spun cotton, 7 oz\nBoxy fit — size up for a longer body\nScreen printed by hand\nPre-shrunk",
        "images": [("front", (BONE, INK, BONE, FOREST)), ("back", (BONE, FOREST, BONE, INK)), ("detail", (BONE, INK, BONE, FOREST))],
        "variants": [("S", 6), ("M", 10), ("L", 8), ("XL", 3)],
    },
    {
        "slug": "garage-hours-hoodie", "name": "Garage Hours Hoodie", "category": "apparel", "price": "88.00",
        "kind": "hoodie", "featured": 2,
        "tagline": "14 oz fleece. Double-lined hood. Built for cold garages.",
        "description": "A thick, warm hoodie with a roomy fit and ribbed cuffs that stay put. "
                       "Oversized back print, tonal drawcords.",
        "details": "80/20 cotton-poly fleece, 14 oz\nDouble-layer hood\nKangaroo pocket\nRelaxed fit",
        "images": [("front", (INK, FOREST, BONE, BONE)), ("back", (INK, FOREST, BONE, BONE)), ("detail", (INK, FOREST, BONE, BONE))],
        "variants": [("S", 4), ("M", 0), ("L", 5), ("XL", 2)],
    },
    {
        "slug": "apex-6-panel-cap", "name": "Apex 6-Panel Cap", "category": "accessories", "price": "34.00",
        "compare_at_price": "40.00", "kind": "cap", "featured": 3,
        "tagline": "Unstructured cotton twill with a curved brim.",
        "description": "Low-profile six-panel cap with an embroidered front and an adjustable strap.",
        "details": "Cotton twill\nEmbroidered front\nAdjustable strap with metal buckle\nOne size fits most",
        "images": [("front", (FOREST, INK, BONE, BONE)), ("back", (FOREST, INK, BONE, BONE))],
        "variants": [("One size", 12)],
    },
    {
        "slug": "low-and-slow-plate-frame", "name": "Low & Slow Plate Frame", "category": "car-accessories",
        "price": "29.00", "kind": "plate", "featured": 4,
        "tagline": "Slim ABS frame for standard US plates.",
        "description": "A slim frame that doesn't cover your registration stickers. Hardware included.",
        "details": "UV-stable ABS\nFits standard US 12 × 6 in. plates\nStainless hardware included\nCheck local laws before installing",
        "images": [("front", (BONE, INK, BONE, FOREST)), ("back", (BONE, INK, BONE, FOREST)), ("detail", (BONE, INK, BONE, FOREST))],
        "variants": [("Gloss black", 15), ("Matte black", 2)],
    },
    {
        "slug": "pit-lane-air-freshener", "name": "Pit Lane Air Freshener", "category": "car-accessories",
        "price": "8.00", "kind": "freshener", "featured": 5,
        "tagline": "Hangs from the mirror. Lasts about 30 days.",
        "description": "A die-cut paper freshener in three scents we actually like. Strong for a week, then steady.",
        "details": "Lasts 30–40 days\nDie-cut fiberboard\nElastic hanging cord",
        "images": [("front", (BONE, INK, BONE, FOREST), "BLACK ICE"), ("front", (INK, FOREST, BONE, BONE), "CITRUS SMOKE"), ("front", (FOREST, BONE, INK, FOREST), "CEDAR GARAGE")],
        "variants": [("Black Ice", 40), ("Citrus Smoke", 25), ("Cedar Garage", 0)],
    },
    {
        "slug": "tow-loop-keychain", "name": "Tow Loop Keychain", "category": "accessories", "price": "16.00",
        "kind": "keychain",
        "tagline": "Woven tow-strap keychain with a steel ring.",
        "description": "Inspired by track tow straps. Tough nylon webbing, a heavy split ring, and a printed tag.",
        "details": "Nylon webbing\nSteel split ring\nAbout 5 in. long",
        "images": [("front", (BONE, FOREST, BONE, INK)), ("front", (INK, "#2a2a2a", BONE, FOREST))],
        "variants": [("Forest", 20), ("Black", 14)],
    },
    {
        "slug": "drive-at-night-sticker", "name": "Drive At Night Sticker", "category": "stickers", "price": "5.00",
        "kind": "diecut", "featured": 6,
        "tagline": "Die-cut vinyl with a UV laminate.",
        "description": "Our core logo sticker. Thick white border, outdoor-rated, safe for paint and glass.",
        "details": "Outdoor-rated vinyl\nUV and scratch-resistant laminate\nDishwasher safe (for your bottle, not your car)",
        "images": [("front", (BONE, FOREST, BONE, FOREST)), ("back", (FOREST, INK, BONE, BONE))],
        "variants": [("3 in.", 100), ("5 in.", 60, "8.00")],
    },
    {
        "slug": "sticker-pack-vol-1", "name": "Sticker Pack Vol. 1", "category": "stickers", "price": "14.00",
        "kind": "pack",
        "tagline": "Six stickers from the first season.",
        "description": "A mixed pack of six designs from our first run. This pack is sold out — the admin shows how to restock it.",
        "details": "6 stickers, 2–4 in.\nOutdoor-rated vinyl",
        "images": [("front", (BONE, INK, INK, FOREST)), ("back", (INK, INK, INK, FOREST))],
        "variants": [("Pack of 6", 0)],
    },
]

REVIEWS = [
    ("Kenji M.", "Osaka", "Heaviest tee I own. Washed it twenty times and it still looks new.", 5),
    ("Dani R.", "Los Angeles", "The plate frame is so clean. It doesn't cover my tags and looks factory.", 5),
    ("Theo B.", "Melbourne", "Ordered on Monday, wearing the hoodie at Friday's meet.", 5),
    ("Sam K.", "Toronto", "The stickers survived a winter on my bumper. That's the review.", 4),
]

# Car-ownership journal entries, written in Markdown. {photo:N} becomes an uploaded media-library image.
JOURNAL_POSTS = [
    {
        "slug": "day-one-bringing-her-home",
        "title": "Day One: Bringing Her Home",
        "excerpt": "Three hundred miles, one cash envelope, and a coupe that had been sitting under a cover for two years.",
        "tags": ["Ownership", "Project Car"],
        "days_ago": 76,
        "cover": ("#f4f4f0", "#4c8a1f", 11),
        "photos": [("#b45309", "#f4f4f0", 12)],
        "body": """I'd been watching the listing for three weeks. Low miles, original paint, one owner who'd parked it when he moved overseas. By the time I called, I'd already decided.

## The drive up

We left at 5 a.m. with a jump pack, a tire inflator, and a toolbag I hoped I wouldn't open. The seller had kept every receipt in a binder, which told me more about the car than any photo could.

![Somewhere around mile 200, the first fuel stop on the way home]({photo:0})

## First impressions

The paint was better than the pictures. The tires were not. They were date-coded 2014 and hard as hockey pucks, so the plan for the drive home was simple: **stay under 65 and keep it smooth.**

> Buy the car that was loved, not the one with the best spec sheet.

## The list starts now

- New tires before anything fun
- Full fluid service, since nobody knows what's in there
- Figure out the squeak from the passenger side

More soon. She's home.""",
    },
    {
        "slug": "coilovers-alignment-lesson-in-patience",
        "title": "Coilovers, Alignment, and a Lesson in Patience",
        "excerpt": "Lowering the car took one weekend. Getting it to drive right took three more.",
        "tags": ["Suspension", "Project Car", "DIY"],
        "days_ago": 45,
        "cover": ("#4c8a1f", "#f4f4f0", 21),
        "photos": [("#4c8a1f", "#f4f4f0", 22), ("#f4f4f0", "#4c8a1f", 23), ("#3b5b7a", "#f4f4f0", 24)],
        "body": """The coilovers arrived on a Thursday. By Sunday night the car was sitting where I wanted it, and it drove terribly.

## What went wrong

I set the ride height by eye and drove to the alignment shop. Too much negative camber up front, toe all over the place, and one corner sitting 8 mm lower than the other three.

{gallery}

## What I'd do differently

1. Measure hub-to-fender at all four corners *before* touching anything
2. Count threads on each perch so left and right match
3. Let the springs settle for a week before the alignment

> Ride height is a feeling. Alignment is math. Do the math.

It drives the way I wanted now: flat, quiet, and still comfortable enough for the daily commute.""",
    },
    {
        "slug": "60k-service-everything-replaced",
        "title": "The 60k Service: Everything I Replaced",
        "excerpt": "Not glamorous, but it's the work that keeps the car on the road. Here's the full list and what it cost.",
        "tags": ["Maintenance", "DIY"],
        "days_ago": 9,
        "cover": ("#3b5b7a", "#f4f4f0", 31),
        "photos": [],
        "body": """With the suspension sorted, it was time for the boring-but-important stuff. I did most of it in the driveway over two Saturdays.

## The list

| Item | Done by | Cost |
| --- | --- | --- |
| Engine oil + filter | Me | $68 |
| Spark plugs | Me | $54 |
| Coolant flush | Me | $41 |
| Brake fluid | Shop | $95 |
| Transmission fluid | Shop | $180 |

## Lessons

- **Buy the torque wrench.** Guessing on spark plugs is how threads get stripped.
- Label every hose before you pull it. Phone photos count.
- Old coolant is toxic and sweet-smelling. Keep it away from pets and dispose of it properly.

Total for the service: about **$440**, roughly a third of what the dealer quoted.""",
    },
    {
        "slug": "six-hundred-miles-of-coast-road",
        "title": "Six Hundred Miles of Coast Road",
        "excerpt": "Three days, one coastline, and the first real test of everything we've changed on the car.",
        "tags": ["Road Trip", "Ownership"],
        "days_ago": 2,
        "featured": True,
        "cover": ("#b45309", "#f4f4f0", 41),
        "photos": [("#b45309", "#f4f4f0", 42), ("#f4f4f0", "#b45309", 43), ("#4c8a1f", "#f4f4f0", 44), ("#3b5b7a", "#f4f4f0", 45)],
        "body": """Every change on this car was made with a trip like this in mind. So we packed light, left early, and pointed it north.

## Day one

The first two hundred miles were freeway, which is where the new suspension surprised me most. It's firm, but it isn't punishing. By the time the road started to wind, I'd stopped thinking about the car and started enjoying it.

{gallery}

## Day two

Fog until noon, then the kind of light that makes everything look like a film still. We stopped every twenty minutes. I don't regret a single one.

> The best upgrade on this car isn't a part. It's the reason to drive it.

## What's next

Brakes are the weak link now. After three days of mountain descents, the pedal was getting long. Expect a brake post soon.""",
    },
]

POSTS = [
    {
        "slug": "night-meet-notes-clean-builds",
        "title": "Night Meet Notes: What a Clean Build Looks Like",
        "excerpt": "Three things the best cars at last month's meet had in common — and none of them cost much.",
        "meta": "What separates a clean build from a busy one, from a night spent walking a parking-lot car meet.",
        "tags": ["Culture", "Builds"],
        "products": ["low-and-slow-plate-frame", "drive-at-night-sticker", "night-shift-tee"],
        "days_ago": 12,
        "body": """<p>We spent last Saturday walking a parking lot full of cars until 2 a.m. The ones people kept coming back to weren't always the loudest or the most expensive. They were the cleanest.</p>
<h2>1. One idea, executed fully</h2>
<p>The best builds pick a direction and commit. A stock-looking sedan on the right wheels and ride height says more than a car with every part from every catalog.</p>
<h2>2. Details you only notice up close</h2>
<p>Matching hardware. A plate frame that doesn't fight the bumper line. Stickers placed with intent, not slapped on at a gas station.</p>
<blockquote>Clean isn't empty. Clean is when everything on the car is there for a reason.</blockquote>
<h2>3. It gets driven</h2>
<p>Rock chips, a little brake dust, a parking pass on the windshield. The cars we liked most were the ones that clearly get used.</p>
<p>See you at the next one.</p>""",
    },
    {
        "slug": "how-we-print-night-shift-tee",
        "title": "How We Print: Inside the Night Shift Tee",
        "excerpt": "From blank to finished tee — why we went heavy on cotton and printed by hand.",
        "meta": "A look at how the Night Shift Tee is made: 7 oz cotton, hand screen printing, and a boxy fit.",
        "tags": ["Apparel", "Process"],
        "products": ["night-shift-tee", "garage-hours-hoodie", "apex-6-panel-cap"],
        "days_ago": 4,
        "body": """<p>We tested eleven blanks before settling on the one we use now. Most were too thin, twisted after a wash, or fit like a dress shirt.</p>
<h2>Why 7 oz</h2>
<p>Heavier cotton holds its shape and drapes better. It also feels like a garment instead of a giveaway. The trade-off is cost, so we print fewer and price fairly.</p>
<h2>Printed by hand</h2>
<p>Every run is screen printed in small batches. Ink sits on top of the fabric instead of soaking in, so the back print stays sharp for years.</p>
<ul><li>Water-based ink on light colors, plastisol on dark</li><li>Each screen is registered by hand</li><li>Every shirt is checked before folding</li></ul>
<p>When a run sells out, it's usually gone. We'd rather make the next thing than reprint the last.</p>""",
    },
]


class Command(BaseCommand):
    help = "Load demo catalog, blog posts, reviews, and placeholder images."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing catalog and blog data first.")
        parser.add_argument(
            "--admin",
            action="store_true",
            help="Also create a local superuser admin / admin12345 (DEBUG only).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        brand = settings.BRAND["name"]
        if opts["reset"]:
            self.stdout.write("Clearing existing demo data…")
            Post.objects.all().delete()
            Tag.objects.all().delete()
            MediaAsset.objects.all().delete()
            FeaturedProduct.objects.all().delete()
            Review.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            ShippingMethod.objects.all().delete()

        categories = {}
        for i, (slug, name, blurb) in enumerate(CATEGORIES):
            categories[slug], _ = Category.objects.update_or_create(
                slug=slug, defaults={"name": name, "blurb": blurb, "position": i}
            )

        for i, (name, desc, price) in enumerate(SHIPPING):
            ShippingMethod.objects.update_or_create(
                name=name, defaults={"description": desc, "price": Decimal(price), "position": i}
            )

        products = {}
        for n, spec in enumerate(PRODUCTS, start=1):
            product, created = Product.objects.update_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"],
                    "category": categories[spec["category"]],
                    "price": Decimal(spec["price"]),
                    "compare_at_price": Decimal(spec["compare_at_price"]) if spec.get("compare_at_price") else None,
                    "tagline": spec["tagline"],
                    "description": spec["description"],
                    "details": spec["details"],
                    "is_active": True,
                },
            )
            products[spec["slug"]] = product
            for pos, variant in enumerate(spec["variants"]):
                name, stock = variant[0], variant[1]
                override = Decimal(variant[2]) if len(variant) > 2 else None
                v, v_created = Variant.objects.get_or_create(
                    product=product, name=name, defaults={"stock": stock, "position": pos, "price_override": override}
                )
                if not v_created and opts["reset"]:
                    v.stock = stock
                    v.save()
            if not product.images.exists():
                for pos, image_spec in enumerate(spec["images"]):
                    view, colors = image_spec[0], image_spec[1]
                    extra = image_spec[2] if len(image_spec) > 2 else None
                    data = art.product_image(spec["kind"], colors, brand, f"{n:03d}", view, extra)
                    img = ProductImage(product=product, position=pos, alt=f"{spec['name']} — {extra or view}")
                    img.image.save(f"{spec['slug']}-{pos + 1}-{ART_VERSION}.jpg", ContentFile(data), save=True)
            if spec.get("featured"):
                FeaturedProduct.objects.update_or_create(product=product, defaults={"position": spec["featured"]})
            self.stdout.write(f"  {'+' if created else '·'} {product.name}")

        for i, (name, loc, body, rating) in enumerate(REVIEWS):
            Review.objects.get_or_create(
                author_name=name, defaults={"location": loc, "body": body, "rating": rating, "position": i}
            )

        author, author_created = User.objects.get_or_create(
            username="lotcrew", defaults={"first_name": "Mika", "last_name": "Arai", "email": "crew@lot.example"}
        )
        if author_created:
            author.set_unusable_password()
            author.save()

        for spec in JOURNAL_POSTS:
            if Post.objects.filter(slug=spec["slug"]).exists():
                self.stdout.write(f"  · Post: {spec['title']}")
                continue
            photo_urls = []
            for glow, tail, seed in spec["photos"]:
                asset = MediaAsset(image=self._photo(glow, tail, seed, brand), uploaded_by=author)
                asset.save()
                photo_urls.append(asset.image.url)
            body = spec["body"].replace("{gallery}", "\n".join(f"![]({url})" for url in photo_urls))
            for n, url in enumerate(photo_urls):
                body = body.replace(f"{{photo:{n}}}", url)
            post = Post(
                slug=spec["slug"], title=spec["title"], excerpt=spec["excerpt"], body=body, author=author,
                status=Post.Status.PUBLISHED, is_featured=spec.get("featured", False),
                published_at=timezone.now() - timedelta(days=spec["days_ago"]),
                cover_image=self._photo(*spec["cover"], brand), cover_alt=spec["title"],
            )
            post.save()
            post.tags.set(
                [Tag.objects.get_or_create(slug=slugify(t), defaults={"name": t})[0] for t in spec["tags"]]
            )
            self.stdout.write(f"  + Post: {post.title}")

        for i, spec in enumerate(POSTS):
            post, created = Post.objects.update_or_create(
                slug=spec["slug"],
                defaults={
                    "title": spec["title"],
                    "excerpt": spec["excerpt"],
                    "meta_description": spec["meta"],
                    "body": spec["body"],
                    "author": author,
                    "status": Post.Status.PUBLISHED,
                    "published_at": timezone.now() - timedelta(days=spec["days_ago"]),
                },
            )
            post.tags.set(
                [Tag.objects.get_or_create(slug=t.lower(), defaults={"name": t})[0] for t in spec["tags"]]
            )
            post.related_products.set([products[s] for s in spec["products"]])
            if not post.cover_image:
                post.cover_image.save(
                    f"{spec['slug']}-{ART_VERSION}.jpg", ContentFile(art.cover_image(i, brand)), save=True
                )
            self.stdout.write(f"  {'+' if created else '·'} Post: {post.title}")

        if opts["admin"]:
            if not settings.DEBUG:
                self.stderr.write("Refusing to create demo admin with DEBUG off.")
            elif not User.objects.filter(username="admin").exists():
                User.objects.create_superuser("admin", "admin@lot.example", "admin12345")
                self.stdout.write(self.style.WARNING("  Created superuser admin / admin12345 (local only!)"))

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {len(PRODUCTS)} products and {len(POSTS) + len(JOURNAL_POSTS)} posts.")
        )

    @staticmethod
    def _photo(glow, tail, seed, brand):
        img = art.road_scene(1600, 1000, glow=glow, tail=tail, brand=brand, seed=seed)
        return ContentFile(art.to_jpeg(img, quality=84), name=f"journal-{seed}.jpg")
