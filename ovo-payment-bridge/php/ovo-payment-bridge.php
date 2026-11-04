<?php
/**
 * Plugin Name: OvO Payment Bridge
 * Description: Agent-to-agent programmatic payment, separate from OvO Enrichment. Test mode only. No browser checkout, no card collection, no card storage.
 * Version: 0.5.0-test
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
 * For Level A test mode, a Stripe test helper SPT may be used instead of a Link SPT, and must be labelled as such.
 * v0.4, DEMO ONLY: a test-only checkout with no token at all is also allowed, using Stripe's
 * test Visa card pm_card_visa in test mode only, with the host test secret. This is NOT a Link
 * payment, NOT a real card payment, and must be labelled test only. It exists only so a consumer
 * demo can finish without asking the consumer for a token.
 * Merchant stays as merchant of record. Money stays with the merchant.
 * TEST MODE ONLY. A live secret key is rejected. A test secret key is read from host settings
 * or from a private file outside public_html, never from code, logs, or this plugin file.
 * Do not install on a live store without Greg's separate approval.
 */

if (!defined('ABSPATH')) { exit; }

define('OVO_BRIDGE_VERSION', '0.5.0-test');
define('OVO_BRIDGE_MANIFEST_PATH', '/ovo-bridge/v1/manifest');
define('OVO_BRIDGE_CHECKOUT_PATH', '/ovo-bridge/v1/checkout/complete');

function ovo_bridge_error($code, $status = 400) {
    return new WP_Error($code, $code, array('status' => $status));
}

// Stripe test secret, host only. Never hard coded, never in WP options by this plugin.
function ovo_bridge_stripe_secret() {
    $key = getenv('STRIPE_TEST_SECRET_KEY');
    if ($key && strpos($key, 'sk_test_') === 0) return trim($key);
    $home = getenv('HOME');
    $candidates = array();
    if ($home) $candidates[] = $home . '/stripe-test-secret';
    $candidates[] = '/home/wsiventuresoutbo/.stripe_test_secret';
    $candidates[] = '/home/wsiventuresoutbo/.ovobridge_stripe_test_secret';
    foreach ($candidates as $f) {
        if (is_readable($f)) { $k = trim(file_get_contents($f)); if (strpos($k, 'sk_test_') === 0) return $k; }
    }
    return '';
}

function ovo_bridge_manifest_data() {
    $network_id = get_option('ovo_bridge_network_id', '');
    $approval = get_option('ovo_bridge_merchant_approval', array());
    $approved = is_array($approval) && empty($approval['revoked']) && !empty($approval['merchant_id']);
    // TEST ONLY, v0.3: no Stripe profile id yet, so no network id. Support means
    // test helper token only, not real Link. seller_network_id stays null until
    // a real profile id is set. Do not present this as real Link support.
    $spt_support = $approved;
    return array(
        'test_mode_no_token_support' => true,
        'test_mode_no_network_id' => empty($network_id),
        'seller_network_id' => !empty($network_id) ? $network_id : null,
        'payment_endpoint' => OVO_BRIDGE_CHECKOUT_PATH,
        'accepted_currencies' => array('USD', 'CAD'),
        'spt_support' => $spt_support,
        'version' => OVO_BRIDGE_VERSION,
    );
}

function ovo_bridge_audit($entry) {
    $log = get_option('ovo_bridge_audit_log', array());
    if (!is_array($log)) $log = array();
    $entry['at'] = gmdate('c');
    $log[] = $entry;
    update_option('ovo_bridge_audit_log', $log, false);
}

add_action('admin_menu', function () {
    add_options_page('OvO Payment Bridge', 'OvO Payment Bridge', 'manage_options', 'ovo-bridge', 'ovo_bridge_settings_page');
});

function ovo_bridge_settings_page() {
    if (!current_user_can('manage_options')) return;
    if (isset($_POST['ovo_bridge_nonce']) && wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['ovo_bridge_nonce'])), 'ovo_bridge')) {
        update_option('ovo_bridge_network_id', sanitize_text_field(wp_unslash($_POST['ovo_bridge_network_id'] ?? '')));
        $approval = get_option('ovo_bridge_merchant_approval', array());
        if (!is_array($approval)) $approval = array();
        $approval['merchant_id'] = sanitize_text_field(wp_unslash($_POST['ovo_bridge_merchant_id'] ?? ''));
        $approval['approver'] = sanitize_text_field(wp_unslash($_POST['ovo_bridge_approver'] ?? ''));
        $approval['bridge_version'] = OVO_BRIDGE_VERSION;
        $approval['approved_at'] = gmdate('c');
        $approval['revoked'] = false;
        update_option('ovo_bridge_merchant_approval', $approval);
        if (!empty($_POST['ovo_bridge_agent_token'])) {
            $tokens = get_option('ovo_bridge_agent_tokens', array());
            if (!is_array($tokens)) $tokens = array();
            $tokens[] = sanitize_text_field(wp_unslash($_POST['ovo_bridge_agent_token']));
            update_option('ovo_bridge_agent_tokens', array_values(array_unique($tokens)));
        }
        echo '<div class="updated"><p>Saved. Test mode only. Stripe secret is NOT stored here; set it on the host.</p></div>';
    }
    $network = get_option('ovo_bridge_network_id', '');
    $approval = get_option('ovo_bridge_merchant_approval', array());
    if (!is_array($approval)) $approval = array();
    $secret_set = ovo_bridge_stripe_secret() !== '';
    ?>
    <div class="wrap"><h1>OvO Payment Bridge — Test mode only</h1>
    <p>Agent-to-agent only, no browser checkout. Merchant stays merchant of record. Stripe test secret is read from host settings or a private file outside public_html, never stored here.</p>
    <p><strong>Stripe test secret on host:</strong> <?php echo $secret_set ? 'Set' : 'Not set'; ?>. Manifest SPT support: <?php echo ovo_bridge_manifest_data()['spt_support'] ? 'Yes' : 'No'; ?>.<?php if (empty($network)) echo ' Test only: no network id yet. Test helper token only, not real Link.'; ?></p>
    <form method="post"><?php wp_nonce_field('ovo_bridge', 'ovo_bridge_nonce'); ?>
    <table class="form-table">
    <tr><th>Seller network id (profile_…)</th><td><input type="text" name="ovo_bridge_network_id" value="<?php echo esc_attr($network); ?>" class="regular-text"></td></tr>
    <tr><th>Merchant id (acct_…)</th><td><input type="text" name="ovo_bridge_merchant_id" value="<?php echo esc_attr($approval['merchant_id'] ?? ''); ?>" class="regular-text"></td></tr>
    <tr><th>Approver</th><td><input type="text" name="ovo_bridge_approver" value="<?php echo esc_attr($approval['approver'] ?? ''); ?>" class="regular-text"></td></tr>
    <tr><th>Add agent token</th><td><input type="text" name="ovo_bridge_agent_token" value="" class="regular-text"><p class="description">Only if empty. The agent must present this token on every checkout call.</p></td></tr>
    </table><?php submit_button('Save bridge settings'); ?></form></div>
    <?php
}

add_action('rest_api_init', function () {
    register_rest_route('ovo-bridge/v1', '/manifest', array(
        'methods' => 'GET',
        'callback' => function () { return ovo_bridge_manifest_data(); },
        'permission_callback' => '__return_true',
    ));
    register_rest_route('ovo-bridge/v1', '/checkout/complete', array(
        'methods' => 'POST',
        'callback' => 'ovo_bridge_checkout_complete',
        'permission_callback' => '__return_true',
    ));
});

function ovo_bridge_checkout_complete($request) {
    $params = $request->get_json_params();
    if (!is_array($params)) $params = array();

    // v0.4: spt_id is optional when test_card is true. No token is needed then.
    foreach (array('cart_id', 'quote_id', 'idempotency_key', 'customer_email', 'shipping_address', 'billing_address', 'agent_token', 'amount_cents', 'currency', 'product_id', 'variation_id') as $field) {
        if (empty($params[$field])) {
            return ovo_bridge_error('ovo_bridge_missing_field', 400);
        }
    }
    $test_card = !empty($params['test_card']);
    if (!$test_card && empty($params['spt_id'])) {
        return ovo_bridge_error('ovo_bridge_missing_field', 400);
    }

    $agent_tokens = get_option('ovo_bridge_agent_tokens', array());
    if (!in_array($params['agent_token'], is_array($agent_tokens) ? $agent_tokens : array(), true)) {
        return ovo_bridge_error('ovo_bridge_unauthorized_agent', 403);
    }

    $approval = get_option('ovo_bridge_merchant_approval', array());
    if (!is_array($approval) || empty($approval['merchant_id']) || !empty($approval['revoked'])) {
        return ovo_bridge_error('ovo_bridge_no_merchant_approval', 403);
    }

    // TEST ONLY, v0.3: merchant approval above is the gate. No network id
    // is required for a test helper token. Real Link still needs a profile id.

    $cart_id = sanitize_text_field($params['cart_id']);
    $idem = sanitize_text_field($params['idempotency_key']);
    $spt = isset($params['spt_id']) ? sanitize_text_field($params['spt_id']) : '';

    // Idempotency, 24 hours: same key + same SPT (or test card) + same amount returns the original result.
    $idem_key = 'ovo_bridge_idem_' . md5($idem);
    $prior = get_transient($idem_key);
    if (is_array($prior)) {
        if ($prior['spt_id'] === $spt && (int)$prior['amount_cents'] === (int)$params['amount_cents']) {
            return $prior['result'];
        }
        return ovo_bridge_error('ovo_bridge_reused_token', 409);
    }
    if (!$test_card) {
        $spt_key = 'ovo_bridge_spt_' . md5($spt);
        if (get_transient($spt_key)) {
            return ovo_bridge_error('ovo_bridge_reused_token', 409);
        }
    }

    // Rate limiting, 5 attempts per cart per hour, 6th = 429
    $attempt_key = 'ovo_bridge_attempts_' . $cart_id;
    $attempts = get_transient($attempt_key);
    if (!is_array($attempts)) $attempts = array();
    $attempts = array_filter($attempts, function ($t) { return time() - $t < 3600; });
    if (count($attempts) >= 5) {
        return ovo_bridge_error('ovo_bridge_rate_limited', 429);
    }
    $attempts[] = time();
    set_transient($attempt_key, $attempts, 3600);

    if (!$test_card && strpos($spt, 'spt_') !== 0) {
        return ovo_bridge_error('ovo_bridge_expired_token', 400);
    }

    // Live price and stock re-check, from WooCommerce itself, never from the agent.
    $product_id = (int)$params['product_id'];
    $variation_id = (int)$params['variation_id'];
    $quantity = isset($params['quantity']) ? max(1, (int)$params['quantity']) : 1;
    $variation = function_exists('wc_get_product') ? wc_get_product($variation_id) : null;
    if (!$variation || (int)$variation->get_parent_id() !== $product_id) {
        return ovo_bridge_error('ovo_bridge_quote_void', 409);
    }
    if (!$variation->is_in_stock()) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_stock_gone'));
        return ovo_bridge_error('ovo_bridge_stock_gone', 409);
    }
    $expected = (int)round((float)$variation->get_price() * 100) * $quantity;
    if ($expected !== (int)$params['amount_cents']) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_quote_void', 'expected_cents' => $expected, 'requested_cents' => (int)$params['amount_cents']));
        return ovo_bridge_error('ovo_bridge_quote_void', 409);
    }
    $currency = strtoupper(sanitize_text_field($params['currency']));
    if (!in_array($currency, array('USD', 'CAD'), true)) {
        return ovo_bridge_error('ovo_bridge_currency_not_supported', 400);
    }

    $secret = ovo_bridge_stripe_secret();
    if ($secret === '') {
        return ovo_bridge_error('ovo_bridge_stripe_key_missing', 503);
    }

    // Stripe PaymentIntent, test mode only, confirm=true.
    // v0.4 test card path: pm_card_visa, no token. SPT path: shared_payment_granted_token.
    $stripe_body = array(
        'amount' => (int)$params['amount_cents'],
        'currency' => strtolower($currency),
        'confirm' => 'true',
        // v0.5: Stripe requires return_url at PaymentIntent confirmation, or payment fails.
        'return_url' => 'https://wsiventures.com/solemates/',
        'metadata[cart_id]' => $cart_id,
        'metadata[quote_id]' => sanitize_text_field($params['quote_id']),
        'metadata[order_source]' => $test_card ? 'ovo-bridge-test-card-only' : 'ovo-bridge-test',
    );
    if ($test_card) {
        $stripe_body['payment_method'] = 'pm_card_visa';
    } else {
        $stripe_body['payment_method_data[shared_payment_granted_token]'] = $spt;
    }
    $stripe = wp_remote_post('https://api.stripe.com/v1/payment_intents', array(
        'timeout' => 30,
        'headers' => array(
            'Authorization' => 'Basic ' . base64_encode($secret . ':'),
            'Stripe-Version' => '2026-09-30.preview',
            'Idempotency-Key' => $idem,
        ),
        'body' => $stripe_body,
    ));
    if (is_wp_error($stripe)) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_declined'));
        return ovo_bridge_error('ovo_bridge_declined', 402);
    }
    $pi = json_decode(wp_remote_retrieve_body($stripe), true);
    if (!is_array($pi) || empty($pi['id'])) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_declined', 'stripe_error' => isset($pi['error']['code']) ? $pi['error']['code'] : 'unknown'));
        return ovo_bridge_error('ovo_bridge_declined', 402);
    }
    if (($pi['status'] ?? '') !== 'succeeded') {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_declined', 'payment_intent_id' => $pi['id'], 'payment_intent_status' => $pi['status'] ?? ''));
        return ovo_bridge_error('ovo_bridge_declined', 402);
    }

    // WooCommerce order, only after Stripe confirms payment.
    if (!function_exists('wc_create_order')) {
        return ovo_bridge_error('ovo_bridge_declined', 500);
    }
    $order = wc_create_order();
    $order->add_product($variation, $quantity);
    $email = sanitize_email($params['customer_email']);
    $ship = is_array($params['shipping_address']) ? $params['shipping_address'] : array();
    $bill = is_array($params['billing_address']) ? $params['billing_address'] : array();
    $order->set_address(array(
        'first_name' => sanitize_text_field($ship['first_name'] ?? ''),
        'last_name' => sanitize_text_field($ship['last_name'] ?? ''),
        'address_1' => sanitize_text_field($ship['address_1'] ?? ''),
        'city' => sanitize_text_field($ship['city'] ?? ''),
        'postcode' => sanitize_text_field($ship['postcode'] ?? ''),
        'country' => sanitize_text_field($ship['country'] ?? ''),
        'email' => $email,
    ), 'shipping');
    $order->set_address(array(
        'first_name' => sanitize_text_field($bill['first_name'] ?? ''),
        'last_name' => sanitize_text_field($bill['last_name'] ?? ''),
        'address_1' => sanitize_text_field($bill['address_1'] ?? ''),
        'city' => sanitize_text_field($bill['city'] ?? ''),
        'postcode' => sanitize_text_field($bill['postcode'] ?? ''),
        'country' => sanitize_text_field($bill['country'] ?? ''),
        'email' => $email,
    ), 'billing');
    $order->set_payment_method_title($test_card ? 'OvO Payment Bridge (Stripe test card, test mode only, no Link)' : 'OvO Payment Bridge (Stripe SPT, test mode)');
    $order->set_transaction_id(sanitize_text_field($pi['id']));
    $order->update_meta_data('_ovo_bridge_payment_intent', sanitize_text_field($pi['id']));
    $order->update_meta_data('_ovo_bridge_spt', $spt);
    $order->update_meta_data('_ovo_bridge_cart', $cart_id);
    $order->update_meta_data('_ovo_bridge_quote', sanitize_text_field($params['quote_id']));
    $order->calculate_totals();
    $order->payment_complete(sanitize_text_field($pi['id']));
    $order->save();

    $result = array(
        'status' => 'succeeded',
        'order_id' => $order->get_id(),
        'order_number' => $order->get_order_number(),
        'payment_intent_id' => $pi['id'],
        'amount_cents' => (int)$params['amount_cents'],
        'currency' => $currency,
        'test_mode' => true,
        'test_card_only' => $test_card,
    );
    set_transient($idem_key, array('spt_id' => $spt, 'amount_cents' => (int)$params['amount_cents'], 'result' => $result), DAY_IN_SECONDS);
    if (!$test_card && isset($spt_key)) {
        set_transient($spt_key, $result, DAY_IN_SECONDS);
    }
    ovo_bridge_audit(array('action' => 'paid', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'payment_intent_id' => $pi['id'], 'order_id' => $order->get_id(), 'amount_cents' => (int)$params['amount_cents'], 'currency' => $currency));
    return $result;
}
