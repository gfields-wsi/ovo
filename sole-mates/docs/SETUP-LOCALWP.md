# Setup in LocalWP

Assumes you already use LocalWP and have a fresh site, or are happy to make one.

## 1. Create the site

- LocalWP > Create a new site, name `Sole Mates`, domain e.g. `solemates.local`
- PHP 8.1 or newer, WordPress latest, MySQL 8
- Note the WP admin username / password — Muse (the agent in this chat) does not have them, and does not need them for the repo-first workflow.

## 2. Install WooCommerce

- Plugins > Add New > WooCommerce > Install + Activate
- Run the setup wizard: store address (use a placeholder), currency **CAD**, product types: Physical products
- Payments: enable test mode. For the first test, Cash on Delivery is the simplest $1 checkout with no gateway. Then switch to WooCommerce Payments / Stripe in test mode for a realistic card checkout, using test card 4242 4242 4242 4242, any future date, any CVC.
- WooCommerce will create Shop, Cart, Checkout and My Account pages automatically.

## 3. Install the Sole Mates theme

- Appearance > Themes > Add New > search **Storefront** > Install + Activate (parent theme, required)
- Copy `wp-content/themes/sole-mates/` from this repo into your LocalWP site's `wp-content/themes/`
  - In LocalWP, right-click the site > "Open Site Shell" or "Reveal in Finder" to find `app/public/wp-content/themes/`
- Appearance > Themes > Activate **Sole Mates**

## 4. Create the products — pick ONE method

### Method A — demo-data plugin (recommended)

- Copy `wp-content/plugins/sole-mates-demo-data/` into `wp-content/plugins/`
- If you copied the plugin on its own (without the rest of the repo), also copy `data/` to `wp-content/sole-mates-data/` so the plugin can find `products.json`
- Plugins > Activate **Sole Mates Demo Data**
- Check Products > All Products: you should see 12 variable products, each $1

### Method B — CSV import

- Products > Import > Choose File > `data/products.csv` > Run the importer
- Check that variations imported: open a product, e.g. Velocity Road Runners, and confirm sizes including 9.5 are listed at $1, stock 10 each

Do not run both methods — the plugin skips SKUs that already exist, but the CSV will duplicate them.

## 5. Homepage

- The theme's `front-page.php` shows the catalog on the homepage.
- Settings > Reading > "Your homepage displays: A static page" > Homepage: create/select a blank "Home" page. Or, for the simplest demo, leave the Shop page as the landing page — the catalog is the homepage either way in the demo narrative.

## 6. Test checkout

1. Go to a product, pick a size, Add to Cart, View Cart, Proceed to Checkout
2. Use test / placeholder customer details, test payment method
3. Confirm order total is $1, order appears in WooCommerce > Orders
4. Repeat for the hero product in `docs/DEMO-SCRIPT.md`

## Troubleshooting

- Products missing after plugin activation: check the plugin could find `data/products.json` (see Method A note above), and that WooCommerce was active before the plugin.
- Theme looks unstyled: Storefront (parent) must be installed, not just the child theme.
- Checkout shows a real payment request: you are not in test mode — switch the gateway to test mode / COD before any demo purchase.
