<?php
/**
 * Ultra-Fast Production Reverse Proxy with Auto-Healing Daemon for Guasha House
 */

// Disable output buffering
while (ob_get_level()) {
    ob_end_clean();
}

$backend_host = "http://127.0.0.1:8000";

// Self-healing check: Ensure backend daemon is running
function check_and_start_backend() {
    $conn = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.2);
    if (is_resource($conn)) {
        fclose($conn);
        return true;
    }
    
    // Auto-start backend
    $dir = __DIR__;
    $python = file_exists("$dir/venv/bin/python") ? "$dir/venv/bin/python" : "/home/u713703050/python/bin/python3";
    $cmd = "cd " . escapeshellarg($dir) . " && nohup " . escapeshellcmd($python) . " -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips '*' > uvicorn.log 2>&1 &";
    @exec($cmd);
    
    // Wait up to 3 seconds for it to bind
    for ($i = 0; $i < 30; $i++) {
        usleep(100000); // 100ms
        $c = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.1);
        if (is_resource($c)) {
            fclose($c);
            return true;
        }
    }
    return false;
}

check_and_start_backend();

$request_uri = $_SERVER['REQUEST_URI'] ?? '/';
$target_url = $backend_host . $request_uri;

$ch = curl_init($target_url);

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 30);
curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 4);
curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

// Forward all request headers
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

$raw_response = curl_exec($ch);

if ($raw_response === false) {
    curl_close($ch);
    http_response_code(503);
    header('Content-Type: text/html; charset=utf-8');
    echo "<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#fbfaf7;'>";
    echo "<h2>🌿 กำลังเริ่มต้นระบบ Guasha House กรุณารอสักครู่...</h2>";
    echo "<script>setTimeout(function(){ location.reload(); }, 1500);</script>";
    echo "</body></html>";
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$header_text = substr($raw_response, 0, $header_size);
$body = substr($raw_response, $header_size);

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
