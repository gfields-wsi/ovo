<?php
// OvO Enrichment uninstall, version 1.0.
// Uninstall restores the kept originals first, so the catalog goes
// back to how it was before OvO wrote anything. Only then are OvO
// meta, webhooks, and options deleted. The audit log is deleted
// with the options; export it from WooCommerce > OvO Enrichment
// before uninstalling if the record is needed.
// Enrichment is never left half-applied by uninstall: every
// enriched product is reverted in full.
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
    exit;
}

global $wpdb;

// Every product OvO touched.
$ids = get_posts(
    array(
        'post_type'      => 'product',
        'post_status'    => array( 'publish', 'draft', 'private' ),
        'posts_per_page' => -1,
        'fields'         => 'ids',
        'meta_key'       => '_ovo_enriched',
    )
);
foreach ( $ids as $product_id ) {
    $product_id = (int) $product_id;
    $enriched   = get_post_meta( $product_id, '_ovo_enriched', true );
    $originals  = get_post_meta( $product_id, '_ovo_originals', true );
    if ( ! is_array( $enriched ) ) {
        $enriched = array();
    }
    if ( ! is_array( $originals ) ) {
        $originals = array();
    }
    foreach ( $enriched as $key => $entry ) {
        $field    = isset( $entry['field'] ) ? $entry['field'] : '';
        $original = array_key_exists( $key, $originals ) ? $originals[ $key ] : null;
        if ( 'image_alt_text' === $field ) {
            $product = function_exists( 'wc_get_product' ) ? wc_get_product( $product_id ) : null;
            if ( $product && $product->get_image_id() ) {
                update_post_meta( $product->get_image_id(), '_wp_attachment_image_alt', is_string( $original ) ? $original : '' );
            }
        } elseif ( 'short_description' === $field ) {
            wp_update_post( array( 'ID' => $product_id, 'post_excerpt' => is_string( $original ) ? $original : '' ) );
        } elseif ( 'description' === $field ) {
            wp_update_post( array( 'ID' => $product_id, 'post_content' => is_string( $original ) ? $original : '' ) );
        } elseif ( 'attribute' === $field ) {
            update_post_meta( $product_id, '_product_attributes', is_array( $original ) ? $original : array() );
        } elseif ( 'product_cat' === $field || 'product_tag' === $field ) {
            $taxonomy = ( 'product_cat' === $field ) ? 'product_cat' : 'product_tag';
            wp_set_post_terms( $product_id, is_array( $original ) ? $original : array(), $taxonomy, false );
        }
        // additional_property needs no native restore: deleting the
        // enriched entry removes it from JSON-LD and REST at once.
    }
    if ( function_exists( 'wc_delete_product_transients' ) ) {
        wc_delete_product_transients( $product_id );
    }
    delete_post_meta( $product_id, '_ovo_enriched' );
    delete_post_meta( $product_id, '_ovo_originals' );
}

// Delete the OvO webhooks. WooCommerce stores webhooks in its own
// table on current releases, so delete through the webhook object,
// not by deleting a post.
$webhook_ids = get_option( 'ovo_enrichment_webhook_ids', array() );
if ( is_array( $webhook_ids ) && function_exists( 'wc_get_webhook' ) ) {
    foreach ( $webhook_ids as $webhook_id ) {
        $hook = wc_get_webhook( (int) $webhook_id );
        if ( $hook ) {
            $hook->delete( true );
        }
    }
}

$wpdb->query( "DELETE FROM {$wpdb->postmeta} WHERE meta_key IN ('_ovo_enriched', '_ovo_originals')" );
delete_option( 'ovo_enrichment_audit_log' );
delete_option( 'ovo_enrichment_demo_mode' );
delete_option( 'ovo_enrichment_token_hash' );
delete_option( 'ovo_enrichment_webhook_ids' );
delete_option( 'ovo_enrichment_webhook_url' );
wp_clear_scheduled_hook( 'ovo_enrichment_webhook_check' );
