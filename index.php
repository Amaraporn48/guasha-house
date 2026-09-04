<?php
/**
 * Guasha House Zero-Hang Gateway
 * Direct Execution with Real-Time Diagnostics
 */

ini_set('display_errors', 1);
error_reporting(E_ALL);

$dir = __DIR__;

// 1. First check if persistent daemon is running on 8000 with ultra-short timeout (0.01s)
$is_daemon_up = false;
$s = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.01);
if ($s) {
    fclose($s);
    $is_daemon_up = true;
}

if ($is_daemon_up) {
    $request_uri = $_SERVER['REQUEST_URI'] ?? '/';
    $target_url = "http://127.0.0.1:8000" . $request_uri;

    $ch = curl_init($target_url);
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 5);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 1);
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

// 2. Try In-Process WSGI Execution
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
    0 => ["pipe", "r"],
    1 => ["pipe", "w"],
    2 => ["pipe", "w"]
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
$output = "";
$errors = "";

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

// 3. Transparent Diagnostic Output (NO INFINITE RELOAD)
header('Content-Type: text/html; charset=utf-8');
?>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>🌿 Guasha House - Status Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fbfaf7; color: #2d3748; padding: 40px 20px; }
        .container { max-width: 650px; margin: 0 auto; background: #fff; border-radius: 16px; padding: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #ede8e1; }
        h2 { margin-top: 0; color: #1a202c; font-size: 22px; }
        .box { background: #1a202c; color: #68d391; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; overflow-x: auto; white-space: pre-wrap; margin-top: 15px; max-height: 250px; }
        .btn { display: inline-block; background: #c5a880; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 15px; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
        .badge-warn { background: #feebc8; color: #c05621; }
    </style>
</head>
<body>
<div class="container">
    <div style="font-size: 40px; margin-bottom: 10px;">🌿</div>
    <h2>ระบบ Guasha House</h2>
    <p><span class="badge badge-warn">Backend Offline</span> เซิร์ฟเวอร์ Python กำลังรอการสั่งรันครั้งแรก</p>
    
    <?php if (!empty($errors)): ?>
        <p><strong>Python Error Output:</strong></p>
        <div class="box"><?php echo htmlspecialchars($errors); ?></div>
    <?php endif; ?>

    <p style="margin-top: 20px; color: #4a5568; font-size: 14px;">
        📌 <strong>คำสั่งเปิดใช้งานบน Hostinger:</strong><br>
        เปิด SSH แล้วรันคำสั่ง: <code>bash hostinger_run.sh</code>
    </p>
</div>
</body>
</html>
