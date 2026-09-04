<?php
/**
 * Guasha House Dual-Mode Gateway
 * Mode 1: High-Speed Reverse Proxy (if uvicorn daemon is running)
 * Mode 2: In-Process WSGI CGI (Instant execution without daemon requirement)
 */

ini_set('display_errors', 0);
error_reporting(0);

$dir = __DIR__;
$backend_host = "http://127.0.0.1:8000";

// Step 1: Check if persistent Uvicorn daemon is listening
$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.05);

if ($fp) {
    fclose($fp);
    
    // --- MODE 1: Fast Proxy to Uvicorn ---
    $request_uri = $_SERVER['REQUEST_URI'] ?? '/';
    $target_url = $backend_host . $request_uri;

    $ch = curl_init($target_url);
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 2);
    curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

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

    if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
        $body = file_get_contents('php://input');
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        if (!empty($_SERVER['CONTENT_TYPE'])) {
            $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
        }
    }
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

    $response = curl_exec($ch);
    if ($response !== false) {
        $header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        $header_text = substr($response, 0, $header_size);
        $body = substr($response, $header_size);
        http_response_code($http_code);

        $raw_headers = explode("\r\n", $header_text);
        foreach ($raw_headers as $index => $header_line) {
            if ($index === 0 || empty(trim($header_line))) continue;
            $lower = strtolower($header_line);
            if (strpos($lower, 'transfer-encoding:') === false && strpos($lower, 'connection:') === false) {
                header($header_line, false);
            }
        }
        echo $body;
        exit;
    }
    curl_close($ch);
}

// --- MODE 2: In-Process WSGI CGI Execution ---
$pythons = [
    "$dir/venv/bin/python",
    "$dir/venv/bin/python3",
    "/home/u713703050/python/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
    "python3"
];

$python_bin = "python3";
foreach ($pythons as $p) {
    if (file_exists($p) && is_executable($p)) {
        $python_bin = $p;
        break;
    }
}

$descriptorspec = [
    0 => ["pipe", "r"], // STDIN
    1 => ["pipe", "w"], // STDOUT
    2 => ["pipe", "w"]  // STDERR
];

$env = $_SERVER;
$env['SCRIPT_FILENAME'] = "$dir/wsgi_runner.py";
$env['SCRIPT_NAME'] = "";
$req_uri = $_SERVER['REQUEST_URI'] ?? '/';
$uri_parts = explode('?', $req_uri, 2);
$env['PATH_INFO'] = $uri_parts[0];
$env['QUERY_STRING'] = $uri_parts[1] ?? ($_SERVER['QUERY_STRING'] ?? '');
$env['SERVER_NAME'] = $_SERVER['HTTP_HOST'] ?? 'guashahouse.com';
$env['SERVER_PORT'] = ($_SERVER['SERVER_PORT'] ?? '443');
$env['SERVER_PROTOCOL'] = $_SERVER['SERVER_PROTOCOL'] ?? 'HTTP/1.1';
$env['REQUEST_METHOD'] = $_SERVER['REQUEST_METHOD'] ?? 'GET';

$process = @proc_open("$python_bin $dir/wsgi_runner.py", $descriptorspec, $pipes, $dir, $env);

if (is_resource($process)) {
    $input = file_get_contents('php://input');
    if (!empty($input)) {
        fwrite($pipes[0], $input);
    }
    fclose($pipes[0]);

    $output = stream_get_contents($pipes[1]);
    fclose($pipes[1]);
    $errors = stream_get_contents($pipes[2]);
    fclose($pipes[2]);
    proc_close($process);

    if (!empty($output)) {
        $parts = explode("\r\n\r\n", $output, 2);
        if (count($parts) < 2) {
            $parts = explode("\n\n", $output, 2);
        }
        if (count($parts) === 2) {
            $header_lines = explode("\n", $parts[0]);
            foreach ($header_lines as $h) {
                $h = trim($h);
                if (empty($h)) continue;
                if (stripos($h, 'Status:') === 0) {
                    $code = intval(trim(substr($h, 7)));
                    http_response_code($code);
                } else {
                    header($h, false);
                }
            }
            echo $parts[1];
            exit;
        }
    }
}

// Fallback Diagnostic screen
http_response_code(503);
header('Content-Type: text/html; charset=utf-8');
echo "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Guasha House</title></head>";
echo "<body style='font-family:-apple-system,sans-serif;text-align:center;padding:50px;background:#fbfaf7;'>";
echo "<div style='max-width:500px;margin:0 auto;background:#fff;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.05);'>";
echo "<h2 style='color:#1a1a1a;'>🌿 กำลังเชื่อมต่อระบบ Guasha House</h2>";
echo "<p style='color:#666;'>กำลังรีสตาร์ทระบบอัตโนมัติ กรุณารอสักครู่...</p>";
echo "<script>setTimeout(function(){ window.location.reload(); }, 2000);</script>";
echo "</div></body></html>";
