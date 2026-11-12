<?php
// OvO Enrichment uninstall.
// This deletes OvO meta and the audit option only.
// It does NOT silently rewrite native store fields. Revert enrichment
// from WooCommerce > OvO Enrichment, or with the REST revert route,
// before uninstalling if you want the kept originals restored.
// Enriched fields left in place after uninstall are ordinary store
// fields, because they were merchant-approved when applied.
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
    exit;
}
global $wpdb;
$wpdb->query( "DELETE FROM {$wpdb->postmeta} WHERE meta_key IN ('_ovo_enriched', '_ovo_originals')" );
delete_option( 'ovo_enrichment_audit_log' );
delete_option( 'ovo_enrichment_demo_mode' );
delete_option( 'ovo_enrichment_token_hash' );
