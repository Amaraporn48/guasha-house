<?php
/**
 * Ultra-Fast Production Reverse Proxy for Guasha House FastAPI
 */

// Disable output buffering for instant streaming
while (ob_get_level()) {
    ob_end_clean();
}

$backend_host = "http://127.0.0.1:8000";
$request_uri = $_SERVER['REQUEST_URI'] ?? '/';
$target_url = $backend_host . $request_uri;

$ch = curl_init($target_url);

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 30);
curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 5);
curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

// Build and forward all incoming HTTP headers
$headers = [];
$incoming_headers = function_exists('getallheaders') ? getallheaders() : [];

$has_cookie = false;
foreach ($incoming_headers as $name => $value) {
    $lower = strtolower($name);
    if (!in_array($lower, ['host', 'content-length', 'connection'])) {
        $headers[] = "$name: $value";
    }
    if ($lower === 'cookie') {
        $has_cookie = true;
    }
}

// Guarantee Cookie forwarding
if (!$has_cookie && !empty($_SERVER['HTTP_COOKIE'])) {
    $headers[] = "Cookie: " . $_SERVER['HTTP_COOKIE'];
}

// Client IP & Proto headers
$headers[] = "Host: " . ($_SERVER['HTTP_HOST'] ?? 'guashahouse.com');
$headers[] = "X-Real-IP: " . ($_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-For: " . ($_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-Proto: " . ((isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http');

// Forward payload body
if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $body = file_get_contents('php://input');
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    if (!empty($_SERVER['CONTENT_TYPE'])) {
        $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
    }
}

curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$raw_response = curl_exec($ch);

if ($raw_response === false) {
    $error = curl_error($ch);
    curl_close($ch);
    
    http_response_code(502);
    header('Content-Type: text/html; charset=utf-8');
    echo "<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#f8fafc;'>";
    echo "<h2>🌿 ระบบ Guasha House กำลังเริ่มต้น กรุณารอสักครู่...</h2>";
    echo "<p><small>กำลังเชื่อมต่อ Uvicorn Backend...</small></p>";
    echo "<script>setTimeout(function(){ location.reload(); }, 2000);</script>";
    echo "</body></html>";
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$header_text = substr($raw_response, 0, $header_size);
$body = substr($raw_response, $header_size);

http_response_code($http_code);

// Forward response headers accurately
$raw_headers = explode("\r\n", $header_text);
foreach ($raw_headers as $index => $header_line) {
    if ($index === 0 || empty(trim($header_line))) {
        continue;
    }
    
    $lower = strtolower($header_line);
    if (strpos($lower, 'transfer-encoding:') === false && strpos($lower, 'connection:') === false) {
        // false as second parameter allows multiple headers of same name (e.g. Set-Cookie)
        header($header_line, false);
    }
}

echo $body;
