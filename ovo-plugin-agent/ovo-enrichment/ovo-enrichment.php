<?php
/**
 * Plugin Name:       OvO Enrichment
 * Plugin URI:        https://wsiventures.com/solemates
 * Description:       Publishes merchant-approved enrichment in place on the merchant's own WooCommerce store. Server-rendered JSON-LD and a REST read surface only. It never writes price, stock, SKU, tax, shipping, or policy claims from modelled data, and it never changes checkout totals. WooCommerce recalculates those server-side.
 * Version:           0.2.0-demo
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            OvO Hackathon, Stream 3
 * License:           GPLv2 or later
 * Text Domain:       ovo-enrichment
 *
 * Demo status: this is a demo build for the Meta AI Hackathon freeze on
 * 2026-11-02. It is not a production plugin, it is not listed in the
 * WordPress plugin directory, and it makes no claim of MCP, ACP, or UCP
 * compliance, consumer Muse discovery, live payment, or production
 * compatibility. Zip upload in WP admin is a demo-only install method.
 * The real merchant path is a CMS app-store install, which does not exist yet.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'OVO_ENRICHMENT_VERSION', '0.2.0-demo' );

/**
 * Write auth, version 0.2.
 * Admin login still works. In addition, a scoped OvO token works:
 * the admin generates a token once in WooCommerce > OvO Enrichment,
 * the plugin stores only its SHA-256 hash, and the caller sends it
 * as X-Ovo-Token. A token call must also carry approved_by and
 * approval_fingerprint, so a token alone never opens publish.
 * The token can be revoked by generating a new one, which replaces
 * the old hash. The token itself is never stored in plain text.
 */
function ovo_enrichment_can_write( $request ) {
    if ( current_user_can( 'manage_options' ) ) {
        return array( 'ok' => true, 'via' => 'admin' );
    }
    $hash = get_option( 'ovo_enrichment_token_hash', '' );
    if ( '' === $hash ) {
        return array( 'ok' => false, 'via' => '' );
    }
    $token = '';
    if ( is_object( $request ) && method_exists( $request, 'get_header' ) ) {
        $token = (string) $request->get_header( 'X-Ovo-Token' );
    }
    if ( '' === $token ) {
        return array( 'ok' => false, 'via' => '' );
    }
    if ( hash_equals( $hash, hash( 'sha256', $token ) ) ) {
        return array( 'ok' => true, 'via' => 'token' );
    }
    return array( 'ok' => false, 'via' => '' );
}

/**
 * Field policy.
 *
 * Safe and medium fields only. Everything else is rejected, fail closed.
 * A field that is not in this map is rejected, even if it looks harmless.
 *
 * Write target:
 *  - "wc"     : written to a WooCommerce / WordPress native field.
 *  - "jsonld" : stored in OVO-namespaced meta and published only in the
 *                OVO JSON-LD block and the OVO REST read surface. It never
 *                overwrites a native store field.
 *
 * Modelled source rule: modelled wording may only reach "jsonld" fields.
 * A modelled value for a "wc" field is rejected. Stream 2 must resubmit
 * that wording as additional_property if it wants it published at all.
 * This keeps store-facing text sourced from merchant text, not from a model.
 */
function ovo_enrichment_field_map() {
    return array(
        // Safe. Image alt text only. Never a price, stock, or policy claim.
        'image_alt_text' => array(
            'target' => 'wc',
            'tier'   => 'safe',
        ),
        // Medium. Store-facing text, reversible, original kept.
        'short_description' => array(
            'target' => 'wc',
            'tier'   => 'medium',
        ),
        'description' => array(
            'target' => 'wc',
            'tier'   => 'medium',
        ),
        // Medium. Non-variation custom attributes only. See apply step:
        // any attribute name that already exists as a variation attribute
        // (for Sole Mates, Size) is rejected, so variations are never broken.
        // Value format: "Attribute name|term". Example: "Best for|Everyday wear".
        'attribute' => array(
            'target' => 'wc',
            'tier'   => 'medium',
        ),
        // Medium. Terms are appended, never used to replace the full set.
        'product_cat' => array(
            'target' => 'wc',
            'tier'   => 'medium',
        ),
        'product_tag' => array(
            'target' => 'wc',
            'tier'   => 'medium',
        ),
        // Medium. JSON-LD only. The vehicle for enrichment that restates
        // store text, including size-label notes and fit notes. It never
        // becomes a native price, stock, or variation value.
        // Value format: "Property name|value". Example: "Fit note|True to size".
        'additional_property' => array(
            'target' => 'jsonld',
            'tier'   => 'medium',
        ),
    );
}

function ovo_enrichment_blocked_fields() {
    return array(
        'price', 'regular_price', 'sale_price',
        'date_on_sale_from', 'date_on_sale_to',
        'stock_quantity', 'stock_status', 'manage_stock', 'backorders',
        'low_stock_amount', 'sold_individually',
        'sku', 'gtin', 'global_unique_id',
        'tax_class', 'tax_status',
        'shipping_class', 'weight', 'length', 'width', 'height',
        'purchase_note', 'returns_policy', 'shipping_policy',
        'material', 'safety', 'compatibility',
        'virtual', 'downloadable', 'featured', 'catalog_visibility',
    );
}

function ovo_enrichment_allowed_sources() {
    return array( 'merchant-provided', 'observed', 'modelled' );
}

/**
 * Validate one Stream 2 change before anything is written.
 * Returns array( 'ok' => bool, 'error' => string ).
 */
function ovo_enrichment_validate_change( $change ) {
    if ( ! is_array( $change ) ) {
        return array( 'ok' => false, 'error' => 'Change must be an object.' );
    }
    $field = isset( $change['field'] ) ? sanitize_text_field( $change['field'] ) : '';
    $map   = ovo_enrichment_field_map();
    if ( '' === $field || ! isset( $map[ $field ] ) ) {
        return array( 'ok' => false, 'error' => 'Field is blocked or unknown: ' . $field );
    }
    if ( in_array( $field, ovo_enrichment_blocked_fields(), true ) ) {
        return array( 'ok' => false, 'error' => 'Field is blocked: ' . $field );
    }
    $source = isset( $change['source'] ) ? sanitize_text_field( $change['source'] ) : '';
    if ( ! in_array( $source, ovo_enrichment_allowed_sources(), true ) ) {
        return array( 'ok' => false, 'error' => 'Source label is missing or unknown.' );
    }
    if ( 'modelled' === $source && 'jsonld' !== $map[ $field ]['target'] ) {
        return array( 'ok' => false, 'error' => 'Modelled values may only publish as additional_property, never as a native store field.' );
    }
    if ( ! isset( $change['product_id'] ) || (int) $change['product_id'] <= 0 ) {
        return array( 'ok' => false, 'error' => 'product_id is missing or invalid.' );
    }
    if ( ! isset( $change['new_value'] ) || '' === trim( (string) $change['new_value'] ) ) {
        return array( 'ok' => false, 'error' => 'new_value is missing or empty.' );
    }
    if ( ! isset( $change['old_value'] ) ) {
        return array( 'ok' => false, 'error' => 'old_value is missing. A diff without an old value cannot be checked against the live store.' );
    }
    // Tier enforcement, version 0.2: a numeric confidence below 50
    // percent is rejected, per the PRD reject-and-iterate tier.
    // Confidence is otherwise stored as given and is not interpreted
    // as a percent, because version 0.1 diffs used labels like medium.
    if ( isset( $change['confidence_percent'] ) ) {
        if ( ! is_numeric( $change['confidence_percent'] ) ) {
            return array( 'ok' => false, 'error' => 'confidence_percent must be numeric.' );
        }
        if ( (float) $change['confidence_percent'] < 50 ) {
            return array( 'ok' => false, 'error' => 'Confidence below 50 percent is rejected and must be iterated, per the PRD tier rule.' );
        }
    }
    if ( isset( $change['confidence'] ) && 'below_50' === sanitize_text_field( $change['confidence'] ) ) {
        return array( 'ok' => false, 'error' => 'Confidence below 50 percent is rejected and must be iterated, per the PRD tier rule.' );
    }
    return array( 'ok' => true, 'error' => '' );
}

/**
 * Read the current live value for a field, for the old-value check.
 * Returns null when the field cannot be read, so the caller rejects
 * rather than guessing.
 */
function ovo_enrichment_current_value( $product_id, $field ) {
    $product = function_exists( 'wc_get_product' ) ? wc_get_product( $product_id ) : null;
    if ( ! $product ) {
        return null;
    }
    if ( 'image_alt_text' === $field ) {
        $image_id = $product->get_image_id();
        if ( ! $image_id ) {
            return '';
        }
        $alt = get_post_meta( $image_id, '_wp_attachment_image_alt', true );
        return is_string( $alt ) ? $alt : '';
    }
    if ( 'short_description' === $field ) {
        return (string) $product->get_short_description();
    }
    if ( 'description' === $field ) {
        return (string) $product->get_description();
    }
    if ( 'additional_property' === $field ) {
        // JSON-LD only: the live value is "not present" unless this exact
        // property was already published by OvO. Old value "" means new.
        $enriched = get_post_meta( $product_id, '_ovo_enriched', true );
        if ( is_array( $enriched ) && isset( $enriched['additional_property'] ) ) {
            return (string) $enriched['additional_property']['new_value'];
        }
        return '';
    }
    // Terms and attributes are append-only in v0.1. The old-value check
    // for them is "term not already present", handled in the apply step.
    // Returning an empty string here would be a false live value, so
    // return a sentinel the apply step understands instead of guessing.
    if ( in_array( $field, array( 'attribute', 'product_cat', 'product_tag' ), true ) ) {
        return '__ovo_append_only__';
    }
    return null;
}

function ovo_enrichment_originals( $product_id ) {
    $originals = get_post_meta( $product_id, '_ovo_originals', true );
    return is_array( $originals ) ? $originals : array();
}

function ovo_enrichment_enriched( $product_id ) {
    $enriched = get_post_meta( $product_id, '_ovo_enriched', true );
    return is_array( $enriched ) ? $enriched : array();
}

/**
 * Keep the original, first-write wins. A later diff must never overwrite
 * the original with an already-enriched value, or revert would be lost.
 */
function ovo_enrichment_keep_original( $product_id, $key, $original ) {
    $originals = ovo_enrichment_originals( $product_id );
    if ( ! array_key_exists( $key, $originals ) ) {
        $originals[ $key ] = $original;
        update_post_meta( $product_id, '_ovo_originals', $originals );
    }
}

function ovo_enrichment_audit( $entry ) {
    $log = get_option( 'ovo_enrichment_audit_log', array() );
    if ( ! is_array( $log ) ) {
        $log = array();
    }
    $entry['at'] = gmdate( 'c' );
    $log[]       = $entry;
    // Cap the log. Revert and demo-reset append, they never truncate it.
    if ( count( $log ) > 500 ) {
        $log = array_slice( $log, -500 );
    }
    update_option( 'ovo_enrichment_audit_log', $log, false );
}

/**
 * Apply one validated change. Returns array( 'ok', 'error', 'applied' ).
 * Old-value check: for readable fields, a mismatch rejects the change.
 * This stops a stale diff from overwriting a merchant edit made since
 * the diff was produced.
 */
function ovo_enrichment_apply_change( $change, $batch_id ) {
    $product_id = (int) $change['product_id'];
    $field      = sanitize_text_field( $change['field'] );
    $new_value  = wp_kses_post( (string) $change['new_value'] );
    $old_value  = (string) $change['old_value'];
    $source     = sanitize_text_field( $change['source'] );
    $confidence = isset( $change['confidence'] ) ? sanitize_text_field( $change['confidence'] ) : '';

    $product = function_exists( 'wc_get_product' ) ? wc_get_product( $product_id ) : null;
    if ( ! $product || 'publish' !== $product->get_status() ) {
        return array( 'ok' => false, 'error' => 'Product not found or not published: ' . $product_id );
    }

    $current = ovo_enrichment_current_value( $product_id, $field );
    if ( null === $current ) {
        return array( 'ok' => false, 'error' => 'Cannot read the live value for field: ' . $field );
    }
    if ( '__ovo_append_only__' !== $current && $current !== $old_value ) {
        return array( 'ok' => false, 'error' => 'Old value does not match the live store. Diff is stale for product ' . $product_id . ', field ' . $field . '. Nothing was written for this change.' );
    }

    $key = $field;
    if ( 'additional_property' === $field || 'attribute' === $field ) {
        // Key by property/attribute name so one product can hold several.
        $parts = explode( '|', $new_value, 2 );
        if ( count( $parts ) < 2 || '' === trim( $parts[0] ) || '' === trim( $parts[1] ) ) {
            return array( 'ok' => false, 'error' => 'Field ' . $field . ' needs "Name|value" format.' );
        }
        $key = $field . ':' . sanitize_text_field( $parts[0] );
    }

    // Variation guard: never write an attribute that is already a
    // variation attribute. Changing Size terms would break variations.
    if ( 'attribute' === $field ) {
        $attrs = $product->get_attributes();
        $parts = explode( '|', $new_value, 2 );
        $name  = sanitize_text_field( $parts[0] );
        foreach ( $attrs as $attr ) {
            if ( method_exists( $attr, 'get_variation' ) && $attr->get_variation() && strtolower( $attr->get_name() ) === strtolower( $name ) ) {
                return array( 'ok' => false, 'error' => 'Attribute is a variation attribute and cannot be written by OvO: ' . $name );
            }
        }
        $raw_attrs = get_post_meta( $product_id, '_product_attributes', true );
        ovo_enrichment_keep_original( $product_id, $key, is_array( $raw_attrs ) ? $raw_attrs : array() );
        $raw_attrs = is_array( $raw_attrs ) ? $raw_attrs : array();
        $slug      = sanitize_title( $name );
        $raw_attrs[ $slug ] = array(
            'name'         => $name,
            'value'        => sanitize_text_field( $parts[1] ),
            'position'     => count( $raw_attrs ),
            'is_visible'   => 1,
            'is_variation' => 0,
            'is_taxonomy'  => 0,
        );
        update_post_meta( $product_id, '_product_attributes', $raw_attrs );
    } elseif ( 'product_cat' === $field || 'product_tag' === $field ) {
        $taxonomy = ( 'product_cat' === $field ) ? 'product_cat' : 'product_tag';
        $terms    = wp_get_post_terms( $product_id, $taxonomy, array( 'fields' => 'ids' ) );
        ovo_enrichment_keep_original( $product_id, $key, is_array( $terms ) ? $terms : array() );
        $term = get_term_by( 'name', $new_value, $taxonomy );
        if ( ! $term ) {
            $created = wp_insert_term( $new_value, $taxonomy );
            if ( is_wp_error( $created ) ) {
                return array( 'ok' => false, 'error' => 'Could not create term: ' . $new_value );
            }
            $term = get_term( $created['term_id'] );
        }
        if ( $term && ! in_array( (int) $term->term_id, array_map( 'intval', (array) $terms ), true ) ) {
            wp_set_post_terms( $product_id, array_merge( (array) $terms, array( (int) $term->term_id ) ), $taxonomy, false );
        }
    } elseif ( 'image_alt_text' === $field ) {
        $image_id = $product->get_image_id();
        if ( ! $image_id ) {
            return array( 'ok' => false, 'error' => 'Product has no image, so alt text cannot be written.' );
        }
        ovo_enrichment_keep_original( $product_id, $key, $current );
        update_post_meta( $image_id, '_wp_attachment_image_alt', sanitize_text_field( $new_value ) );
    } elseif ( 'short_description' === $field ) {
        ovo_enrichment_keep_original( $product_id, $key, $current );
        wp_update_post(
            array(
                'ID'           => $product_id,
                'post_excerpt' => $new_value,
            )
        );
    } elseif ( 'description' === $field ) {
        ovo_enrichment_keep_original( $product_id, $key, $current );
        wp_update_post(
            array(
                'ID'           => $product_id,
                'post_content' => $new_value,
            )
        );
    } elseif ( 'additional_property' === $field ) {
        ovo_enrichment_keep_original( $product_id, $key, '' );
        // No native field is touched. The value lives in _ovo_enriched only.
    }

    $enriched = ovo_enrichment_enriched( $product_id );
    $enriched[ $key ] = array(
        'field'      => $field,
        'new_value'  => $new_value,
        'source'     => $source,
        'confidence' => $confidence,
        'batch_id'   => $batch_id,
        'applied_at' => gmdate( 'c' ),
    );
    update_post_meta( $product_id, '_ovo_enriched', $enriched );
    if ( function_exists( 'wc_delete_product_transients' ) ) {
        wc_delete_product_transients( $product_id );
    }
    ovo_enrichment_audit(
        array(
            'action'     => 'apply',
            'product_id' => $product_id,
            'field'      => $field,
            'key'        => $key,
            'source'     => $source,
            'batch_id'   => $batch_id,
        )
    );
    return array( 'ok' => true, 'error' => '', 'applied' => $key );
}

/**
 * Revert one field, or all OvO fields for a product, to the kept original.
 * The audit log is kept. Revert itself is logged.
 */
function ovo_enrichment_revert_product( $product_id, $field_key = '' ) {
    $originals = ovo_enrichment_originals( $product_id );
    $enriched  = ovo_enrichment_enriched( $product_id );
    if ( empty( $enriched ) ) {
        return array( 'ok' => true, 'reverted' => array() );
    }
    $reverted = array();
    foreach ( $enriched as $key => $entry ) {
        if ( '' !== $field_key && $key !== $field_key ) {
            continue;
        }
        $field    = $entry['field'];
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
        unset( $enriched[ $key ] );
        $reverted[] = $key;
    }
    update_post_meta( $product_id, '_ovo_enriched', $enriched );
    if ( empty( $enriched ) ) {
        // Keep originals after a full revert? No: once the catalog is back
        // to the original, the snapshot has served its purpose. The audit
        // log still records what was applied and reverted.
        delete_post_meta( $product_id, '_ovo_originals' );
    } else {
        // Partial revert: keep originals for the fields still enriched.
        $kept = array();
        foreach ( $enriched as $key => $entry ) {
            if ( array_key_exists( $key, $originals ) ) {
                $kept[ $key ] = $originals[ $key ];
            }
        }
        update_post_meta( $product_id, '_ovo_originals', $kept );
    }
    if ( function_exists( 'wc_delete_product_transients' ) ) {
        wc_delete_product_transients( $product_id );
    }
    ovo_enrichment_audit(
        array(
            'action'     => 'revert',
            'product_id' => $product_id,
            'field_key'  => $field_key,
            'reverted'   => $reverted,
        )
    );
    return array( 'ok' => true, 'reverted' => $reverted );
}

/* ------------------------------------------------------------------ */
/* REST: public read, admin-only write. No new shared secret in v0.1. */
/* Writes require a logged-in user who can manage options, which in   */
/* the demo is the merchant admin. That is a stated gap, not a claim   */
/* of a scoped agent token, which does not exist yet.                 */
/* ------------------------------------------------------------------ */

function ovo_enrichment_public_product( $product_id ) {
    $product = function_exists( 'wc_get_product' ) ? wc_get_product( $product_id ) : null;
    if ( ! $product ) {
        return null;
    }
    $enriched = ovo_enrichment_enriched( $product_id );
    $fields   = array();
    foreach ( $enriched as $key => $entry ) {
        // Only JSON-LD and descriptive enrichment are exposed here.
        // Price and stock are deliberately absent from this surface.
        // Agents must read them from the store's own product data.
        $fields[] = array(
            'key'        => $key,
            'field'      => $entry['field'],
            'value'      => $entry['new_value'],
            'source'     => $entry['source'],
            'confidence' => $entry['confidence'],
            'batch_id'   => $entry['batch_id'],
        );
    }
    return array(
        'product_id'    => $product_id,
        'permalink'     => get_permalink( $product_id ),
        'tool_endpoint' => rest_url( 'ovo/v1/products/' . $product_id ),
        'enriched'      => ! empty( $fields ),
        'fields'        => $fields,
        'price_and_stock_note' => 'Price and stock are not in this block. Read them from the store\'s own product data and Store API.',
    );
}

function ovo_enrichment_register_routes() {
    register_rest_route(
        'ovo/v1',
        '/manifest',
        array(
            'methods'             => 'GET',
            'callback'            => function () {
                return array(
                    'plugin'        => 'ovo-enrichment',
                    'version'       => OVO_ENRICHMENT_VERSION,
                    'tool_endpoint' => rest_url( 'ovo/v1/products' ),
                    'scope'         => 'WordPress + WooCommerce only. Shopify, Wix, and Squarespace are out of scope.',
                    'blocked_fields' => ovo_enrichment_blocked_fields(),
                    'note'          => 'This manifest is not MCP, ACP, or UCP compliance, and it is not consumer Muse discovery.',
                );
            },
            'permission_callback' => '__return_true',
        )
    );
    register_rest_route(
        'ovo/v1',
        '/products',
        array(
            'methods'             => 'GET',
            'callback'            => function () {
                $ids = get_posts(
                    array(
                        'post_type'      => 'product',
                        'post_status'    => 'publish',
                        'posts_per_page' => 100,
                        'fields'         => 'ids',
                        'meta_key'       => '_ovo_enriched',
                    )
                );
                $out = array();
                foreach ( $ids as $id ) {
                    $out[] = ovo_enrichment_public_product( (int) $id );
                }
                return $out;
            },
            'permission_callback' => '__return_true',
        )
    );
    register_rest_route(
        'ovo/v1',
        '/products/(?P<id>\d+)',
        array(
            'methods'             => 'GET',
            'callback'            => function ( $request ) {
                $data = ovo_enrichment_public_product( (int) $request['id'] );
                if ( null === $data ) {
                    return new WP_Error( 'ovo_not_found', 'Product not found.', array( 'status' => 404 ) );
                }
                return $data;
            },
            'permission_callback' => '__return_true',
        )
    );
    register_rest_route(
        'ovo/v1',
        '/diff',
        array(
            'methods'             => 'POST',
            'callback'            => function ( $request ) {
                $params  = $request->get_json_params();
                $batch   = isset( $params['batch_id'] ) ? sanitize_text_field( $params['batch_id'] ) : '';
                $changes = isset( $params['changes'] ) && is_array( $params['changes'] ) ? $params['changes'] : array();
                if ( '' === $batch || empty( $changes ) ) {
                    return new WP_Error( 'ovo_bad_diff', 'batch_id and a non-empty changes list are required.', array( 'status' => 400 ) );
                }
                // Token path, version 0.2: a token call must carry an
                // approval record, or it is rejected before any write.
                // Admin path: the admin posting the diff is the approver,
                // as in version 0.1. That admin-as-approver limit is
                // stated in the readme, not hidden.
                $auth = ovo_enrichment_can_write( $request );
                if ( 'token' === $auth['via'] ) {
                    if ( empty( $params['approved_by'] ) || empty( $params['approval_fingerprint'] ) ) {
                        return new WP_Error( 'ovo_approval_required', 'Token calls must carry approved_by and approval_fingerprint.', array( 'status' => 403 ) );
                    }
                    ovo_enrichment_audit(
                        array(
                            'action'               => 'diff_received_via_token',
                            'batch_id'             => $batch,
                            'approved_by'          => sanitize_text_field( $params['approved_by'] ),
                            'approval_fingerprint' => sanitize_text_field( $params['approval_fingerprint'] ),
                        )
                    );
                }
                $applied = array();
                $rejected = array();
                foreach ( $changes as $change ) {
                    $check = ovo_enrichment_validate_change( $change );
                    if ( ! $check['ok'] ) {
                        $rejected[] = array( 'change' => $change, 'error' => $check['error'] );
                        continue;
                    }
                    $result = ovo_enrichment_apply_change( $change, $batch );
                    if ( $result['ok'] ) {
                        $applied[] = $result['applied'];
                    } else {
                        $rejected[] = array( 'change' => $change, 'error' => $result['error'] );
                    }
                }
                return array( 'batch_id' => $batch, 'applied' => $applied, 'rejected' => $rejected );
            },
            'permission_callback' => function ( $request ) {
                $auth = ovo_enrichment_can_write( $request );
                return $auth['ok'];
            },
        )
    );
    register_rest_route(
        'ovo/v1',
        '/revert',
        array(
            'methods'             => 'POST',
            'callback'            => function ( $request ) {
                $params     = $request->get_json_params();
                $product_id = isset( $params['product_id'] ) ? (int) $params['product_id'] : 0;
                $field_key  = isset( $params['field'] ) ? sanitize_text_field( $params['field'] ) : '';
                if ( $product_id <= 0 ) {
                    return new WP_Error( 'ovo_bad_revert', 'product_id is required.', array( 'status' => 400 ) );
                }
                return ovo_enrichment_revert_product( $product_id, $field_key );
            },
            'permission_callback' => function () {
                return current_user_can( 'manage_options' );
            },
        )
    );
    register_rest_route(
        'ovo/v1',
        '/demo-reset',
        array(
            'methods'             => 'POST',
            'callback'            => function ( $request ) {
                if ( ! get_option( 'ovo_enrichment_demo_mode', false ) ) {
                    return new WP_Error( 'ovo_demo_off', 'Demo mode is off. Turn it on in WooCommerce > OvO Enrichment first.', array( 'status' => 403 ) );
                }
                $params = $request->get_json_params();
                if ( ! isset( $params['confirm'] ) || 'RESET-DEMO' !== $params['confirm'] ) {
                    return new WP_Error( 'ovo_confirm', 'Send confirm set to RESET-DEMO.', array( 'status' => 400 ) );
                }
                $ids = get_posts(
                    array(
                        'post_type'      => 'product',
                        'post_status'    => 'publish',
                        'posts_per_page' => 100,
                        'fields'         => 'ids',
                        'meta_key'       => '_ovo_enriched',
                    )
                );
                $reset = array();
                foreach ( $ids as $id ) {
                    $result  = ovo_enrichment_revert_product( (int) $id, '' );
                    $reset[] = array( 'product_id' => (int) $id, 'reverted' => $result['reverted'] );
                }
                ovo_enrichment_audit( array( 'action' => 'demo-reset', 'products' => $reset ) );
                // Deliberately not touched: WooCommerce orders, carts,
                // shopper sessions, and the audit log itself. A demo reset
                // restores the catalog and OvO state. It does not erase
                // judged history or a shopper's order.
                return array(
                    'reset'              => $reset,
                    'orders_not_touched' => true,
                    'audit_log_kept'     => true,
                );
            },
            'permission_callback' => function () {
                return current_user_can( 'manage_options' );
            },
        )
    );
}
add_action( 'rest_api_init', 'ovo_enrichment_register_routes' );

/* ------------------------------------------------------------------ */
/* Server-rendered output. No JavaScript snippet. Product pages only.  */
/* Nothing is output on cart, checkout, or account pages.              */
/* WooCommerce's own Product JSON-LD is left untouched, so its offers  */
/* block stays canonical. OvO publishes a separate, labelled block.    */
/* ------------------------------------------------------------------ */

function ovo_enrichment_is_forbidden_page() {
    if ( function_exists( 'is_checkout' ) && is_checkout() ) {
        return true;
    }
    if ( function_exists( 'is_cart' ) && is_cart() ) {
        return true;
    }
    if ( function_exists( 'is_account_page' ) && is_account_page() ) {
        return true;
    }
    return false;
}

function ovo_enrichment_output() {
    if ( ovo_enrichment_is_forbidden_page() ) {
        return;
    }
    if ( ! function_exists( 'is_product' ) || ! is_product() ) {
        return;
    }
    $product_id = get_the_ID();
    if ( ! $product_id ) {
        return;
    }
    // Discovery pointer: a plain link to the OvO read surface for this
    // product. It is server-rendered, it is not JavaScript, and it is
    // only on product pages.
    echo '<link rel="alternate" type="application/json" title="OvO enrichment" href="' . esc_url( rest_url( 'ovo/v1/products/' . $product_id ) ) . "\" />\n";
    $data = ovo_enrichment_public_product( $product_id );
    if ( ! $data || empty( $data['fields'] ) ) {
        return;
    }
    $block = array(
        '@context'     => 'https://schema.org',
        '@type'        => 'Product',
        '@id'          => $data['permalink'] . '#ovo-enrichment',
        'sameAs'       => $data['permalink'],
        'name'         => get_the_title( $product_id ),
        'ovoEnrichment' => array(
            'toolEndpoint' => $data['tool_endpoint'],
            'fields'       => $data['fields'],
            'note'         => 'Price and stock are not in this block. Read them from the store\'s own product data.',
        ),
    );
    echo '<script type="application/ld+json" id="ovo-enrichment">' . wp_json_encode( $block ) . "</script>\n";
}
add_action( 'wp_head', 'ovo_enrichment_output', 20 );

/* ------------------------------------------------------------------ */
/* Admin screen: status, demo mode, revert, demo reset, audit log.    */
/* ------------------------------------------------------------------ */

function ovo_enrichment_admin_menu() {
    add_submenu_page(
        'woocommerce',
        'OvO Enrichment',
        'OvO Enrichment',
        'manage_options',
        'ovo-enrichment',
        'ovo_enrichment_admin_page'
    );
}
add_action( 'admin_menu', 'ovo_enrichment_admin_menu' );

function ovo_enrichment_admin_page() {
    if ( ! current_user_can( 'manage_options' ) ) {
        wp_die( 'You do not have permission to view this page.' );
    }
    if ( isset( $_POST['ovo_demo_mode_nonce'] ) && wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['ovo_demo_mode_nonce'] ) ), 'ovo_demo_mode' ) ) {
        update_option( 'ovo_enrichment_demo_mode', isset( $_POST['ovo_demo_mode'] ) ? 1 : 0, false );
        echo '<div class="notice notice-success"><p>Demo mode saved.</p></div>';
    }
    $new_token = '';
    if ( isset( $_POST['ovo_token_nonce'] ) && wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['ovo_token_nonce'] ) ), 'ovo_token' ) ) {
        $new_token = wp_generate_password( 48, false, false );
        update_option( 'ovo_enrichment_token_hash', hash( 'sha256', $new_token ), false );
        ovo_enrichment_audit( array( 'action' => 'token_generated' ) );
    }
    $count = count(
        get_posts(
            array(
                'post_type'      => 'product',
                'post_status'    => 'publish',
                'posts_per_page' => 100,
                'fields'         => 'ids',
                'meta_key'       => '_ovo_enriched',
            )
        )
    );
    $log = get_option( 'ovo_enrichment_audit_log', array() );
    if ( ! is_array( $log ) ) {
        $log = array();
    }
    $log = array_slice( array_reverse( $log ), 0, 50 );
    ?>
    <div class="wrap">
        <h1>OvO Enrichment</h1>
        <p>Demo build <?php echo esc_html( OVO_ENRICHMENT_VERSION ); ?>. Enrichment publishes in place on this store. It never writes price, stock, SKU, tax, shipping, or policy claims from modelled data, and it never changes checkout totals.</p>
        <p><strong>Enriched products:</strong> <?php echo esc_html( $count ); ?></p>
        <p><strong>Install note:</strong> zip upload here is a demo-only method. A real merchant install would be one tap from a CMS app store, which does not exist yet.</p>
        <p><strong>Demo reset:</strong> reverts enrichment to the kept originals and keeps the audit log. It does not delete WooCommerce orders, carts, or shopper sessions. Use the REST demo-reset route with confirm set to RESET-DEMO, with demo mode on.</p>
        <form method="post">
            <?php wp_nonce_field( 'ovo_demo_mode', 'ovo_demo_mode_nonce' ); ?>
            <label><input type="checkbox" name="ovo_demo_mode" value="1" <?php checked( get_option( 'ovo_enrichment_demo_mode', false ), 1 ); ?> /> Demo mode on (required for demo-reset)</label>
            <?php submit_button( 'Save demo mode' ); ?>
        </form>
        <h2>OvO token (version 0.2)</h2>
        <p>Send the token as X-Ovo-Token on POST /ovo/v1/diff. A token call must also carry approved_by and approval_fingerprint. Generating a new token revokes the old one. Only the hash is stored.</p>
        <?php if ( '' !== $new_token ) : ?>
            <p><strong>New token, shown once. Copy it now:</strong> <code><?php echo esc_html( $new_token ); ?></code></p>
        <?php endif; ?>
        <form method="post">
            <?php wp_nonce_field( 'ovo_token', 'ovo_token_nonce' ); ?>
            <?php submit_button( 'Generate new OvO token' ); ?>
        </form>
        <h2>Recent audit log (last 50, newest first)</h2>
        <?php if ( empty( $log ) ) : ?>
            <p>No OvO actions logged yet.</p>
        <?php else : ?>
            <ul>
            <?php foreach ( $log as $entry ) : ?>
                <li><?php echo esc_html( gmdate( 'Y-m-d H:i', strtotime( $entry['at'] ?? '' ) ) . ' — ' . ( $entry['action'] ?? '' ) . ' — product ' . ( $entry['product_id'] ?? '' ) ); ?></li>
            <?php endforeach; ?>
            </ul>
        <?php endif; ?>
    </div>
    <?php
}

function ovo_enrichment_activate() {
    // No catalog change on activation. Enrichment only arrives through
    // an approved diff, so activating the plugin changes nothing yet.
    if ( false === get_option( 'ovo_enrichment_audit_log', false ) ) {
        update_option( 'ovo_enrichment_audit_log', array(), false );
    }
}
register_activation_hook( __FILE__, 'ovo_enrichment_activate' );
