<?php
// OvO Harness publish proxy — demo store only, test mode only.
// The browser never sees the OvO token. The token lives only in host
// settings or in a private file outside public_html, and is forwarded
// server-to-server to the merchant's own OvO plugin.
// Publish only runs after a recorded, matching merchant approval in the
// harness. This proxy does not approve anything by itself: it requires
// approved_by and approval_fingerprint in the request, and the plugin
// itself rejects token calls without them.
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
function respond(int $status, array $body): void { http_response_code($status); echo json_encode($body, JSON_UNESCAPED_SLASHES); exit; }
if ($_SERVER['REQUEST_METHOD'] !== 'POST') respond(405, ['error'=>'POST required']);
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
$host = $_SERVER['HTTP_HOST'] ?? '';
if ($origin !== '' && parse_url($origin, PHP_URL_HOST) !== explode(':', $host)[0]) respond(403, ['error'=>'Same-origin requests only']);
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 120000) respond(413, ['error'=>'Request too large']);
$body = json_decode(file_get_contents('php://input', false, null, 0, 120001), true);
if (!is_array($body)) respond(400, ['error'=>'Invalid JSON request']);
$batch = trim((string)($body['batch_id'] ?? ''));
$approved_by = trim((string)($body['approved_by'] ?? ''));
$fingerprint = trim((string)($body['approval_fingerprint'] ?? ''));
$changes = $body['changes'] ?? [];
if ($batch === '' || $approved_by === '' || $fingerprint === '' || !is_array($changes) || count($changes) === 0) {
    respond(400, ['error'=>'batch_id, approved_by, approval_fingerprint, and a non-empty changes list are required. No live request was sent.']);
}
// Demo only, locked: product 23, additional_property, observed prose values only.
$allowed_labels = ['Material','Fit','Returns'];
foreach ($changes as $c) {
    if (!is_array($c) || (int)($c['product_id'] ?? 0) !== 23 || ($c['field'] ?? '') !== 'additional_property' || ($c['source'] ?? '') !== 'observed') {
        respond(400, ['error'=>'Only product 23, additional_property, observed values are allowed in this demo. No live request was sent.']);
    }
    $parts = explode('|', (string)($c['new_value'] ?? ''), 2);
    if (count($parts) < 2 || !in_array(trim($parts[0]), $allowed_labels, true) || trim($parts[1]) === '') {
        respond(400, ['error'=>'new_value must be Material|…, Fit|…, or Returns|… with a non-empty value. No live request was sent.']);
    }
    if (!isset($c['old_value'])) respond(400, ['error'=>'old_value is required for every change. No live request was sent.']);
}
$token = getenv('OVO_TOKEN') ?: getenv('OVO_PLUGIN_TOKEN');
if (!$token) {
    $home = getenv('HOME');
    $candidates = [];
    if ($home) $candidates[] = $home.'/ovo-token';
    $candidates[] = '/home/wsiventuresoutbo/.ovo_token';
    $candidates[] = '/home/wsiventuresoutbo/.ovoharness_ovo_token';
    foreach ($candidates as $f) {
        if (is_readable($f)) { $k = trim(file_get_contents($f)); if ($k !== '') { $token = $k; break; } }
    }
}
if (!$token) respond(503, ['error'=>'OvO token not configured on this host. Set OVO_TOKEN in host settings, or put the token (one line, token only) in ~/ovo-token outside public_html, then run again. No live request was sent.']);
if (!function_exists('curl_init')) respond(503, ['error'=>'PHP cURL extension unavailable. No live request was sent.']);
$payload = ['batch_id'=>$batch, 'approved_by'=>$approved_by, 'approval_fingerprint'=>$fingerprint, 'changes'=>$changes];
$ch = curl_init('https://wsiventures.com/solemates/?rest_route=/ovo/v1/diff');
curl_setopt_array($ch, [CURLOPT_POST=>true, CURLOPT_RETURNTRANSFER=>true, CURLOPT_TIMEOUT=>30, CURLOPT_CONNECTTIMEOUT=>10, CURLOPT_HTTPHEADER=>['Content-Type: application/json','X-Ovo-Token: '.$token], CURLOPT_POSTFIELDS=>json_encode($payload)]);
$raw = curl_exec($ch); $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE); $failed = curl_errno($ch); curl_close($ch);
if ($failed) respond(502, ['error'=>'Plugin request failed or timed out. No result was confirmed.']);
$result = json_decode((string)$raw, true);
if (!is_array($result)) respond(502, ['error'=>'Plugin returned a non-JSON response. No result was confirmed.']);
// Never return the token, even if the plugin echoes it.
$out = json_encode($result);
if (strpos($out, $token) !== false) $out = str_replace($token, '[redacted]', $out);
http_response_code($status);
echo $out;
