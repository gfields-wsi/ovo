<?php
// Stub test for the pure validation logic in ovo-enrichment.php.
// Stubs only the WordPress functions that run at load time. It does not
// boot WordPress or WooCommerce, and it does not touch a live store.
// Run: php tests-stub.php
define( 'ABSPATH', '/tmp/' );
function add_action() {}
function add_filter() {}
function register_activation_hook() {}
function sanitize_text_field( $s ) { return is_string( $s ) ? trim( strip_tags( $s ) ) : $s; }
function wp_kses_post( $s ) { return $s; }
require __DIR__ . '/ovo-enrichment.php';

$tests = array(
    array( 'name' => 'price blocked', 'change' => array( 'product_id' => 110, 'field' => 'price', 'old_value' => '100', 'new_value' => '200', 'source' => 'merchant-provided', 'confidence' => 'high' ), 'want_ok' => false ),
    array( 'name' => 'stock_quantity blocked', 'change' => array( 'product_id' => 110, 'field' => 'stock_quantity', 'old_value' => '', 'new_value' => '5', 'source' => 'observed', 'confidence' => 'high' ), 'want_ok' => false ),
    array( 'name' => 'sku blocked', 'change' => array( 'product_id' => 110, 'field' => 'sku', 'old_value' => 'SM-RUN-004', 'new_value' => 'X', 'source' => 'merchant-provided', 'confidence' => 'high' ), 'want_ok' => false ),
    array( 'name' => 'gtin blocked', 'change' => array( 'product_id' => 110, 'field' => 'gtin', 'old_value' => '', 'new_value' => '123', 'source' => 'merchant-provided', 'confidence' => 'high' ), 'want_ok' => false ),
    array( 'name' => 'unknown field blocked', 'change' => array( 'product_id' => 110, 'field' => 'material', 'old_value' => '', 'new_value' => 'leather', 'source' => 'observed', 'confidence' => 'high' ), 'want_ok' => false ),
    array( 'name' => 'unknown source blocked', 'change' => array( 'product_id' => 110, 'field' => 'image_alt_text', 'old_value' => '', 'new_value' => 'shoe', 'source' => 'guessed', 'confidence' => 'high' ), 'want_ok' => false ),
    array( 'name' => 'modelled description rejected', 'change' => array( 'product_id' => 110, 'field' => 'description', 'old_value' => 'old', 'new_value' => 'new', 'source' => 'modelled', 'confidence' => 'medium' ), 'want_ok' => false ),
    array( 'name' => 'modelled short_description rejected', 'change' => array( 'product_id' => 110, 'field' => 'short_description', 'old_value' => 'old', 'new_value' => 'new', 'source' => 'modelled', 'confidence' => 'medium' ), 'want_ok' => false ),
    array( 'name' => 'observed alt text accepted', 'change' => array( 'product_id' => 110, 'field' => 'image_alt_text', 'old_value' => '', 'new_value' => 'Everyday Comfort Runners in sage green', 'source' => 'observed', 'confidence' => 'medium' ), 'want_ok' => true ),
    array( 'name' => 'modelled additional_property accepted', 'change' => array( 'product_id' => 110, 'field' => 'additional_property', 'old_value' => '', 'new_value' => 'Fit note|True to size', 'source' => 'modelled', 'confidence' => 'medium' ), 'want_ok' => true ),
    array( 'name' => 'missing old_value rejected', 'change' => array( 'product_id' => 110, 'field' => 'image_alt_text', 'new_value' => 'shoe', 'source' => 'observed', 'confidence' => 'medium' ), 'want_ok' => false ),
    array( 'name' => 'confidence below 50 rejected', 'change' => array( 'product_id' => 110, 'field' => 'additional_property', 'old_value' => '', 'new_value' => 'Fit|True to size', 'source' => 'observed', 'confidence' => 'medium', 'confidence_percent' => 40 ), 'want_ok' => false ),
    array( 'name' => 'confidence 90 accepted', 'change' => array( 'product_id' => 110, 'field' => 'additional_property', 'old_value' => '', 'new_value' => 'Fit|True to size', 'source' => 'observed', 'confidence' => 'medium', 'confidence_percent' => 90 ), 'want_ok' => true ),
);
$fail = 0;
foreach ( $tests as $t ) {
    $r = ovo_enrichment_validate_change( $t['change'] );
    $pass = ( $r['ok'] === $t['want_ok'] );
    echo ( $pass ? 'PASS' : 'FAIL' ) . ' ' . $t['name'] . ' (ok=' . var_export( $r['ok'], true ) . ', error=' . $r['error'] . ")\n";
    if ( ! $pass ) { $fail++; }
}
// Structural checks: blocked fields must not appear in the allow map,
// and the output function must guard checkout and cart pages.
$map = ovo_enrichment_field_map();
foreach ( ovo_enrichment_blocked_fields() as $b ) {
    if ( isset( $map[ $b ] ) ) { echo "FAIL blocked field in allow map: $b\n"; $fail++; }
}
$src = file_get_contents( __DIR__ . '/ovo-enrichment.php' );
foreach ( array( 'is_checkout', 'is_cart', 'is_account_page', 'is_product' ) as $guard ) {
    if ( strpos( $src, $guard ) === false ) { echo "FAIL missing guard: $guard\n"; $fail++; }
}
if ( strpos( $src, "'offers'" ) !== false ) { echo "FAIL OVO block contains offers\n"; $fail++; }
echo $fail === 0 ? "ALL STUB TESTS PASSED\n" : "$fail STUB TEST FAILURES\n";
exit( $fail === 0 ? 0 : 1 );
