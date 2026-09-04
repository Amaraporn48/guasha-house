<?php
/**
 * Guasha House High-Performance LiteSpeed Proxy
 */

ini_set('display_errors', 0);
error_reporting(0);

$backend_host = "http://127.0.0.1:8000";

function start_uvicorn_backend() {
    $dir = __DIR__;
    $python = file_exists("$dir/venv/bin/python") ? "$dir/venv/bin/python" : (file_exists("/home/u713703050/python/bin/python3") ? "/home/u713703050/python/bin/python3" : "python3");
    $cmd = "cd $dir && nohup $python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload --proxy-headers --forwarded-allow-ips '*' > uvicorn.log 2>&1 &";
    @exec($cmd);
    
    for ($i = 0; $i < 20; $i++) {
        usleep(150000);
        $fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.1);
        if ($fp) {
            fclose($fp);
            return true;
        }
    }
    return false;
}

// Check backend availability
$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.1);
if (!$fp) {
    start_uvicorn_backend();
} else {
    fclose($fp);
}

$request_uri = $_SERVER['REQUEST_URI'] ?? '/';
$target_url = $backend_host . $request_uri;

$ch = curl_init($target_url);

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 15);
curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 3);
curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

// Forward all incoming request headers
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

if (!$has_cookie && !empty($_SERVER['HTTP_COOKIE'])) {
    $headers[] = "Cookie: " . $_SERVER['HTTP_COOKIE'];
}

$headers[] = "Host: " . ($_SERVER['HTTP_HOST'] ?? 'guashahouse.com');
$headers[] = "X-Real-IP: " . ($_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-For: " . ($_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-Proto: " . ((isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http');

// Forward body
if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $body = file_get_contents('php://input');
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    if (!empty($_SERVER['CONTENT_TYPE'])) {
        $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
    }
}

curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$response = curl_exec($ch);

if ($response === false) {
    curl_close($ch);
    http_response_code(503);
    header('Content-Type: text/html; charset=utf-8');
    echo "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Guasha House</title></head>";
    echo "<body style='font-family:sans-serif;text-align:center;padding:50px;background:#fbfaf7;'>";
    echo "<h2 style='color:#1a1a1a;'>🌿 กำลังเชื่อมต่อระบบ Guasha House กรุณารอสักครู่...</h2>";
    echo "<p style='color:#666;'>กำลังโหลดหน้าเว็บใหม่อัตโนมัติ...</p>";
    echo "<script>setTimeout(function(){ window.location.reload(); }, 2000);</script>";
    echo "</body></html>";
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$header_text = substr($response, 0, $header_size);
$body = substr($response, $header_size);

http_response_code($http_code);

// Forward response headers
$raw_headers = explode("\r\n", $header_text);
foreach ($raw_headers as $index => $header_line) {
    if ($index === 0 || empty(trim($header_line))) {
        continue;
    }
    $lower = strtolower($header_line);
    if (strpos($lower, 'transfer-encoding:') === false && strpos($lower, 'connection:') === false) {
        header($header_line, false);
    }
}

echo $body;
