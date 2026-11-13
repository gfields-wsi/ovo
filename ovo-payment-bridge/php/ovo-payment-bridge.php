<?php
/**
 * Plugin Name: OvO Payment Bridge
 * Description: Agent-to-agent programmatic payment, separate from OvO Enrichment. Test mode only. No browser checkout, no card collection, no card storage.
 * Version: 1.0.0
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
 * Phase 6 adds: a single-use human approval token bound to cart and total, and
 * the attribution link written into the WooCommerce order record (session id,
 * cart id, agent route, human approval id, subtotal before tax and shipping).
 * The fee itself is set by OvO billing from the rate in force, not by this plugin.
 * For Level A test mode, a Stripe test helper SPT may be used instead of a Link SPT, and must be labelled as such.
 * v0.4, TEST MODE ONLY: a test-only checkout with no token at all is also allowed, using Stripe's
 * test Visa card pm_card_visa in test mode only, with the host test secret. This is NOT a Link
 * payment, NOT a real card payment, and must be labelled test only. It exists only so a consumer
 * demo can finish without asking the consumer for a token.
 * Merchant stays as merchant of record. Money stays with the merchant.
 * TEST MODE ONLY. A live secret key is rejected. A test secret key is read from host settings
 * or from a private file outside public_html, never from code, logs, or this plugin file.
 * The attribution signing key is read the same way, from host settings or a private file
 * outside public_html, never from code, logs, or this plugin file. Without it, the
 * signed attribution endpoint answers 503: the link is still written into the order
 * record, but no signed event is sent.
 * Do not install on a live store without Greg's separate approval.
 */

if (!defined('ABSPATH')) { exit; }

define('OVO_BRIDGE_VERSION', '1.0.0');
define('OVO_BRIDGE_MANIFEST_PATH', '/ovo-bridge/v1/manifest');
define('OVO_BRIDGE_CHECKOUT_PATH', '/ovo-bridge/v1/checkout/complete');
define('OVO_BRIDGE_APPROVAL_PATH', '/ovo-bridge/v1/approval');
define('OVO_BRIDGE_ATTRIBUTION_PATH', '/ovo-bridge/v1/attribution');

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
    foreach ($candidates as $f) {
        if (is_readable($f)) { $k = trim(file_get_contents($f)); if (strpos($k, 'sk_test_') === 0) return $k; }
    }
    return '';
}

// Attribution signing key, host only. Never hard coded, never in WP options.
function ovo_bridge_signing_key() {
    $key = getenv('OVO_ATTRIBUTION_SIGNING_KEY');
    if ($key) return trim($key);
    $home = getenv('HOME');
    $candidates = array();
    if ($home) $candidates[] = $home . '/ovo-attribution-signing-key';
    foreach ($candidates as $f) {
        if (is_readable($f)) { $k = trim(file_get_contents($f)); if ($k !== '') return $k; }
    }
    return '';
}

function ovo_bridge_manifest_data() {
    $network_id = get_option('ovo_bridge_network_id', '');
    $approval = get_option('ovo_bridge_merchant_approval', array());
    $approved = is_array($approval) && empty($approval['revoked']) && !empty($approval['merchant_id']);
    // TEST ONLY: no Stripe profile id yet, so no network id. Support means
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
    $signing_set = ovo_bridge_signing_key() !== '';
    ?>
    <div class="wrap"><h1>OvO Payment Bridge — Test mode only</h1>
    <p>Agent-to-agent only, no browser checkout. Merchant stays merchant of record. Stripe test secret is read from host settings or a private file outside public_html, never stored here.</p>
    <p><strong>Stripe test secret on host:</strong> <?php echo $secret_set ? 'Set' : 'Not set'; ?>. <strong>Attribution signing key on host:</strong> <?php echo $signing_set ? 'Set' : 'Not set'; ?>. Manifest SPT support: <?php echo ovo_bridge_manifest_data()['spt_support'] ? 'Yes' : 'No'; ?>.<?php if (empty($network)) echo ' Test only: no network id yet. Test helper token only, not real Link.'; ?></p>
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
    register_rest_route('ovo-bridge/v1', '/approval', array(
        'methods' => 'POST',
        'callback' => 'ovo_bridge_issue_approval',
        'permission_callback' => '__return_true',
    ));
    register_rest_route('ovo-bridge/v1', '/checkout/complete', array(
        'methods' => 'POST',
        'callback' => 'ovo_bridge_checkout_complete',
        'permission_callback' => '__return_true',
    ));
    register_rest_route('ovo-bridge/v1', '/attribution/(?P<order_id>\d+)', array(
        'methods' => 'GET',
        'callback' => 'ovo_bridge_attribution_event',
        'permission_callback' => '__return_true',
    ));
});

// Phase 6: single-use human approval token, bound to cart and total.
// Issued after the buyer approves the exact merchant total. Stored as
// a transient for 10 minutes. Used up on first checkout. A token is
// also refused when the live total no longer matches it, so a changed
// cart can never be paid on an old approval.
function ovo_bridge_issue_approval($request) {
    $params = $request->get_json_params();
    if (!is_array($params)) $params = array();
    foreach (array('cart_id', 'total_cents', 'currency', 'session_id', 'human_approval_id', 'agent_token') as $field) {
        if (empty($params[$field])) {
            return ovo_bridge_error('ovo_bridge_missing_field', 400);
        }
    }
    $agent_tokens = get_option('ovo_bridge_agent_tokens', array());
    if (!in_array($params['agent_token'], is_array($agent_tokens) ? $agent_tokens : array(), true)) {
        return ovo_bridge_error('ovo_bridge_unauthorized_agent', 403);
    }
    $approval = get_option('ovo_bridge_merchant_approval', array());
    if (!is_array($approval) || empty($approval['merchant_id']) || !empty($approval['revoked'])) {
        return ovo_bridge_error('ovo_bridge_no_merchant_approval', 403);
    }
    $token = 'appr_' . bin2hex(random_bytes(12));
    set_transient('ovo_bridge_appr_' . md5($token), array(
        'cart_id' => sanitize_text_field($params['cart_id']),
        'total_cents' => (int)$params['total_cents'],
        'currency' => strtoupper(sanitize_text_field($params['currency'])),
        'session_id' => sanitize_text_field($params['session_id']),
        'human_approval_id' => sanitize_text_field($params['human_approval_id']),
    ), 600);
    return array(
        'approval_token' => $token,
        'cart_id' => sanitize_text_field($params['cart_id']),
        'total_cents' => (int)$params['total_cents'],
        'currency' => strtoupper(sanitize_text_field($params['currency'])),
        'expires_in_seconds' => 600,
    );
}

function ovo_bridge_checkout_complete($request) {
    $params = $request->get_json_params();
    if (!is_array($params)) $params = array();

    // v0.4: spt_id is optional when test_card is true. No token is needed then.
    // Phase 6: approval token, session id, agent route, human approval id,
    // and the subtotal split (subtotal, tax, shipping) are required on every
    // checkout. They are the attribution link. No link fields, no checkout.
    foreach (array('cart_id', 'quote_id', 'idempotency_key', 'customer_email', 'shipping_address', 'billing_address', 'agent_token', 'amount_cents', 'currency', 'product_id', 'variation_id', 'approval_token', 'session_id', 'agent_route', 'human_approval_id', 'subtotal_cents', 'tax_cents', 'shipping_cents') as $field) {
        if (!isset($params[$field]) || ($params[$field] === '' && $params[$field] !== 0 && $params[$field] !== '0')) {
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

    // Phase 6: human approval token. Single use, bound to this cart
    // and this total. It is deleted here, so a second checkout with
    // the same token is refused. A token for another cart or total
    // is refused. A declined payment therefore needs a fresh approval.
    $appr_key = 'ovo_bridge_appr_' . md5(sanitize_text_field($params['approval_token']));
    $appr = get_transient($appr_key);
    if (!is_array($appr)) {
        return ovo_bridge_error('ovo_bridge_approval_token', 409);
    }
    delete_transient($appr_key);
    if ($appr['cart_id'] !== $cart_id
        || (int)$appr['total_cents'] !== (int)$params['amount_cents']
        || $appr['currency'] !== strtoupper(sanitize_text_field($params['currency']))
        || $appr['session_id'] !== sanitize_text_field($params['session_id'])
        || $appr['human_approval_id'] !== sanitize_text_field($params['human_approval_id'])) {
        return ovo_bridge_error('ovo_bridge_approval_token', 409);
    }

    // The subtotal split must add up to the total. The fee is 1.5
    // percent of the subtotal, set by OvO billing, not by this plugin.
    $subtotal = (int)$params['subtotal_cents'];
    $tax = (int)$params['tax_cents'];
    $shipping = (int)$params['shipping_cents'];
    if ($subtotal + $tax + $shipping !== (int)$params['amount_cents']) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_quote_void'));
        return ovo_bridge_error('ovo_bridge_quote_void', 409);
    }

    // Live price and stock re-check, from WooCommerce itself, never from the agent.
    $product_id = (int)$params['product_id'];
    $variation_id = (int)$params['variation_id'];
    $quantity = isset($params['quantity']) ? max(1, (int)$params['quantity']) : 1;
    $variation = function_exists('wc_get_product') ? wc_get_product($variation_id) : null;
    // A variation of the product, or the product itself when it is a
    // simple product with no variations. The live test install has
    // simple products only, so a variation-only rule would refuse
    // every checkout there. A simple product is its own line item.
    $is_simple = $variation && (int)$variation->get_parent_id() === 0
        && (int)$variation->get_id() === $product_id;
    if (!$variation || (!$is_simple && (int)$variation->get_parent_id() !== $product_id)) {
        return ovo_bridge_error('ovo_bridge_quote_void', 409);
    }
    if (!$variation->is_in_stock()) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_stock_gone'));
        return ovo_bridge_error('ovo_bridge_stock_gone', 409);
    }
    $expected_subtotal = (int)round((float)$variation->get_price() * 100) * $quantity;
    if ($expected_subtotal !== $subtotal) {
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_quote_void', 'expected_cents' => $expected_subtotal, 'requested_cents' => $subtotal));
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
        'return_url' => home_url('/'),
        'metadata[cart_id]' => $cart_id,
        'metadata[quote_id]' => sanitize_text_field($params['quote_id']),
        'metadata[session_id]' => sanitize_text_field($params['session_id']),
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
    if (($pi['status'] ?? '') === 'requires_action') {
        // An extra card check, such as 3D Secure, fails closed:
        // no paid order is created. The buyer must approve again.
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_requires_action', 'payment_intent_id' => $pi['id'], 'payment_intent_status' => $pi['status']));
        return ovo_bridge_error('ovo_bridge_requires_action', 402);
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
    // Phase 6: the attribution link, written into the order record
    // so the merchant can see it in their own store. The fee is
    // set by OvO billing from the rate in force, not here.
    $order->update_meta_data('_ovo_attribution_session', sanitize_text_field($params['session_id']));
    $order->update_meta_data('_ovo_attribution_cart', $cart_id);
    $order->update_meta_data('_ovo_attribution_agent_route', sanitize_text_field($params['agent_route']));
    $order->update_meta_data('_ovo_attribution_human_approval', sanitize_text_field($params['human_approval_id']));
    $order->update_meta_data('_ovo_attribution_subtotal_cents', $subtotal);
    $order->update_meta_data('_ovo_attribution_tax_cents', $tax);
    $order->update_meta_data('_ovo_attribution_shipping_cents', $shipping);
    $order->update_meta_data('_ovo_attribution_test_mode', true);
    // Phase 6, Requirement 6: set the shipping and tax lines from
    // the approved split before WooCommerce works the totals out.
    // The approved split is the merchant total: subtotal plus tax
    // plus shipping. Without these lines, calculate_totals() works
    // tax and shipping out from the store rules, and the order
    // total can differ from the amount already charged through
    // Stripe. The lines below carry the approved amounts, in
    // dollars, as WooCommerce expects.
    if ($shipping > 0) {
        $ship_item = new WC_Order_Item_Shipping();
        $ship_item->set_method_title('OvO Bridge Shipping');
        $ship_item->set_method_id('ovo_bridge');
        $ship_item->set_total(number_format($shipping / 100, 2, '.', ''));
        $order->add_item($ship_item);
    }
    if ($tax > 0) {
        $tax_item = new WC_Order_Item_Tax();
        $tax_item->set_label('OvO Bridge Tax');
        $tax_item->set_rate_id(0);
        $tax_item->set_tax_total(number_format($tax / 100, 2, '.', ''));
        $tax_item->set_shipping_tax_total('0');
        $order->add_item($tax_item);
    }
    $order->calculate_totals();
    // Guard, Phase 6: the order total after calculate_totals()
    // must equal the amount already charged. If WooCommerce worked
    // it out differently, the order is not marked paid: it is held
    // for the merchant, the mismatch is logged, and the charge is
    // named in the order note so the merchant can refund it if
    // needed. No paid order is created on a mismatch.
    $order_total_cents = (int)round((float)$order->get_total() * 100);
    if ($order_total_cents !== (int)$params['amount_cents']) {
        $order->update_meta_data('_ovo_bridge_total_mismatch', true);
        $order->update_meta_data('_ovo_bridge_expected_total_cents', $order_total_cents);
        $order->update_meta_data('_ovo_bridge_charged_total_cents', (int)$params['amount_cents']);
        $order->add_order_note(sprintf('OvO Bridge: order total %d cents does not match charged amount %d cents. PaymentIntent %s. Order held, not marked paid.', $order_total_cents, (int)$params['amount_cents'], sanitize_text_field($pi['id'])));
        $order->set_status('on-hold');
        $order->save();
        ovo_bridge_audit(array('action' => 'failed', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'error' => 'ovo_bridge_total_mismatch', 'payment_intent_id' => $pi['id'], 'order_id' => $order->get_id(), 'order_total_cents' => $order_total_cents, 'amount_cents' => (int)$params['amount_cents']));
        return ovo_bridge_error('ovo_bridge_total_mismatch', 409);
    }
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
        'attribution' => array(
            'session_id' => sanitize_text_field($params['session_id']),
            'cart_id' => $cart_id,
            'agent_route' => sanitize_text_field($params['agent_route']),
            'human_approval_id' => sanitize_text_field($params['human_approval_id']),
            'subtotal_cents' => $subtotal,
        ),
    );
    set_transient($idem_key, array('spt_id' => $spt, 'amount_cents' => (int)$params['amount_cents'], 'result' => $result), DAY_IN_SECONDS);
    if (!$test_card && isset($spt_key)) {
        set_transient($spt_key, $result, DAY_IN_SECONDS);
    }
    ovo_bridge_audit(array('action' => 'paid', 'cart_id' => $cart_id, 'quote_id' => $params['quote_id'], 'spt_id' => $spt, 'payment_intent_id' => $pi['id'], 'order_id' => $order->get_id(), 'amount_cents' => (int)$params['amount_cents'], 'currency' => $currency));
    return $result;
}

// Phase 6: signed attribution event for an order, for the OVO host.
// The event carries the link from the order record. It is signed
// with HMAC-SHA256 and the host signing key. Without the key, this
// endpoint answers 503: the link is still in the order record, but
// no signed event is sent. The fee is set by OvO billing, not here.
function ovo_bridge_attribution_event($request) {
    $order_id = (int)$request['order_id'];
    $order = function_exists('wc_get_order') ? wc_get_order($order_id) : null;
    if (!$order) {
        return ovo_bridge_error('ovo_bridge_order_not_found', 404);
    }
    $key = ovo_bridge_signing_key();
    if ($key === '') {
        return ovo_bridge_error('ovo_bridge_signing_key_missing', 503);
    }
    $approval = get_option('ovo_bridge_merchant_approval', array());
    $event = array(
        'session_id' => $order->get_meta('_ovo_attribution_session', true),
        'cart_id' => $order->get_meta('_ovo_attribution_cart', true),
        'order_id' => (string)$order->get_id(),
        'agent_route' => $order->get_meta('_ovo_attribution_agent_route', true),
        'human_approval_id' => $order->get_meta('_ovo_attribution_human_approval', true),
        'subtotal_cents' => (int)$order->get_meta('_ovo_attribution_subtotal_cents', true),
        'currency' => $order->get_currency(),
        'store_url' => home_url('/'),
        'merchant_id' => is_array($approval) ? (string)($approval['merchant_id'] ?? '') : '',
        'test_mode' => true,
        'paid_at_utc' => $order->get_date_paid() ? $order->get_date_paid()->date('c') : gmdate('c'),
    );
    // Canonical form, shared with the Python host: keys sorted,
    // compact separators, slashes unescaped. The host verifies
    // with the same form, so the signature matches across languages.
    ksort($event);
    $canonical = json_encode($event, JSON_UNESCAPED_SLASHES);
    $signature = hash_hmac('sha256', $canonical, $key);
    return array('event' => $event, 'signature' => $signature);
}
