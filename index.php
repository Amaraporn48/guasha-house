<?php
/**
 * Hostinger High-Speed PHP Gateway for Guasha House FastAPI
 * Bridges LiteSpeed Web Server directly to the background Uvicorn daemon
 */

$backend_host = "http://127.0.0.1:8000";
$request_uri = $_SERVER['REQUEST_URI'];
$target_url = $backend_host . $request_uri;

$ch = curl_init($target_url);

curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $_SERVER['REQUEST_METHOD']);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 60);

// Forward all request headers
$headers = [];
$incoming_headers = function_exists('getallheaders') ? getallheaders() : [];
foreach ($incoming_headers as $name => $value) {
    if (strtolower($name) !== 'host' && strtolower($name) !== 'content-length') {
        $headers[] = "$name: $value";
    }
}

$headers[] = "Host: " . (isset($_SERVER['HTTP_HOST']) ? $_SERVER['HTTP_HOST'] : 'guashahouse.com');
$headers[] = "X-Real-IP: " . $_SERVER['REMOTE_ADDR'];
$headers[] = "X-Forwarded-For: " . $_SERVER['REMOTE_ADDR'];
$headers[] = "X-Forwarded-Proto: " . (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? 'https' : 'http');

// Forward request body
$method = $_SERVER['REQUEST_METHOD'];
if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $input = file_get_contents('php://input');
    curl_setopt($ch, CURLOPT_POSTFIELDS, $input);
    if (isset($_SERVER['CONTENT_TYPE'])) {
        $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
    }
}

curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$response = curl_exec($ch);

if ($response === false) {
    $error = curl_error($ch);
    curl_close($ch);
    
    // Server starting up or temporary unavailable
    http_response_code(503);
    header('Content-Type: text/html; charset=utf-8');
    echo "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Guasha House - กำลังเริ่มต้นระบบ</title>";
    echo "<style>body{font-family:sans-serif;text-align:center;padding:50px;background:#f8fafc;}h1{color:#1e293b;}</style></head>";
    echo "<body><h1>🌿 ระบบ Guasha House กำลังเริ่มต้น...</h1><p>กรุณารอประมาณ 5 วินาทีแล้วกดรีเฟรชหน้าใหม่อีกครั้ง</p></body></html>";
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$header_text = substr($response, 0, $header_size);
$body = substr($response, $header_size);

http_response_code($http_code);

// Forward response headers
$header_lines = explode("\r\n", $header_text);
foreach ($header_lines as $index => $line) {
    if ($index > 0 && !empty($line)) {
        if (stripos($line, 'Transfer-Encoding:') === false) {
            header($line, false);
        }
    }
}

echo $body;
