<?php
/**
 * Guasha House Zero-Maintenance Self-Healing Gateway
 * Automatically boots backend on demand - never requires manual start
 */

ini_set('display_errors', 0);
error_reporting(0);

$dir = __DIR__;
$backend_host = "http://127.0.0.1:8000";

function wake_up_backend() {
    global $dir;
    $lockfile = sys_get_temp_dir() . '/guasha_boot.lock';
    if (file_exists($lockfile) && (time() - filemtime($lockfile)) < 5) {
        return;
    }
    @touch($lockfile);
    
    $cmd = "cd $dir && bash hostinger_run.sh > uvicorn.log 2>&1 &";
    if (function_exists('exec')) {
        @exec($cmd);
    } elseif (function_exists('shell_exec')) {
        @shell_exec($cmd);
    } elseif (function_exists('system')) {
        @system($cmd);
    } elseif (function_exists('popen')) {
        $p = @popen($cmd, 'r');
        if ($p) @pclose($p);
    }
}

// 1. Check if backend daemon is active with reasonable timeout (0.2s)
$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.2);

// 2. If offline, wake it up!
if (!$fp) {
    wake_up_backend();
    
    // Poll for up to 4 seconds
    for ($i = 0; $i < 20; $i++) {
        usleep(200000); // 0.2s
        $fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.2);
        if ($fp) break;
    }
}

// 3. Proxy request to Uvicorn Backend
if ($fp) {
    fclose($fp);
    
    $request_uri = $_SERVER['REQUEST_URI'] ?? '/';
    $target_url = $backend_host . $request_uri;

    $ch = curl_init($target_url);
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 60);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 5);
    curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

    $headers = [];
    $incoming = function_exists('getallheaders') ? getallheaders() : [];
    $has_cookie = false;
    foreach ($incoming as $name => $value) {
        $lower = strtolower($name);
        if (!in_array($lower, ['host', 'content-length', 'connection'])) {
            $headers[] = "$name: $value";
        }
        if ($lower === 'cookie') $has_cookie = true;
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

// 4. If request is an API request, return JSON error instead of HTML
$request_uri = $_SERVER['REQUEST_URI'] ?? '/';
if (strpos($request_uri, '/api/') !== false) {
    http_response_code(503);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['success' => false, 'detail' => 'ระบบหลังบ้านกำลังเริ่มการทำงาน กรุณารอสักครู่แล้วลองใหม่อีกครั้ง']);
    exit;
}

// 5. Fallback HTML Reload Screen for web browser
header('Content-Type: text/html; charset=utf-8');
?>
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="utf-8">
    <title>🌿 Guasha House</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #fbfaf7; text-align: center; padding: 50px 20px; color: #1a1a1a; }
        .card { max-width: 480px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); border: 1px solid #ede8e1; }
        .spinner { width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #c5a880; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
<div class="card">
    <div style="font-size: 40px;">🌿</div>
    <h3 style="margin: 10px 0;">กำลังเปิดระบบ Guasha House</h3>
    <div class="spinner"></div>
    <p style="color: #666; font-size: 14px;">ระบบกำลังโหลดอัตโนมัติ กรุณารอสักครู่...</p>
</div>
<script>setTimeout(function(){ window.location.reload(); }, 1500);</script>
</body>
</html>
