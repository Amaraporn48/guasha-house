<?php
/**
 * Guasha House - Railway Proxy Gateway
 * Forwards all requests to Railway backend (runs 24/7)
 */
ini_set('display_errors', 0);
error_reporting(0);

$RAILWAY_URL = "https://guasha-house-production.up.railway.app";

$request_uri = $_SERVER['REQUEST_URI'] ?? '/';
$target_url = $RAILWAY_URL . $request_uri;

if (!extension_loaded('curl')) {
    http_response_code(503);
    echo "cURL not available";
    exit;
}

$ch = curl_init($target_url);
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 30);
curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 10);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

$headers = [];
$incoming = function_exists('getallheaders') ? getallheaders() : [];
foreach ($incoming as $name => $value) {
    $lower = strtolower($name);
    if (!in_array($lower, ['host', 'content-length', 'connection', 'transfer-encoding'])) {
        $headers[] = "$name: $value";
    }
}
if (!empty($_SERVER['HTTP_COOKIE'])) {
    $headers[] = "Cookie: " . $_SERVER['HTTP_COOKIE'];
}
$headers[] = "Host: guashahouse.com";
$headers[] = "X-Real-IP: " . ($_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-For: " . ($_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-Proto: https";

if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $body = file_get_contents('php://input');
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    if (!empty($_SERVER['CONTENT_TYPE'])) {
        $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
    }
}
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$response = curl_exec($ch);
$curl_error = curl_error($ch);

if ($response !== false && empty($curl_error)) {
    $header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $header_text = substr($response, 0, $header_size);
    $body = substr($response, $header_size);
    http_response_code($http_code);

    foreach (explode("\r\n", $header_text) as $i => $line) {
        if ($i === 0 || empty(trim($line))) continue;
        $lower = strtolower($line);
        if (strpos($lower, 'transfer-encoding:') === false && strpos($lower, 'connection:') === false) {
            header($line, false);
        }
    }
    echo $body;
    exit;
}
curl_close($ch);

// Fallback
http_response_code(503);
header('Content-Type: text/html; charset=utf-8');
?>
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="5">
    <title>🌿 Guasha House</title>
    <style>body{font-family:-apple-system,sans-serif;background:#fbfaf7;text-align:center;padding:50px 20px}.card{max-width:480px;margin:0 auto;background:#fff;padding:30px;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.06);border:1px solid #ede8e1}.spinner{width:40px;height:40px;border:4px solid #f3f3f3;border-top:4px solid #c5a880;border-radius:50%;animation:spin 1s linear infinite;margin:20px auto}@keyframes spin{to{transform:rotate(360deg)}}</style>
</head>
<body>
<div class="card">
    <div style="font-size:40px">🌿</div>
    <h3>กำลังเปิดระบบ Guasha House</h3>
    <div class="spinner"></div>
    <p style="color:#666;font-size:14px">กรุณารอสักครู่...</p>
</div>
</body>
</html>
