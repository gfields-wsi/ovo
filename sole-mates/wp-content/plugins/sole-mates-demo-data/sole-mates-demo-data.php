<?php
/**
 * Plugin Name: Sole Mates Demo Data
 * Description: Creates the 12-product Sole Mates catalog (variable products, $1 each) from data/products.json on activation, attaches one generated product image per shoe as the featured image, and adds 3 demo reviews per product. Deactivate / delete to remove the demo data hook — products themselves are normal WooCommerce products and can be deleted in Products > All Products.
 * Version: 0.1.3
 * Author: WSI Hackathon Team
 */

if ( ! defined( 'ABSPATH' ) ) exit;

register_activation_hook( __FILE__, 'sole_mates_create_demo_products' );

function sole_mates_find_products_json() {
    $candidates = array(
        WP_CONTENT_DIR . '/sole-mates-data/products.json',
        WP_CONTENT_DIR . '/data/products.json',
        dirname( __FILE__ ) . '/data/products.json',
        dirname( __FILE__, 3 ) . '/data/products.json',
    );
    foreach ( $candidates as $candidate ) {
        if ( file_exists( $candidate ) ) return $candidate;
    }
    error_log( 'Sole Mates Demo Data: products.json not found. Tried: ' . implode( ', ', $candidates ) );
    return '';
}

function sole_mates_find_image_file( $sku ) {
    $filename = strtolower( $sku ) . '.webp';
    $candidates = array(
        dirname( __FILE__ ) . '/images/' . $filename,
        WP_CONTENT_DIR . '/sole-mates-data/images/' . $filename,
        WP_CONTENT_DIR . '/sole-mates-data/' . $filename,
        WP_CONTENT_DIR . '/uploads/sole-mates/' . $filename,
    );
    foreach ( $candidates as $candidate ) {
        if ( file_exists( $candidate ) ) return $candidate;
    }
    return '';
}

function sole_mates_attach_image( $product_id, $sku ) {
    if ( has_post_thumbnail( $product_id ) ) return;
    $file = sole_mates_find_image_file( $sku );
    if ( ! $file ) {
        error_log( 'Sole Mates Demo Data: image not found for ' . $sku );
        return;
    }
    $contents = file_get_contents( $file );
    if ( false === $contents ) return;
    $filename = strtolower( $sku ) . '.webp';
    $upload = wp_upload_bits( $filename, null, $contents );
    if ( ! empty( $upload['error'] ) ) {
        error_log( 'Sole Mates Demo Data: upload failed for ' . $sku . ': ' . $upload['error'] );
        return;
    }
    $filetype = wp_check_filetype( $upload['file'] );
    $attachment = array(
        'post_mime_type' => $filetype['type'] ? $filetype['type'] : 'image/webp',
        'post_title'     => sanitize_file_name( $filename ),
        'post_content'   => '',
        'post_status'    => 'inherit',
    );
    $attach_id = wp_insert_attachment( $attachment, $upload['file'], $product_id );
    if ( is_wp_error( $attach_id ) || ! $attach_id ) return;
    require_once ABSPATH . 'wp-admin/includes/image.php';
    $attach_data = wp_generate_attachment_metadata( $attach_id, $upload['file'] );
    wp_update_attachment_metadata( $attach_id, $attach_data );
    set_post_thumbnail( $product_id, $attach_id );
}

function sole_mates_add_reviews( $product_id, $item ) {
    if ( empty( $item['reviews'] ) || ! is_array( $item['reviews'] ) ) return;
    // Don't duplicate reviews on reactivation.
    $existing = get_comments( array(
        'post_id' => $product_id,
        'type'    => 'review',
        'count'   => true,
    ) );
    if ( $existing ) return;

    $total = 0;
    $count = 0;
    foreach ( $item['reviews'] as $review ) {
        $author = sanitize_text_field( $review['author'] );
        $email  = sanitize_email( strtolower( str_replace( ' ', '.', $author ) ) . '@example.com' );
        $date   = ! empty( $review['date'] ) ? $review['date'] . ' 12:00:00' : current_time( 'mysql' );
        $comment_id = wp_insert_comment( array(
            'comment_post_ID'      => $product_id,
            'comment_author'       => $author,
            'comment_author_email' => $email,
            'comment_content'      => wp_kses_post( $review['text'] ),
            'comment_type'         => 'review',
            'comment_approved'     => 1,
            'comment_date'         => $date,
            'comment_date_gmt'     => get_gmt_from_date( $date ),
        ) );
        if ( ! $comment_id ) continue;
        $rating = (int) $review['rating'];
        add_comment_meta( $comment_id, 'rating', $rating, true );
        $total += $rating;
        $count++;
    }
    if ( $count ) {
        $product = wc_get_product( $product_id );
        if ( $product ) {
            $product->set_average_rating( round( $total / $count, 2 ) );
            $product->set_review_count( $count );
            $product->save();
        }
    }
}

function sole_mates_create_demo_products() {
    if ( ! class_exists( 'WooCommerce' ) ) return;

    $json_path = sole_mates_find_products_json();
    if ( ! $json_path ) return;

    $data = json_decode( file_get_contents( $json_path ), true );
    if ( empty( $data['products'] ) ) return;

    foreach ( $data['products'] as $item ) {
        $existing_id = wc_get_product_id_by_sku( $item['sku'] );
        if ( $existing_id ) {
            // Product already exists (e.g. from a CSV import, or an earlier
            // activation before images / reviews were added): attach its
            // image and add its reviews if it has none yet.
            sole_mates_attach_image( $existing_id, $item['sku'] );
            sole_mates_add_reviews( $existing_id, $item );
            continue;
        }

        $term = get_term_by( 'name', $item['type'], 'product_cat' );
        $cat_id = $term ? (int) $term->term_id : 0;
        if ( ! $cat_id ) {
            $new = wp_insert_term( $item['type'], 'product_cat' );
            $cat_id = is_wp_error( $new ) ? 0 : (int) $new['term_id'];
        }

        $size_attr = new WC_Product_Attribute();
        $size_attr->set_name( 'Size' );
        $size_attr->set_options( $item['sizes'] );
        $size_attr->set_visible( true );
        $size_attr->set_variation( true );

        $colour_attr = new WC_Product_Attribute();
        $colour_attr->set_name( 'Colour' );
        $colour_attr->set_options( array( $item['colour'] ) );
        $colour_attr->set_visible( true );
        $colour_attr->set_variation( false );

        $product = new WC_Product_Variable();
        $product->set_name( $item['name'] );
        $product->set_sku( $item['sku'] );
        $product->set_description( $item['desc'] . ' Material: ' . $item['material'] . ' Fit: ' . $item['fit'] . ' Returns: ' . $item['returns'] );
        $product->set_short_description( $item['short'] );
        $product->set_regular_price( '1' );
        $product->set_status( 'publish' );
        $product->set_catalog_visibility( 'visible' );
        if ( $cat_id ) $product->set_category_ids( array( $cat_id ) );
        $product->set_attributes( array( $size_attr, $colour_attr ) );
        $product->save();

        sole_mates_attach_image( $product->get_id(), $item['sku'] );
        sole_mates_add_reviews( $product->get_id(), $item );

        foreach ( $item['sizes'] as $size ) {
            $variation = new WC_Product_Variation();
            $variation->set_parent_id( $product->get_id() );
            $variation->set_attributes( array( 'size' => $size ) );
            $variation->set_regular_price( '1' );
            $variation->set_status( 'publish' );
            $variation->set_manage_stock( true );
            $variation->set_stock_quantity( 10 );
            $variation->set_stock_status( 'instock' );
            $variation->save();
        }
    }
}
