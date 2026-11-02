<?php
/**
 * Plugin Name: OvO Payment Bridge
 * Description: Agent-to-agent programmatic payment, separate from OvO Enrichment. Test mode only. No browser checkout, no card collection, no card storage.
 * Version: 0.1.0-test
 * Requires at least: 6.0
 * Requires PHP: 7.4
 * Author: OvO
 * Text Domain: ovo-payment-bridge
 *
 * SCOPE, LOCKED: Agent to merchant, programmatic only, no browser step.
 * WordPress + WooCommerce only. Stripe only. Meta Muse as reference agent only.
 * Generic for all OvO merchant customers, on all their web stores.
 * Store address, merchant id, and seller network id are inputs per merchant, never hard coded.
 * Product and amount are inputs per purchase request, never hard coded.
 * Linked Stripe card authentication happens per purchase request, via Link spend request approval at that time.
 * Merchant stays as merchant of record. Money stays with the merchant.
 * No live Stripe call in this skeleton. Test mode only. A real PaymentIntent
 * requires a secret key supplied via environment, test mode first, and fails
 * closed if missing. Do not install on a live store without Greg's separate approval.
 */

if (!defined('ABSPATH')) { exit; }

define('OVO_BRIDGE_VERSION', '0.1.0-test');
define('OVO_BRIDGE_MANIFEST_PATH', '/ovo-bridge/v1/manifest');
define('OVO_BRIDGE_CHECKOUT_PATH', '/ovo-bridge/v1/checkout/complete');

// Error codes, locked to PAYMENT-BRIDGE-REQUIREMENTS-2026-11-02.md
function ovo_bridge_error($code, $status = 400) {
    return new WP_Error($code, $code, array('status' => $status));
}

// Req 1, 2, 4: manifest. Network id is an option per merchant, never hard coded.
// In test mode, a placeholder network id may be set by the merchant in settings;
// if empty, spt_support is false and the bridge cannot start.
function ovo_bridge_manifest_data() {
    $network_id = get_option('ovo_bridge_network_id', '');
    $approval = get_option('ovo_bridge_merchant_approval', array());
    $approved = is_array($approval) && empty($approval['revoked']) && !empty($approval['merchant_id']);
    $spt_support = !empty($network_id) && $approved;
    return array(
        'seller_network_id' => $spt_support ? $network_id : null,
        'payment_endpoint' => OVO_BRIDGE_CHECKOUT_PATH,
        'accepted_currencies' => array('USD', 'CAD'),
        'spt_support' => $spt_support,
        'version' => OVO_BRIDGE_VERSION,
    );
}

add_action('rest_api_init', function () {
    register_rest_route('ovo-bridge/v1', '/manifest', array(
        'methods' => 'GET',
        'callback' => function () { return ovo_bridge_manifest_data(); },
        'permission_callback' => '__return_true',
    ));

    // Req 11: programmatic checkout complete. Schema locked, no card data, no browser form data.
    // This skeleton validates quote, SPT format, amount, currency, address, idempotency,
    // rate limiting, and audit shape. Real Stripe charging is NOT implemented here:
    // it must be added as a separate, test-mode-gated step, with a secret key via
    // environment, and with Greg's separate approval to deploy and to charge live.
    register_rest_route('ovo-bridge/v1', '/checkout/complete', array(
        'methods' => 'POST',
        'callback' => 'ovo_bridge_checkout_complete',
        'permission_callback' => function ($request) {
            // Req 3: agent authorization + merchant bridge approval are checked in callback,
            // so a missing token returns a bridge error code, not a generic 401.
            return true;
        },
    ));
});

function ovo_bridge_checkout_complete($request) {
    $params = $request->get_json_params();
    if (!is_array($params)) { $params = array(); }

    // Req 11.2: schema required
    foreach (array('cart_id', 'quote_id', 'spt_id', 'idempotency_key', 'customer_email', 'shipping_address', 'billing_address', 'agent_token') as $field) {
        if (empty($params[$field])) {
            return ovo_bridge_error('ovo_bridge_missing_field', 400);
        }
    }

    // Req 3: agent authorization, test mode token list is an option, never hard coded in production
    $agent_tokens = get_option('ovo_bridge_agent_tokens', array());
    if (!in_array($params['agent_token'], is_array($agent_tokens) ? $agent_tokens : array(), true)) {
        return ovo_bridge_error('ovo_bridge_unauthorized_agent', 403);
    }

    // Req 4: merchant approval, separate from enrichment approval
    $approval = get_option('ovo_bridge_merchant_approval', array());
    if (!is_array($approval) || empty($approval['merchant_id']) || !empty($approval['revoked'])) {
        return ovo_bridge_error('ovo_bridge_no_merchant_approval', 403);
    }

    $manifest = ovo_bridge_manifest_data();
    if (empty($manifest['spt_support'])) {
        return ovo_bridge_error('ovo_bridge_no_merchant_approval', 403);
    }

    // Req 19: rate limiting, proposed default 5 attempts per cart per hour, 6th = 429
    $cart_id = sanitize_text_field($params['cart_id']);
    $attempt_key = 'ovo_bridge_attempts_' . $cart_id;
    $attempts = get_transient($attempt_key);
    if (!is_array($attempts)) { $attempts = array(); }
    $attempts = array_filter($attempts, function ($t) { return time() - $t < 3600; });
    if (count($attempts) >= 5) {
        return ovo_bridge_error('ovo_bridge_rate_limited', 429);
    }
    $attempts[] = time();
    set_transient($attempt_key, $attempts, 3600);

    // Req 10: SPT format locked
    if (strpos($params['spt_id'], 'spt_') !== 0) {
        return ovo_bridge_error('ovo_bridge_expired_token', 400);
    }

    // Real charging, order creation, and audit are intentionally NOT completed here.
    // Returning this error is fail-closed, not a success claim.
    // Next step, after network id, Link authorization, Stripe key, and deployment
    // approval are resolved 1 by 1, is to implement Req 12-18 behind a test-mode gate.
    return ovo_bridge_error('ovo_bridge_not_implemented_test_mode_only', 501);
}
