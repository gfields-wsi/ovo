<?php
/**
 * Sole Mates — Storefront child theme.
 * Visual polish only: Inter type, monochrome palette.
 * No sidebar on product or shop pages, header has no search, no promo banner.
 * Logo in the nav + favicon come from the theme's assets/ folder.
 */

add_action( 'wp_enqueue_scripts', function () {
    wp_enqueue_style( 'sole-mates-inter', 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap', array(), null );
    wp_enqueue_style( 'sole-mates-parent', get_template_directory_uri() . '/style.css' );
    wp_enqueue_style( 'sole-mates', get_stylesheet_uri(), array( 'sole-mates-parent', 'sole-mates-inter' ), '0.3.1' );
} );

add_action( 'after_setup_theme', function () {
    add_theme_support( 'woocommerce' );
    add_theme_support( 'wc-product-gallery-zoom' );
    add_theme_support( 'wc-product-gallery-lightbox' );
    add_theme_support( 'wc-product-gallery-slider' );
} );

// Remove the header product search — 12 products, no search needed.
add_action( 'init', function () {
    remove_action( 'storefront_header', 'storefront_product_search', 40 );
} );

// Remove the sidebar on single product pages (PDP), the shop page,
// and product category / tag archives. Storefront uses its own
// storefront_sidebar hook; WooCommerce's woocommerce_sidebar is
// removed as a fallback. These conditionals only work after the
// query has run, so this runs on get_header.
add_action( 'get_header', function () {
    $is_store_page = false;
    if ( function_exists( 'is_product' ) && is_product() ) $is_store_page = true;
    if ( function_exists( 'is_shop' ) && is_shop() ) $is_store_page = true;
    if ( function_exists( 'is_product_category' ) && is_product_category() ) $is_store_page = true;
    if ( function_exists( 'is_product_taxonomy' ) && is_product_taxonomy() ) $is_store_page = true;
    if ( $is_store_page ) {
        remove_action( 'storefront_sidebar', 'storefront_get_sidebar', 10 );
        remove_action( 'woocommerce_sidebar', 'woocommerce_get_sidebar', 10 );
    }
} );

// Logo in the main nav: replace Storefront's text branding with the
// Sole Mates logo image when it is present in the theme, otherwise
// fall back to the plain site title.
add_action( 'init', function () {
    remove_action( 'storefront_header', 'storefront_site_branding', 20 );
    add_action( 'storefront_header', 'sole_mates_site_branding', 20 );
} );

function sole_mates_site_branding() {
    $logo_path = get_stylesheet_directory() . '/assets/sole-mates-logo.png';
    $logo_url  = get_stylesheet_directory_uri() . '/assets/sole-mates-logo.png';
    echo '<div class="site-branding"><a class="sm-logo-link" href="' . esc_url( home_url( '/' ) ) . '" rel="home">';
    if ( file_exists( $logo_path ) ) {
        echo '<img class="sm-logo" src="' . esc_url( $logo_url ) . '" alt="Sole Mates" height="36">';
    } else {
        echo esc_html( get_bloginfo( 'name' ) );
    }
    echo '</a></div>';
}

// Favicon: use the square sole-mark icon from the theme's assets/.
// Filtered through get_site_icon_url so WordPress uses it as the
// site icon, plus an explicit <link> in wp_head as a fallback.
add_filter( 'get_site_icon_url', function ( $url, $size, $blog_id ) {
    $icon_path = get_stylesheet_directory() . '/assets/sole-mates-icon.png';
    if ( file_exists( $icon_path ) ) {
        return get_stylesheet_directory_uri() . '/assets/sole-mates-icon.png';
    }
    return $url;
}, 10, 3 );

add_action( 'wp_head', function () {
    $icon_path = get_stylesheet_directory() . '/assets/sole-mates-icon.png';
    if ( file_exists( $icon_path ) ) {
        $icon_url = get_stylesheet_directory_uri() . '/assets/sole-mates-icon.png';
        echo '<link rel="icon" type="image/png" href="' . esc_url( $icon_url ) . '">' . "\n";
        echo '<link rel="apple-touch-icon" href="' . esc_url( $icon_url ) . '">' . "\n";
    }
} );

// Shop page: show 12 products, 4 per row — matches the 12-product demo catalog.
add_filter( 'loop_shop_per_page', function () { return 12; } );
add_filter( 'loop_shop_columns', function () { return 4; } );
